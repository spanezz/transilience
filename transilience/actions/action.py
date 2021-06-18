from __future__ import annotations
from typing import TYPE_CHECKING, List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
import contextlib
import subprocess
import traceback
import importlib
import logging
import shutil
import shlex
import time
import uuid
import sys
import os

if TYPE_CHECKING:
    import transilience.system


def doc(default: Any, doc: str, **kw):
    return field(default=default, metadata={"doc": doc})


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

    @contextlib.contextmanager
    def collect(self):
        start_ns = time.perf_counter_ns()
        try:
            yield
        except Exception as e:
            self.state = ResultState.FAILED
            self.exc_type = str(e.__class__)
            self.exc_val = str(e)
            self.exc_tb = traceback.format_tb(sys.exc_info()[2])
        finally:
            self.elapsed = time.perf_counter_ns() - start_ns


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
    result: Result = field(default_factory=Result)

    def __post_init__(self):
        self.log = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

    def summary(self):
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
        return subprocess.run(cmd, check=check, **kw)

    def run(self, system: transilience.system.System):
        """
        Perform the action
        """
        self.result.state = ResultState.NOOP

    def run_pipeline_failed(self, system: transilience.system.System):
        """
        Run in a pipeline where a previous action failed.

        This should normally just set the result state and do nothing
        """
        self.log.info("skipped: a previous task failed in the same pipeline")
        self.result.state = ResultState.SKIPPED

    def run_pipeline_skipped(self, system: transilience.system.System, reason: str):
        """
        Run in a pipeline where a previous action failed.

        This should normally just set the result state and do nothing
        """
        self.log.info("skipped: %s", reason)
        self.result.state = ResultState.SKIPPED

    def serialize(self) -> Dict[str, Any]:
        """
        Serialize this action as a dict
        """
        d = asdict(self)
        d["__action__"] = f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        return d

    @classmethod
    def deserialize(cls, serialized: Dict[str, Any]) -> "Action":
        """
        Deserialize an action form a dict
        """
        action_name = serialized.pop("__action__", None)
        if action_name is None:
            raise ValueError(f"action {serialized!r} has no '__action__' element")
        mod_name, _, cls_name = action_name.rpartition(".")
        mod = importlib.import_module(mod_name)
        action_cls = getattr(mod, cls_name, None)
        if action_cls is None:
            raise ValueError(f"action {action_name!r} not found in transilience.actions")
        if not issubclass(action_cls, Action):
            raise ValueError(f"action {action_name!r} is not an subclass of transilience.actions.Action")
        serialized["result"] = Result(**serialized["result"])
        return action_cls(**serialized)

# https://docs.ansible.com/ansible/latest/collections/index_module.html

# @dataclass
# class AptInstall(Action):
#     packages: Sequence[str]
#     recommends: bool = False
#
#     def run(self, system: System):
#         """
#         Install the given package(s), if they are not installed yet
#         """
#         cmd = ["apt", "-y", "install"]
#         if not self.recommends:
#             cmd.append("--no-install-recommends")
#
#         has_packages = False
#         for pkg in self.packages:
#             if system.has_file("var", "lib", "dpkg", "info", f"{pkg}.list"):
#                 continue
#             cmd.append(pkg)
#             has_packages = True
#
#         if not has_packages:
#             return
#
#         system.run(cmd)
#
#
# @dataclass
# class AptRemove(Action):
#     packages: Sequence[str]
#     purge: bool = False
#
#     def run(self, system: System):
#         """
#         Remove the given packages
#         """
#         cmd = ["apt", "-y", "remove" if self.purge is False else "purge"]
#         for pkg in self.packages:
#             # TODO: check in /var/lib/dpkg if they are already removed/purged
#             cmd.append(pkg)
#         system.run(cmd)
#
#
# @dataclass
# class AptInstallDeb(Action):
#     packages: Sequence[str]
#     recommends: bool = False
#
#     def run(self, system: System):
#         """
#         Install the given package(s), if they are not installed yet
#         """
#         with system.tempdir() as workdir:
#             system_paths = []
#             for package in self.packages:
#                 system.copy_to(package, workdir)
#                 system_paths.append(os.path.join(workdir, os.path.basename(package)))
#
#             cmd = ["apt", "-y", "install"]
#             if not self.recommends:
#                 cmd.append("--no-install-recommends")
#
#             for path in system_paths:
#                 cmd.append(path)
#
#             system.run(cmd)
