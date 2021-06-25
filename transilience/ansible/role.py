from __future__ import annotations
from typing import TYPE_CHECKING, Type, Dict, Any, List, Optional, Set
from dataclasses import dataclass, fields
import re
from ..actions import facts
from ..role import Role, with_facts
from .tasks import Task

if TYPE_CHECKING:
    YamlDict = Dict[str, Any]


class AnsibleRole:
    def __init__(self, name: str, with_facts: bool = True):
        self.name = name
        self.with_facts = with_facts
        self.tasks: List[Task] = []
        self.handlers: Dict[str, "AnsibleRole"] = {}

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
