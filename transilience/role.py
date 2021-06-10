from __future__ import annotations
from typing import TYPE_CHECKING, Sequence, Optional, List, Union
import contextlib
from transilience import actions

if TYPE_CHECKING:
    from .runner import Runner


class PendingAction:
    def __init__(
            self,
            role: "Role",
            action: actions.Action,
            name: Optional[str] = None,
            notify: Optional[List["Role"]] = None):
        self._name = name
        self.role = role
        self.action = action
        if notify is None:
            notify = []
        self.notify: List[str] = notify

    @property
    def summary(self):
        if self._name is None:
            self._name = self.action.summary()
        return self._name

    def add(
            self,
            name: Optional[str] = None,
            notify: Union[None, "Role", Sequence["Role"]] = None):
        self._name = name
        if notify is None:
            pass
        elif issubclass(notify, Role):
            self.notify.append(notify)
        else:
            self.notify.extend(notify)
        return self


class ActionMaker:
    def __init__(self, chain: "ChainHelper", module):
        self.chain = chain
        self.module = module

    def __getattr__(self, name: str):
        act_cls = getattr(self.module, name, None)
        if act_cls is not None:
            def make(*args, **kw):
                act = act_cls(*args, **kw)
                return self.chain.add(act)
            return make
        return super().__getattr__(name)


class ChainHelper:
    def __init__(self, role: "Role"):
        self.role = role
        self.actions: List[actions.Action] = []
        self.core = ActionMaker(self, actions)

    def add(self, act: actions.Action, **kw):
        pa = PendingAction(self.role, act, **kw)
        self.actions.append(pa)
        return pa


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
