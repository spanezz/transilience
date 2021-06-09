from __future__ import annotations
from typing import TYPE_CHECKING, Sequence, Dict, Set, List
import importlib
from . import actions
from . import template
from .role import PendingAction

if TYPE_CHECKING:
    from .role import Role


class Runner:
    def __init__(self, system):
        self.template_engine = template.Engine()
        self.system = system
        self.pending: Dict[str, PendingAction] = {}
        self.notified: Set[str] = set()

    def enqueue_chain(self, role: Role, pending_actions: Sequence[PendingAction]):
        chain: List[actions.Action] = []
        for pa in pending_actions:
            for f in pa.action.list_local_files_needed():
                # TODO: if it's a directory, share by prefix?
                self.system.share_file(f)
            self.pending[pa.action.uuid] = pa
            chain.append(pa.action)
        self.system.enqueue_chain(chain)

    def receive(self):
        for act in self.system.receive_actions():
            pending = self.pending.pop(act.uuid)
            pending.role.notify_done(act)
            if act.result.changed:
                self.notified.update(act.notify)
                changed = "changed"
            else:
                changed = "noop"
            print(f"[{changed} {act.result.elapsed/1000000000:.3f}s] {pending.role.name} {act.name}")

    def add_role(self, name: str, **kw):
        mod = importlib.import_module(f"roles.{name}")
        role = mod.Role(**kw)
        role.name = name
        role.set_runner(self)
        role.main()
