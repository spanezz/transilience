from __future__ import annotations
from typing import TYPE_CHECKING, Sequence, Optional, List, Union
from transilience import actions

if TYPE_CHECKING:
    from .runner import Runner
    from transilience.system import Pipeline
    from transilience import template


class PendingAction:
    def __init__(
            self,
            role: "Role",
            action: actions.Action,
            name: Optional[str] = None,
            notify: Union[None, "Role", Sequence["Role"]] = None):
        self.name = name
        self.role = role
        self.action = action

        self.notify: List[str]
        if notify is None:
            self.notify = []
        elif issubclass(notify, Role):
            self.notify = [notify]
        else:
            self.notify = list(notify)

    @property
    def summary(self):
        if self.name is None:
            self.name = self.action.summary()
        return self.name

    def add(
            self,
            name: Optional[str] = None,
            notify: Union[None, "Role", Sequence["Role"]] = None):
        self.name = name
        if notify is None:
            pass
        elif issubclass(notify, Role):
            self.notify.append(notify)
        else:
            self.notify.extend(notify)
        return self


class ActionMaker:
    def __init__(self, role: "Role", namespace: actions.Namespace):
        self.role = role
        self.namespace = namespace

    def __getattr__(self, name: str):
        act_cls = getattr(self.namespace, name, None)
        if act_cls is not None:
            def make(*args, **kw):
                act = act_cls(*args, **kw)
                pa = PendingAction(self.role, act)
                self.role._runner.add_pending_action(pa)
                return pa
            return make
        raise AttributeError(name)


class Role:
    """
    A collection of related actions to perform a provisioning macro-task on a
    system.

    The main point of a Role is to enqueue actions to be executed on a System,
    and possibly enqueue some more based on their results
    """
    def __init__(self):
        self.name: Optional[str] = None
        self.template_engine: template.Engine
        self.runner: "Runner"
        self.pipeline: Pipeline

    def add(self, action: actions.Action, **kw):
        pa = PendingAction(self, action, **kw)
        self.runner.add_pending_action(pa)
        return pa

    def set_runner(self, runner: "Runner"):
        self.runner = runner
        self.template_engine = runner.template_engine
        self.pipeline = runner.system.create_pipeline()

    def notify_done(self, action: actions.Action):
        pass

    def close(self):
        """
        Called when the role is done executing
        """
        self.pipeline.close()

    def main(self):
        raise NotImplementedError(f"{self.__class__}.start not implemented")
