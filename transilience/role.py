from __future__ import annotations
from typing import TYPE_CHECKING, Sequence, Optional, List, Union, Tuple
import contextlib
from transilience import actions

if TYPE_CHECKING:
    from .runner import Runner


class PendingAction:
    def __init__(self, role: "Role", action: actions.Action, notify: Optional[List["Role"]] = None):
        self.role = role
        self.action = action
        if notify is None:
            notify = []
        self.notify: List[str] = notify


class ChainHelper:
    def __init__(self, role: "Role"):
        self.role = role
        self.actions: List[actions.Action] = []

    def add(self, act: actions.Action, **kw):
        self.actions.append(PendingAction(self.role, act, **kw))

    def notify(self, *args: Tuple[Runner]):
        if not self.actions:
            raise RuntimeError("notify called on an empty chain")
        self.actions[-1].notify.extend(args)

    def __iadd__(self, val: Union[actions.Action, Sequence[actions.Action]]):
        if isinstance(val, actions.Action):
            self.add(val)
        else:
            for act in val:
                self.add(act)
        return self


class Role:
    def __init__(self):
        self.name: Optional[str] = None
        self.template_engine = None
        self.runner: "Runner" = None

    @contextlib.contextmanager
    def chain(self):
        c = ChainHelper(self)
        yield c
        self.runner.enqueue_chain(self, c.actions)

    def set_runner(self, runner: "Runner"):
        self.runner = runner
        self.template_engine = runner.template_engine

    def start_chain(self, chain: Sequence[actions.Action]):
        self.runner.enqueue_chain(self, chain)

    def main(self):
        raise NotImplementedError(f"{self.__class__}.start not implemented")

    def notify_done(self, action: actions.Action):
        pass
