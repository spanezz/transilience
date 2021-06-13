from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Set, Union, Type
import importlib
from . import template
from .role import PendingAction
from .system.local import Local
from .actions import builtin, ResultState

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
            print(f"[{changed} {act.result.elapsed/1000000000:.3f}s] {pending.role.name} {pending.summary}")

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
        role.main()
