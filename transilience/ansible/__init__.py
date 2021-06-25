from __future__ import annotations
from typing import TYPE_CHECKING, Type, Dict, Any
import os
import yaml
from .exceptions import RoleNotFoundError
from .tasks import Task
from .role import AnsibleRole

if TYPE_CHECKING:
    from ..role import Role
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


class RoleLoader:
    def __init__(self, name: str):
        self.ansible_role = AnsibleRole(name=name)
        self.root = os.path.join("roles", name)

    def load_tasks(self):
        tasks_file = os.path.join(self.root, "tasks", "main.yaml")

        try:
            with open(tasks_file, "rt") as fd:
                tasks = yaml.load(fd)
        except FileNotFoundError:
            raise RoleNotFoundError(self.name)

        for task_info in tasks:
            self.ansible_role.tasks.append(Task.create(task_info))

    def load_handlers(self):
        handlers_file = os.path.join(self.root, "handlers", "main.yaml")

        try:
            with open(handlers_file, "rt") as fd:
                handlers = yaml.load(fd)
        except FileNotFoundError:
            return

        for info in handlers:
            h = AnsibleRole(info["name"], with_facts=False)
            h.tasks.append(Task.create(info))
            self.ansible_role.handlers[info["name"]] = h

    def load(self):
        self.load_handlers()
        self.load_tasks()

    def get_role_class(self) -> Type[Role]:
        return self.ansible_role.get_role_class()

    def get_python_code(self) -> str:
        lines = self.ansible_role.get_python_code_module()

        code = "\n".join(lines)
        try:
            from yapf.yapflib import yapf_api
        except ModuleNotFoundError:
            return code
        code, changed = yapf_api.FormatCode(code)
        return code
