from __future__ import annotations
from typing import TYPE_CHECKING, Sequence, Optional, List, Union, Type, Set, Dict, Tuple
from dataclasses import dataclass, field, make_dataclass, fields, asdict
import contextlib
import warnings
import uuid
import os
from . import actions
from .system import PipelineInfo
from .runner import PendingAction
from .actions.facts import Facts
from .actions import ResultState
from .actions.misc import Fail
from .actions.action import LocalFileAsset, ZipFileAsset, scalar
from . import template

if TYPE_CHECKING:
    from .runner import Runner


def with_facts(facts: Union[Facts, Sequence[Facts]] = ()):
    """
    Decorate a role, adding all fields from the listed facts to it
    """
    if isinstance(facts, type):
        facts = [facts]

    # Merge all fields collected by facts
    facts_fields = {}
    for fact in facts:
        for f in fields(fact):
            if f.name in ("uuid", "result"):
                continue
            facts_fields[f.name] = f

    def wrapper(cls):
        # Merge in fields from the class
        orig = dataclass(cls)
        for f in fields(orig):
            facts_fields[f.name] = f

        # Create the unique list of facts to use, sorted as they have been
        # added to the class
        all_facts = []
        for f in getattr(cls, "_facts", ()):
            if f not in all_facts:
                all_facts.append(f)
        for f in facts:
            if f not in all_facts:
                all_facts.append(f)

        return make_dataclass(
                cls_name=cls.__name__,
                fields=[(f.name, f.type, f) for f in facts_fields.values()],
                bases=(cls,),
                namespace={
                    "_facts": tuple(all_facts),
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
    role_name: Optional[str] = None
    # Root directory of the filesystem area where role-related files and
    # templates are found.
    # If not provided it defaults to roles/{name}/
    role_assets_root: Optional[str] = None
    role_assets_zipfile: Optional[str] = scalar(
            None, "If the role comes from a .zip file, path to the zipfile that contains this role")

    def __post_init__(self):
        if self.role_assets_root is None:
            self.role_assets_root = os.path.join("roles", self.role_name)
        self.template_engine: template.Engine = template.EngineFilesystem([self.role_assets_root])
        self._runner: "Runner"
        # UUIDs of actions sent and not received yet
        self._pending: Set[str] = set()
        self._extra_when: Dict[Union[actions.Action, PendingAction], Union[str, List[str]]] = {}
        self._extra_notify: List[Type["Role"]] = []
        self._facts_received: Set[Type[Facts]] = set()

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

        pipeline_info = PipelineInfo(self.uuid)
        if when or self._extra_when:
            pipe_when = {}
            for a, s in self._extra_when.items():
                if isinstance(s, str):
                    s = [s]
                pipe_when[a.uuid] = s
            if when:
                for a, s in when.items():
                    if isinstance(s, str):
                        s = [s]
                    pipe_when[a.uuid] = s
            pipeline_info.when = pipe_when

        # File the action for execution
        self._runner.add_pending_action(pa, pipeline_info)

        return pa

    def add(self, *args, **kw):
        warnings.warn("Role.add() has been renamed to Role.task()", DeprecationWarning)
        return self.task(*args, **kw)

    def end(self):
        """
        Called when the role has no more tasks to send.

        This method is not supposed to enqueue more tasks, only to do cleanup
        operations
        """
        pass

    def on_action(self, pending: PendingAction, action: actions.Action):
        """
        Called when an action comes back from the remote with its results
        """
        self._pending.discard(action.uuid)

        if action.result.state != ResultState.FAILED:
            # Call chained callables, if any.
            # This can enqueue more tasks in the role
            for c in pending.then:
                c(action)

            if isinstance(action, Facts):
                # Merge fact info into role members
                for name, value in asdict(action).items():
                    if name not in ("uuid", "result"):
                        setattr(self, name, value)

                facts_available = getattr(self, "facts_available", None)
                if facts_available is not None:
                    facts_available(action)

                have_facts = getattr(self, "have_facts", None)
                if have_facts is not None:
                    have_facts(action)

                # Call all_facts_available() if all the facts we were waiting
                # for were received
                facts_cls = action.__class__
                if facts_cls not in self._facts_received:
                    # We hadn't received this Facts before
                    self._facts_received.add(action.__class__)

                    # Is it one of those we were expecting?
                    wanted_facts = set(getattr(self, "_facts", ()))
                    if facts_cls in wanted_facts:
                        # Are we expecting anything else?
                        if not (self._facts_received - wanted_facts):
                            all_facts_available = getattr(self, "all_facts_available", None)
                            if all_facts_available is not None:
                                all_facts_available()
        else:
            if isinstance(action, Facts):
                # Enqueue a Fail action to stop the pipeline
                self._runner.add_pending_action(
                        Fail("{pending.name!r} failed, pipeline stopped"),
                        PipelineInfo(self.uuid))

    def set_runner(self, runner: "Runner"):
        self._runner = runner

    def main(self):
        warnings.warn("Role.main() has been renamed to Role.start()", DeprecationWarning)
        return self.start()

    def start(self):
        raise NotImplementedError(f"{self.__class__}.start not implemented")

    def lookup_file(self, path: str) -> str:
        """
        Resolve a pathname inside the place where the role assets are stored.
        Returns a pathname to the file
        """
        if self.role_assets_zipfile is not None:
            return ZipFileAsset(self.role_assets_zipfile, os.path.join(self.role_assets_root, path))
        else:
            return LocalFileAsset(os.path.join(self.role_assets_root, path))

    def render_file(self, path: str, **kwargs) -> str:
        """
        Render a Jinja2 template from a file, using as context all Role fields,
        plus the given kwargs.
        """
        ctx = asdict(self)
        ctx.update(kwargs)
        return self.template_engine.render_file(path, ctx)

    def render_string(self, template: str, **kwargs) -> str:
        """
        Render a Jinja2 template from a string, using as context all Role fields,
        plus the given kwargs.
        """
        ctx = asdict(self)
        ctx.update(kwargs)
        return self.template_engine.render_string(template, ctx)

    @classmethod
    def load_python(cls, role_name: str) -> Optional[Type["Role"]]:
        """
        Try to build a Transilience role from a Python module
        """
        import importlib
        mod = importlib.import_module(f"roles.{role_name}")
        if not hasattr(mod, "Role"):
            return None
        return type(role_name, (mod.Role,), {})

    @classmethod
    def load_ansible(cls, role_name: str) -> Optional[Type["Role"]]:
        """
        Try to build a Transilience role from an Ansible YAML role
        """
        from .ansible import FilesystemRoleLoader, RoleNotFoundError
        try:
            loader = FilesystemRoleLoader(role_name)
            loader.load()
        except RoleNotFoundError:
            return None
        return loader.get_role_class()

    @classmethod
    def load(cls, role_name: str) -> Type["Role"]:
        """
        Load a role by its name
        """
        role = cls.load_python(role_name)
        if role is not None:
            return role

        role = cls.load_ansible(role_name)
        if role is not None:
            return role

        raise RuntimeError(f"role {role_name} not found")
