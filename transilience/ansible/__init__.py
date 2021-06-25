from __future__ import annotations
from typing import TYPE_CHECKING, Type, Dict, Any, List, Optional, Set
from dataclasses import dataclass, fields
import re
import os
import yaml
from ..actions import facts
from ..role import Role, with_facts
from .exceptions import RoleNotFoundError
from .tasks import Task

if TYPE_CHECKING:
    YamlDict = Dict[str, Any]

# Currently supported:
#  - actions in Transilience's builtin.* namespace
#  - arguments not supported by the Transilience action are detected and raise an exception
#  - template action (without block_start_string, block_end_string,
#    lstrip_blocks, newline_sequence, output_encoding, trim_blocks, validate,
#    variable_end_string, variable_start_string)
#  - jinja templates in string parameters, even when present inside lists and
#    dicts and nested lists and dicts
#  - variables from facts provided by transilience.actions.facts.Platform
#  - variables used in templates used in jitsi templates, both in strings and
#    in files
#  - notify/handlers if defined inside thet same role (cannot notify
#    handlers from other roles)


class RoleBuilder:
    def __init__(
            self,
            name: str, tasks: List[Task],
            handlers: Optional[Dict[str, "RoleBuilder"]] = None,
            with_facts: bool = True):
        self.name = name
        self.tasks = tasks
        self.with_facts = with_facts
        self.handlers = handlers if handlers else {}

    def get_role_class(self) -> Type[Role]:
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

        if with_facts:
            role_cls = type(self.name, (Role,), {
                "start": lambda host: None,
                "all_facts_available": role_main
            })
            role_cls = dataclass(role_cls)
            role_cls = with_facts(facts.Platform)(role_cls)
        else:
            role_cls = type(self.name, (Role,), {
                "start": role_main
            })
            role_cls = dataclass(role_cls)

        return role_cls

    def get_python_code_module(self) -> List[str]:
        lines = [
            "from __future__ import annotations",
            "from typing import Any",
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

        role = self.get_role_class()(name=self.name)

        lines = []
        if self.with_facts:
            lines.append("@role.with_facts([facts.Platform])")

        if name is None:
            name = self.get_python_name()

        lines.append(f"class {name}(role.Role):")

        role_vars: Set[str] = set()
        for task in self.tasks:
            role_vars.update(task.list_role_vars(role))

        role_vars -= {f.name for f in fields(facts.Platform)}

        if role_vars:
            lines.append("    # Role variables used by templates")
            for name in sorted(role_vars):
                lines.append(f"    {name}: Any = None")
            lines.append("")

        if self.with_facts:
            lines.append("    def all_facts_available(self):")
        else:
            lines.append("    def start(self):")

        for role_action in self.tasks:
            lines.append(" " * 8 + role_action.get_python(handlers=handlers))

        return lines


class RoleLoader:
    def __init__(self, name: str):
        self.name = name
        self.root = os.path.join("roles", name)
        self.main_tasks = []
        self.handlers: Dict[str, Dict[str, Any]] = {}

    def load_tasks(self):
        tasks_file = os.path.join(self.root, "tasks", "main.yaml")

        try:
            with open(tasks_file, "rt") as fd:
                tasks = yaml.load(fd)
        except FileNotFoundError:
            raise RoleNotFoundError(self.name)

        for task_info in tasks:
            self.main_tasks.append(Task.create(task_info))

    def load_handlers(self):
        handlers_file = os.path.join(self.root, "handlers", "main.yaml")

        try:
            with open(handlers_file, "rt") as fd:
                handlers = yaml.load(fd)
        except FileNotFoundError:
            return

        for info in handlers:
            self.handlers[info["name"]] = RoleBuilder(info["name"], [Task.create(info)], with_facts=False)

    def load(self):
        self.load_handlers()
        self.load_tasks()

    def get_role_class(self) -> Type[Role]:
        builder = RoleBuilder(self.name, self.main_tasks, handlers=self.handlers)
        return builder.get_role_class()

    def get_python_code(self) -> str:
        builder = RoleBuilder(self.name, self.main_tasks, handlers=self.handlers)
        lines = builder.get_python_code_module()

        code = "\n".join(lines)
        try:
            from yapf.yapflib import yapf_api
        except ModuleNotFoundError:
            return code
        code, changed = yapf_api.FormatCode(code)
        return code
