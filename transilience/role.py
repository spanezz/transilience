from __future__ import annotations
from typing import TYPE_CHECKING, Sequence, Optional, List, Union, Type, Set, Dict, Tuple
from dataclasses import dataclass, field, make_dataclass, fields
import contextlib
import warnings
import uuid
from . import actions
from .system import PipelineInfo
from .runner import PendingAction

if TYPE_CHECKING:
    from .runner import Runner
    from transilience import template
    from transilience.actions.facts import Facts


def with_facts(facts: Sequence[Facts] = ()):
    """
    Decorate a role, adding all fields from the listed facts to it
    """
    # Merge all fields collected by facts
    cls_fields = {}
    for fact in facts:
        for f in fields(fact):
            if f.name in ("uuid", "result"):
                continue
            cls_fields[f.name] = f

    def wrapper(cls):
        # Merge in fields from the class
        orig = dataclass(cls)
        for f in fields(orig):
            cls_fields[f.name] = f

        return make_dataclass(
                cls_name=cls.__name__,
                fields=[(f.name, f.type, f) for f in cls_fields.values()],
                bases=(cls,),
                namespace={
                    "_facts": tuple(facts),
                },
        )
    return wrapper


@dataclass
class Role:
    """
    A collection of related actions to perform a provisioning macro-task on a
    system.

    The main point of a Role is to enqueue actions to be executed on a System,
    and possibly enqueue some more based on their results
    """
    # Unique identifier for this role
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Name used to display the role
    name: Optional[str] = None

    def __post_init__(self):
        self.template_engine: template.Engine
        self._runner: "Runner"
        # UUIDs of actions sent and not received yet
        self._pending: Set[str] = set()
        self._extra_when: Dict[Union[actions.Action, PendingAction], Union[str, List[str]]] = {}
        self._extra_notify: List[Type["Role"]] = []

    @contextlib.contextmanager
    def when(self, when: Dict[Union[actions.Action, PendingAction], Union[str, List[str]]]):
        """
        Add the given when rules to all actions added during the duration of this context manager.

        Multiple nested context managers add extra rules, and rules merge
        """
        orig_extra_when = self._extra_when
        try:
            self._extra_when = orig_extra_when.copy()
            self._extra_when.update(when)
            yield
        finally:
            self._extra_when = orig_extra_when

    @contextlib.contextmanager
    def notify(self, *args: Tuple[Type["Role"]]):
        """
        Add the given notify rules to all actions added during the duration of this context manager.

        Multiple nested context managers add extra notify entries, and the results merge
        """
        orig_extra_notify = self._extra_notify
        try:
            self._extra_notify = list(orig_extra_notify)
            self._extra_notify.extend(args)
            yield
        finally:
            self._extra_notify = orig_extra_notify

    def task(
            self,
            action: actions.Action,
            notify: Union[None, Type["Role"], Sequence[Type["Role"]]] = None,
            when: Optional[Dict[Union[actions.Action, PendingAction], Union[str, List[str]]]] = None,
            **kw):
        """
        Enqueue an action for execution
        """
        clean_notify: List[Type[Role]] = [] + self._extra_notify
        if notify is None:
            pass
        elif isinstance(notify, type):
            if not issubclass(notify, Role):
                raise RuntimeError("notify elements must be Role subclasses")
            clean_notify.append(notify)
        else:
            clean_notify.extend(notify)
        pa = PendingAction(self, action, notify=clean_notify, **kw)
        self._pending.add(action.uuid)
        self._runner.add_pending_action(pa)

        # Mark files for sharing
        for f in action.list_local_files_needed():
            # TODO: if it's a directory, share by prefix?
            self._runner.system.share_file(f)

        pipeline_info = PipelineInfo(self.uuid)

        if when is not None:
            pipe_when = {}
            for a, s in self._extra_when.items():
                if isinstance(s, str):
                    s = [s]
                pipe_when[a.uuid] = s
            for a, s in when.items():
                if isinstance(s, str):
                    s = [s]
                pipe_when[a.uuid] = s
            pipeline_info.when = pipe_when

        # File the action for execution
        self._runner.system.send_pipelined(action, pipeline_info)

        return pa

    def add(self, *args, **kw):
        warnings.warn("Role.add() has been renamed to Role.task()", DeprecationWarning)
        return self.task(*args, **kw)

    def on_action_executed(self, pending_action: PendingAction, action: actions.Action):
        """
        Called by the runner when an action has been executed
        """
        self._pending.discard(action.uuid)

        # Call chained callables, if any.
        # This can enqueue more tasks in the role
        for c in pending_action.then:
            c(action)

        # Mark role as done if there are no more tasks
        if not self._pending:
            self.close()
            # TODO: move the notification to runner
            from .runner import log
            log.info("%s", f"[done] {self.name}")

    def set_runner(self, runner: "Runner"):
        self._runner = runner
        self.template_engine = runner.template_engine

    def close(self):
        """
        Called when the role is done executing
        """
        self._runner.system.pipeline_close(self.uuid)

    def main(self):
        warnings.warn("Role.main() has been renamed to Role.start()", DeprecationWarning)
        return self.start()

    def start(self):
        raise NotImplementedError(f"{self.__class__}.start not implemented")
