from __future__ import annotations
import base64
from dataclasses import dataclass, field, fields, asdict, is_dataclass
import contextlib
import importlib
import logging
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
import traceback
from typing import TYPE_CHECKING, List, Dict, Any, Optional
import uuid
from ..fileasset import FileAsset

if TYPE_CHECKING:
    import transilience.system


def scalar(default: Any, doc: str, octal: bool = False):
    metadata = {"doc": doc}
    if octal:
        metadata["octal"] = True
    return field(default=default, metadata=metadata)


def local_file(default: Any, doc: str):
    metadata = {"doc": doc, "type": "local_file"}
    return field(default=default, metadata=metadata)


class ResultState:
    """
    Enumeration of possible result states for an action
    """
    # No state is available yet
    NONE = "none"
    # The action did not perform any change
    NOOP = "noop"
    # The action performed changes in the system
    CHANGED = "changed"
    # The action was not run, for example because a previous action failed
    SKIPPED = "skipped"
    # The action was run but threw an exception
    FAILED = "failed"


@dataclass
class CommandResult:
    """
    Store information about one command run by an action
    """
    cmdline: List[str] = field(default_factory=list)
    stderr: Optional[str] = None
    returncode: Optional[int] = None


@dataclass
class Result:
    """
    Store information about the execution of an action
    """
    # Execution state
    state: int = ResultState.NONE
    # Elapsed time in nanoseconds
    elapsed: Optional[int] = None
    # Exception type, as a string
    exc_type: Optional[str] = None
    # Exception value, stringified
    exc_val: Optional[str] = None
    # Exception traceback, formatted
    exc_tb: List[str] = field(default_factory=list)
    # Trace of commands run by this action
    command_log: List[CommandResult] = field(default_factory=list)

    @contextlib.contextmanager
    def collect(self):
        start_ns = time.perf_counter_ns()
        try:
            yield
        except Exception as e:
            self.state = ResultState.FAILED
            self.exc_type = e.__class__.__name__
            self.exc_val = str(e)
            self.exc_tb = traceback.format_tb(sys.exc_info()[2])
        finally:
            self.elapsed = time.perf_counter_ns() - start_ns

    def print(self, file=sys.stdout):
        print("State:", self.state, file=file)
        print("Elapsed:", self.elapsed, file=file)
        print("Exception type:", self.exc_type, file=file)
        print("Exception value:", self.exc_val, file=file)
        print("Exception traceback:", "[]" if not self.exc_val else "", file=file)
        for row in self.exc_tb:
            print("    " + row.rstrip(), file=file)
        print("Commands run:", "[]" if not self.command_log else "", file=file)
        for cr in self.command_log:
            print("    Command: ", " ".join(shlex.quote(c) for c in cr.cmdline), file=file)
            print("    Returncode: ", cr.returncode, file=file)
            print("    Stderr: ", "-" if not cr.stderr else "", file=file)
            print(textwrap.indent(cr.stderr, "        "), file=file)

    def log(self, logger):
        logger("State: %s", self.state)
        logger("Elapsed: %s", self.elapsed)
        logger("Exception type: %s", self.exc_type)
        logger("Exception value: %r", self.exc_val)
        if self.exc_tb:
            logger("Exception traceback:")
            for row in self.exc_tb:
                logger("  %s", row.rstrip())
        if self.command_log:
            logger("Commands run:")
            for cr in self.command_log:
                logger("  Command: %s", " ".join(shlex.quote(c) for c in cr.cmdline))
                logger("  Returncode: %d", cr.returncode)
                if cr.stderr:
                    logger("  Stderr:")
                    for line in cr.stderr.splitlines():
                        logger("    %s", line.rstrip())

    @classmethod
    def deserialize(cls, serialized: Dict[str, Any]) -> "Result":
        """
        Deserialize a Result from a dict
        """
        command_log = serialized.pop("command_log", None)
        if command_log is not None:
            command_log = [CommandResult(**cr) for cr in command_log]
        return cls(command_log=command_log, **serialized)


