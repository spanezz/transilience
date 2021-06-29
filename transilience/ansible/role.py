from __future__ import annotations
from typing import TYPE_CHECKING, Type, Dict, Any, List, Optional, Set, Sequence
from dataclasses import fields, field, make_dataclass
import zipfile
import shlex
import re
from ..actions import facts, builtin
from ..role import Role, with_facts
from .. import template
from .tasks import Task, TaskTemplate
from .conditionals import Conditional
from .exceptions import RoleNotLoadedError

if TYPE_CHECKING:
    YamlDict = Dict[str, Any]


class AnsibleRole:
    def __init__(self, name: str, uses_facts: bool = True):
        self.name = name
        self.uses_facts = uses_facts
        self.tasks: List[Task] = []
        self.handlers: Dict[str, "AnsibleRole"] = {}
        self.template_engine: template.Engine

    def add_task(self, task_info: YamlDict):
        candidates = []

        for key in task_info.keys():
            if key in ("name", "args", "notify", "when"):
                continue
            candidates.append(key)

        if len(candidates) != 1:
            raise RoleNotLoadedError(f"could not find a known module in task {task_info!r}")

        modname = candidates[0]
        if modname.startswith("ansible.builtin."):
            name = modname[16:]
        else:
            name = modname

        args: YamlDict
        if isinstance(task_info[name], dict):
            args = task_info[name]
        else:
            args = task_info.get("args", {})
            # Fixups for command: in Ansible it can be a simple string instead
            # of a dict
            if name == "command":
                args["argv"] = shlex.split(task_info[name])
            else:
                raise RoleNotLoadedError(f"ansible module argument for {modname} is not a dict")

        if name == "template":
            task = TaskTemplate(args, task_info)
        else:
            action_cls = getattr(builtin, name, None)
            if action_cls is None:
                raise RoleNotLoadedError(f"Action builtin.{name} not available in Transilience")

            transilience_name = f"builtin.{name}"

            task = Task(action_cls, args, task_info, transilience_name)

        notify = task_info.get("notify")
        if notify is not None:
            if isinstance(notify, str):
                notify = [notify]
            for name in notify:
                h = self.handlers[name]
                task.notify.append(h)

        when = task_info.get("when")
        if when is not None:
            if not isinstance(when, list):
                when = [when]
            for expr in when:
                cond = Conditional(self.template_engine, expr)
                task.conditionals.append(cond)

        self.tasks.append(task)

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "role",
            "name": self.name,
            "python_name": self.get_python_name(),
            "uses_facts": self.uses_facts,
            "tasks": [t.to_jsonable() for t in self.tasks],
            "handlers": [h.to_jsonable() for h in self.handlers.values()],
        }

    def list_role_vars(self) -> Sequence[str]:
        role_vars: Set[str] = set()
        for task in self.tasks:
            role_vars.update(task.list_role_vars(self))
        role_vars -= {f.name for f in fields(facts.Platform)}
        return role_vars

    def get_role_class_fields(self):
        fields = []
        for name in sorted(self.list_role_vars()):
            fields.append((name, Any, field(default=None)))
        return fields

    def get_role_class_namespace(self):
        # If we have handlers, instantiate role classes for them
        handler_classes = {}
        for name, role_builder in self.handlers.items():
            handler_classes[name] = role_builder.get_role_class()

        # Create all the functions to start actions in the role
        start_funcs = []
        for role_action in self.tasks:
            start_funcs.append(role_action.get_start_func(handlers=handler_classes))

        # Function that calls all the 'Action start' functions
        def role_main(self):
            for func in start_funcs:
                func(self)

        namespace = {}
        if self.uses_facts:
            namespace["start"] = lambda host: None
            namespace["all_facts_available"] = role_main
        else:
            namespace["start"] = role_main
        return namespace

    def get_role_class(self) -> Type[Role]:
        fields = self.get_role_class_fields()
        namespace = self.get_role_class_namespace()
        if self.uses_facts:
            role_cls = make_dataclass(self.name, fields, bases=(Role,), namespace=namespace)
            role_cls = with_facts(facts.Platform)(role_cls)
        else:
            role_cls = make_dataclass(self.name, fields, bases=(Role,), namespace=namespace)

        return role_cls

    def get_python_code_module(self) -> List[str]:
        lines = [
            "from __future__ import annotations",
            "from typing import Any",
            "import os",
            "from transilience import role",
            "from transilience.actions import builtin, facts",
            "",
        ]

        handlers: Dict[str, str] = {}
        for name, handler in self.handlers.items():
            lines += handler.get_python_code_role()
            lines.append("")
            handlers[name] = handler.get_python_name()

        lines += self.get_python_code_role("Role", handlers=handlers)

        return lines

    def get_python_name(self) -> str:
        name_components = re.sub(r"[^A-Za-z]+", " ", self.name).split()
        return "".join(c.capitalize() for c in name_components)

    def get_python_code_role(self, name=None, handlers: Optional[Dict[str, str]] = None) -> List[str]:
        if handlers is None:
            handlers = {}

        lines = []
        if self.uses_facts:
            lines.append("@role.with_facts([facts.Platform])")

        if name is None:
            name = self.get_python_name()

        lines.append(f"class {name}(role.Role):")

        role_vars = self.list_role_vars()

        if role_vars:
            lines.append("    # Role variables used by templates")
            for name in sorted(role_vars):
                lines.append(f"    {name}: Any = None")
            lines.append("")

        if self.uses_facts:
            lines.append("    def all_facts_available(self):")
        else:
            lines.append("    def start(self):")

        for task in self.tasks:
            for line in task.get_python(handlers=handlers):
                lines.append(" " * 8 + line)

        return lines


class AnsibleRoleFilesystem(AnsibleRole):
    def __init__(self, name: str, root: str, uses_facts: bool = True):
        super().__init__(name, uses_facts=uses_facts)
        self.root = root
        self.template_engine: template.Engine = template.EngineFilesystem([self.root])

    def create_handler_role(self, name: str) -> "AnsibleRoleFilesystem":
        return AnsibleRoleFilesystem(name, root=self.root, uses_facts=False)


class AnsibleRoleZip(AnsibleRole):
    def __init__(self, name: str, archive: zipfile.ZipFile, root: str, uses_facts: bool = True):
        super().__init__(name, uses_facts=uses_facts)
        self.root = root
        self.archive = archive
        self.template_engine: template.Engine = template.EngineZip(archive=archive, root=root)

    def get_role_class_fields(self):
        fields = super().get_role_class_fields()
        fields.append(("role_assets_zipfile", str, self.archive.filename))
        return fields

    def create_handler_role(self, name: str) -> "AnsibleRoleZip":
        return AnsibleRoleZip(name, archive=self.archive, root=self.root, uses_facts=False)
