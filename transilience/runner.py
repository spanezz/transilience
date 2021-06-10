from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Set
from collections import defaultdict
import importlib
from . import template
from .role import PendingAction
from .system.local import Local
from .actions import builtin

if TYPE_CHECKING:
    from .role import Role
    from .actions import Namespace
    from .system import System


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
            return act.run(self._system)
        return runner


class Script:
    def __init__(self):
        self._system = Local()
        self.add_namespace(builtin)

    def add_namespace(self, namespace: Namespace, name=None):
        if name is None:
            name = namespace.name
        setattr(self, name, NamespaceRunner(self._system, namespace))


class Runner:
    def __init__(self, system):
        self.template_engine = template.Engine()
        self.system = system
        self.pending: Dict[str, PendingAction] = {}
        self.notified: Set[str] = set()
        self.by_role: Dict[Role, Set[str]] = defaultdict(set)

    def add_pending_action(self, pa: PendingAction):
        for f in pa.action.list_local_files_needed():
            # TODO: if it's a directory, share by prefix?
            self.system.share_file(f)

        # Add to pending queues
        self.pending[pa.action.uuid] = pa
        self.by_role[pa.role].add(pa.action.uuid)

        # File the action for execution
        pa.role.pipeline.add(pa.action)

    def receive(self):
        for act in self.system.receive_actions():
            # Remove from pending queues
            pending = self.pending.pop(act.uuid)
            self.by_role[pending.role].discard(act.uuid)

            if act.result.changed:
                self.notified.update(pending.notify)
                changed = "changed"
            else:
                changed = "noop"
            print(f"[{changed} {act.result.elapsed/1000000000:.3f}s] {pending.role.name} {pending.summary}")

            # Call chained callables, if any.
            # This can enqueue more tasks in the role
            for c in pending.then:
                c(act)

            # Mark role as done if there are no more tasks
            if not self.by_role[pending.role]:
                del self.by_role[pending.role]
                pending.role.close()
                print(f"[done] {pending.role.name}")

    def add_role(self, name: str, **kw):
        mod = importlib.import_module(f"roles.{name}")
        role = mod.Role(**kw)
        role.name = name
        role.set_runner(self)
        role.main()
