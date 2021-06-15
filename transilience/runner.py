from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Set, Union, Type
import importlib
import logging
import sys
from . import template
from .role import PendingAction
from .system.local import Local
from .actions import builtin, ResultState

if TYPE_CHECKING:
    from .role import Role
    from .actions import Namespace
    from .system import System


log = logging.getLogger("runner")


class NamespaceRunner:
    def __init__(self, system: System, namespace: Namespace):
        self._system = system
        self._namespace = namespace

    def __getattr__(self, name: str):
        act_cls = getattr(self._namespace, name, None)
        if act_cls is None:
            raise AttributeError(name)

        def runner(*args, **kw):
            act = act_cls(*args, **kw)
            return self._system.execute(act)
        return runner


class Script:
    """
    Convenient way to instantiate and run actions on a System, one at a time.

    It defaults to the local system, and it is convenient as a way to use
    Transilience actions as building blocks in normal Python scripts.

    If used remotely, this requires one round trip for each and every action
    that gets executed, and quickly becomes inefficient. Use a pipelining
    runner in that case.
    """
    def __init__(self, system: System = None):
        if system is None:
            system = Local()
        self._system = system
        self.add_namespace(builtin)

    def add_namespace(self, namespace: Namespace, name=None):
        """
        Add a new namespace of actions to those accessible by this Script
        """
        if name is None:
            name = namespace.name
        setattr(self, name, NamespaceRunner(self._system, namespace))


class Runner:
    def __init__(self, system):
        self.template_engine = template.Engine()
        self.system = system
        self.pending: Dict[str, PendingAction] = {}
        self.notified: Set[str] = set()

    def add_pending_action(self, pa: PendingAction):
        # Add to pending queues
        self.pending[pa.action.uuid] = pa

    def receive(self):
        for act in self.system.receive_pipelined():
            # Remove from pending queues
            pending = self.pending.pop(act.uuid)

            if act.result.state == ResultState.CHANGED:
                self.notified.update(pending.notify)
                changed = "changed"
            elif act.result.state == ResultState.SKIPPED:
                changed = "skipped"
            else:
                changed = "noop"
            log.info("%s", f"[{changed} {act.result.elapsed/1000000000:.3f}s] {pending.role.name} {pending.summary}")

            pending.role.on_action_executed(pending, act)

    def add_role(self, role_cls: Union[str, Type[Role]], **kw):
        if isinstance(role_cls, str):
            name = role_cls
            mod = importlib.import_module(f"roles.{role_cls}")
            role = mod.Role(**kw)
        else:
            name = role_cls.__name__
            role = role_cls(**kw)
        role.name = name
        role.set_runner(self)
        role.start()

    def main(self):
        """
        Run until all roles are done
        """
        while True:
            self.receive()

            todo = self.notified
            if not todo:
                break

            self.notified = set()
            for role in todo:
                self.add_role(role)

    @classmethod
    def cli(cls, main):
        def wrapped():
            import argparse
            try:
                import coloredlogs
            except ModuleNotFoundError:
                coloredlogs = None

            parser = argparse.ArgumentParser(description="Provision a system")
            parser.add_argument("-v", "--verbose", action="store_true",
                                help="verbose output")
            parser.add_argument("--debug", action="store_true",
                                help="verbose output")
            args = parser.parse_args()

            FORMAT = "%(asctime)-15s %(levelname)s %(name)s %(message)s"
            PROGRESS_FORMAT = "%(asctime)-15s %(message)s"
            if args.debug:
                log_level = logging.DEBUG
            elif args.verbose:
                log_level = logging.INFO
            else:
                log_level = logging.WARN

            progress_formatter = None
            if coloredlogs is not None:
                coloredlogs.install(level=log_level, fmt=FORMAT, stream=sys.stderr)
                if log_level > logging.INFO:
                    progress_formatter = coloredlogs.ColoredFormatter(fmt=PROGRESS_FORMAT)
            else:
                logging.basicConfig(level=log_level, stream=sys.stderr, format=FORMAT)
                if log_level > logging.INFO:
                    progress_formatter = logging.Formatter(fmt=PROGRESS_FORMAT)

            handler = logging.StreamHandler(stream=sys.stderr)
            handler.setFormatter(progress_formatter)
            log.addHandler(handler)
            log.setLevel(logging.INFO)

            # TODO: add options for specifying remote systems, and pass a
            # system to main
            # TODO: work on multiple systems by starting a thread per system
            # and running main in each thread
            main()

        return wrapped
