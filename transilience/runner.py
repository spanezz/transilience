from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Dict, List, Set, Sequence, Union, Type, Callable
from collections import Counter
from dataclasses import fields
import warnings
import logging
import time
import sys
from . import template
from .system.local import Local
from .actions import builtin, ResultState
from .actions.facts import Facts
from .system import PipelineInfo
from .hosts import Host

if TYPE_CHECKING:
    from .role import Role
    from .actions import Namespace, Action
    from .system import System
    ChainedMethod = Callable[[Action], None]


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
            res = self._system.execute(act)
            if res.result.state == ResultState.FAILED:
                raise RuntimeError(f"{act.summary()} failed with {res.result.exc_type}: {res.result.exc_val}")
            return res
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


class PendingAction:
    """
    Track an action that has been sent to an execution pipeline
    """
    def __init__(
            self,
            role: "Role",
            action: Action,
            notify: List[Type["Role"]],
            name: Optional[str] = None,
            then: Union[None, ChainedMethod, Sequence[ChainedMethod]] = None,
            ):
        self.name = name
        self.roles: List[Role] = [role]
        self.action = action

        self.notify = notify

        self.then: List[ChainedMethod]
        if then is None:
            self.then = []
        elif callable(then):
            self.then = [then]
        else:
            self.then = list(then)

    @property
    def uuid(self):
        return self.action.uuid

    @property
    def summary(self):
        if self.name is None:
            self.name = self.action.summary()
        return self.name


class Runner:
    def __init__(self, host: Union[Host, System], check_mode: bool = False):
        self.started = time.time()
        self.check_mode = check_mode
        self.template_engine = template.Engine()
        if isinstance(host, Host):
            self.host = host
            self.system = host._make_system()
        else:
            warnings.warn("Use a Host instead of a System to instantiate Runner", DeprecationWarning)
            self.host = None
            self.system = host
        self.pending: Dict[str, PendingAction] = {}
        # Cache of facts that have already been collected
        self.facts_cache: Dict[Type[Facts], Facts] = {}
        self.count_by_result = Counter()
        self.progress = logging.getLogger("progress")
        elapsed = f"{time.time() - self.started:.3f}s"
        self.progress.info("%s: [connected %s]", self.system.name, elapsed)

    def add_pending_action(self, pa: PendingAction, pipeline_info: PipelineInfo):
        if self.check_mode:
            pa.action.check = True

        # Add to pending queues
        self.pending[pa.action.uuid] = pa

        # Mark files for sharing
        for f in pa.action.list_local_files_needed():
            # TODO: if it's a directory, share by prefix?
            self.system.share_file(f)

        self.system.send_pipelined(pa.action, pipeline_info)

    def receive(self) -> Set[Type[Role]]:
        notified: Set[Type[Role]] = set()
        for act in self.system.receive_pipelined():
            self.count_by_result[act.result.state] += 1

            # Remove from pending queues
            pending = self.pending.pop(act.uuid, None)
            if pending is not None:
                if act.result.state == ResultState.CHANGED:
                    notified.update(pending.notify)

                if isinstance(act, Facts):
                    # If succeeded:
                    # Add to cache
                    self.facts_cache[act.__class__] = act

                self._notify_action_to_roles(pending, act)
            else:
                log.error("%s: Received unexpected action %r", self.system.name, act)

        return notified

    def _notify_action_to_roles(self, pending: PendingAction, action: Action, cached: bool = False):
        if action.result.state == ResultState.FAILED:
            log_fun = self.progress.error
        elif action.result.state == ResultState.CHANGED:
            log_fun = self.progress.warning
        else:
            log_fun = self.progress.info

        for idx, role in enumerate(pending.roles):
            if cached or idx > 0:
                elapsed = "cached"
            else:
                elapsed = f"{action.result.elapsed/1000000000:.3f}s"

            log_fun("%s: %s%s", self.system.name,
                    f"[{action.result.state} {elapsed}] {role.name} {pending.summary}",
                    " (check)" if self.check_mode else "")
            role.on_action(pending, action)

            # Mark role as done if there are no more tasks
            if not role._pending:
                self.progress.info("%s: %s", self.system.name, f"[done] {role.name}")
                self.system.pipeline_close(role.uuid)
                role.end()

    def add_role(self, role_cls: Union[str, Type[Role]], **kw):
        name = role_cls.__name__

        # TODO: remove this `if` once Role accepts only Host: then we can do
        #       the merging all the time
        if self.host is not None:
            # Add host/group variables to role constructor args
            host_fields = {f.name: f for f in fields(self.host)}
            for field in fields(role_cls):
                if field.name in host_fields:
                    kw.setdefault(field.name, getattr(self.host, field.name))

        role = role_cls(**kw)
        role.name = name
        role.set_runner(self)
        for fact_cls in getattr(role, "_facts", ()):
            cached = self.facts_cache.get(fact_cls)
            if cached is not None:
                # Simulate processing this action for this role
                pa = PendingAction(role, cached, [])
                role._pending.add(cached.uuid)
                self._notify_action_to_roles(pa, cached)
            else:
                # Check if this Facts is already pending: if it is, schedule to
                # notify this role too when it arrives
                for pending in self.pending.values():
                    if pending.action.__class__ == fact_cls:
                        pending.roles.append(role)
                        role._pending.add(pending.action.uuid)
                        break
                else:
                    # Enqueue the facts object as an action on a pipeline by itself
                    facts = fact_cls()
                    pa = PendingAction(role, facts, [])
                    role._pending.add(facts.uuid)
                    self.add_pending_action(pa, PipelineInfo(id=facts.uuid))
        role.start()
        return role

    def main(self):
        """
        Run until all roles are done
        """
        while True:
            todo = self.receive()
            if not todo:
                break

            for role in todo:
                self.add_role(role)

        elapsed = time.time() - self.started
        if elapsed > 60:
            timings = f"{elapsed/60:d}m {elapsed%60:.2f}s"
        elif elapsed > 0.8:
            timings = f"{elapsed:.2f}s"
        elif elapsed > 0.0008:
            timings = f"{elapsed/1000:.2f}ms"
        else:
            timings = f"{elapsed/1000000:.2f}µs"
        self.progress.info(
                "%s: %d total actions in %s: %d unchanged, %d changed, %d skipped, %d failed, %d not executed.",
                self.system.name,
                sum(self.count_by_result.values()),
                timings,
                self.count_by_result[ResultState.NOOP],
                self.count_by_result[ResultState.CHANGED],
                self.count_by_result[ResultState.SKIPPED],
                self.count_by_result[ResultState.FAILED],
                self.count_by_result[ResultState.NONE])

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