@dataclass
class Action:
    """
    Base class for all action implementations.

    An Action is the equivalent of an ansible module: a declarative
    representation of an idempotent operation on a system.

    An Action can be run immediately, or serialized, sent to a remote system,
    run, and sent back with its results.
    """
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    check: bool = scalar(False, "when True, check if the action would perform changes, but do nothing")
    result: Result = field(default_factory=Result)

    def __post_init__(self):
        self.log = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

    def action_summary(self):
        """
        Return a short text description of this action
        """
        return self.__class__.__name__

    def list_local_files_needed(self) -> List[str]:
        """
        Return a list of all files needed by this action, that are found in the
        local file system
        """
        return []

    def set_changed(self):
        """
        Mark that this action has changed something
        """
        self.result.state = ResultState.CHANGED

    def find_command(self, cmd: str) -> str:
        """
        Look for this command in the path, and return its full path.

        Raises an exception if the command does not exist.
        """
        res = shutil.which(cmd)
        if res is None:
            raise RuntimeError(f"Command {cmd!r} not found on this system")
        return res

    def run_command(self, cmd: List[str], check=True, **kw) -> subprocess.CompletedProcess:
        """
        Run the given command inside the chroot
        """
        self.log.debug("running %s", " ".join(shlex.quote(x) for x in cmd))
        if "env" not in kw:
            kw["env"] = dict(os.environ)
            kw["env"]["LANG"] = "C"

        command_log = CommandResult(cmdline=cmd)
        try:
            res = subprocess.run(cmd, check=check, **kw)
        except subprocess.CalledProcessError as e:
            if e.stderr is None:
                command_log.stderr = None
            elif isinstance(e.stderr, str):
                command_log.stderr = e.stderr
            else:
                command_log.stderr = e.stderr.decode(errors="surrogateescape")
            command_log.returncode = e.returncode
            raise
        else:
            if res.stderr is None:
                command_log.stderr = None
            elif isinstance(res.stderr, str):
                command_log.stderr = res.stderr
            else:
                command_log.stderr = res.stderr.decode(errors="surrogateescape")
            command_log.returncode = res.returncode
        finally:
            self.result.command_log.append(command_log)
        return res

    def action_run(self, system: transilience.system.System):
        """
        Perform the action
        """
        self.result.state = ResultState.NOOP

    def action_run_pipeline_failed(self, system: transilience.system.System):
        """
        Run in a pipeline where a previous action failed.

        This should normally just set the result state and do nothing
        """
        self.log.info("skipped: a previous task failed in the same pipeline")
        self.result.state = ResultState.SKIPPED

    def action_run_pipeline_skipped(self, system: transilience.system.System, reason: str):
        """
        Run in a pipeline where a previous action failed.

        This should normally just set the result state and do nothing
        """
        self.log.info("skipped: %s", reason)
        self.result.state = ResultState.SKIPPED

    def serialize(self) -> Dict[str, Any]:
        """
        Serialize this action as a dict suitable for pickling
        """
        file_assets: List[str] = []
        d = {
            "__action__": f"{self.__class__.__module__}.{self.__class__.__qualname__}",
            "__file_assets__": file_assets,
        }
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, FileAsset):
                d[f.name] = value.serialize()
                file_assets.append(f.name)
            elif is_dataclass(value):
                d[f.name] = asdict(value)
            else:
                d[f.name] = value
        return d

    def serialize_for_json(self) -> Dict[str, Any]:
        """
        Serialize this action as a dict suitable for encoding to JSON
        """
        binary_fields = {}
        file_assets = []
        res = {
            "__action__": f"{self.__class__.__module__}.{self.__class__.__qualname__}",
            "__binary__": binary_fields,
            "__file_assets__": file_assets,
        }
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, bytes):
                binary_fields[f.name] = "a85"
                res[f.name] = base64.a85encode(value).decode()
            elif isinstance(value, FileAsset):
                file_assets.append(f.name)
                res[f.name] = value.serialize()
            elif is_dataclass(value):
                res[f.name] = asdict(value)
            else:
                res[f.name] = value
        return res

    @classmethod
    def deserialize(cls, serialized: Dict[str, Any]) -> "Action":
        """
        Deserialize an Action from a dict
        """
        action_name = serialized.pop("__action__", None)
        if action_name is None:
            raise ValueError(f"action {serialized!r} has no '__action__' element")

        file_assets = serialized.pop("__file_assets__", None)
        if file_assets is None:
            file_assets = []

        # Decode file assets
        for name in file_assets:
            serialized[name] = FileAsset.deserialize(serialized[name])

        mod_name, _, cls_name = action_name.rpartition(".")
        mod = importlib.import_module(mod_name)
        action_cls = getattr(mod, cls_name, None)
        if action_cls is None:
            raise ValueError(f"action {action_name!r} not found in transilience.actions")
        if not issubclass(action_cls, Action):
            raise ValueError(f"action {action_name!r} is not an subclass of transilience.actions.Action")
        serialized["result"] = Result.deserialize(serialized["result"])
        return action_cls(**serialized)

    @classmethod
    def deserialize_from_json(cls, serialized: Dict[str, Any]) -> "Action":
        """
        Deserialize an Action from a dict that was suitable for JSON
        """
        action_name = serialized.pop("__action__", None)
        if action_name is None:
            raise ValueError(f"action {serialized!r} has no '__action__' element")

        file_assets = serialized.pop("__file_assets__", None)
        if file_assets is None:
            file_assets = []

        mod_name, _, cls_name = action_name.rpartition(".")
        mod = importlib.import_module(mod_name)
        action_cls = getattr(mod, cls_name, None)
        if action_cls is None:
            raise ValueError(f"action {action_name!r} not found in transilience.actions")
        if not issubclass(action_cls, Action):
            raise ValueError(f"action {action_name!r} is not an subclass of transilience.actions.Action")

        # Decode binary fields
        binary_fields = serialized.pop("__binary__", None)
        if binary_fields is not None:
            for name, val in binary_fields.items():
                if val == "a85":
                    dec = base64.a85decode
                elif val == "b64":
                    dec = base64.b64decode
                else:
                    raise NotImplementedError(f"unknown binary encoding style: {val!r}")
                serialized[name] = dec(serialized[name])

        # Decode file assets
        for name in file_assets:
            serialized[name] = FileAsset.deserialize(serialized[name])

        serialized["result"] = Result.deserialize(serialized["result"])
        return action_cls(**serialized)

# https://docs.ansible.com/ansible/latest/collections/index_module.html
