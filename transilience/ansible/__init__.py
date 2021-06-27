from __future__ import annotations
from typing import TYPE_CHECKING, Type, Dict, Any
import zipfile
import os
import yaml
from .exceptions import RoleNotFoundError
from .role import AnsibleRoleFilesystem, AnsibleRoleZip

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
#  - when: expressions with:
#     - variable references
#     - is defined
#     - is undefined
#     - not
#     - and
#     - or


class RoleLoader:
    def load_parsed_tasks(self, tasks: YamlDict):
        for task_info in tasks:
            self.ansible_role.add_task(task_info)

    def load_parsed_handlers(self, handlers: YamlDict):
        for info in handlers:
            h = AnsibleRoleFilesystem(info["name"], root=self.root, uses_facts=False)
            h.add_task(info)
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


class FilesystemRoleLoader(RoleLoader):
    def __init__(self, name: str, roles_root: str = "roles"):
        super().__init__()
        self.root = os.path.join(roles_root, name)
        # TODO: make something to create a subrole from self.ansible_role
        self.ansible_role = AnsibleRoleFilesystem(name=name, root=self.root)

    def load_tasks(self):
        tasks_file = os.path.join(self.root, "tasks", "main.yaml")

        try:
            with open(tasks_file, "rt") as fd:
                tasks = yaml.load(fd)
        except FileNotFoundError:
            raise RoleNotFoundError(self.name)

        self.load_parsed_tasks(tasks)

    def load_handlers(self):
        handlers_file = os.path.join(self.root, "handlers", "main.yaml")

        try:
            with open(handlers_file, "rt") as fd:
                handlers = yaml.load(fd)
        except FileNotFoundError:
            return

        self.load_parsed_handlers(handlers)


class ZipRoleLoader(RoleLoader):
    """
    Load Ansible roles from zip files.

    From Python 3.9 we can replace this with importlib.resources, and have a
    generic loader for both data in zipfiles and data bundled with modules.
    Before Python 3.9, it is hard to deal with resources that are directory
    trees.
    """
    def __init__(self, name: str, path: str):
        super().__init__()
        self.name = name
        self.zipfile = zipfile.ZipFile(path, "r")
        self.ansible_role = AnsibleRoleZip(name=name, zipfile=self.zipfile, root=os.path.join("roles", self.name))

    def load_tasks(self):
        try:
            with self.zipfile.open(os.path.join("roles", self.name, "tasks", "main.yaml"), "r") as fd:
                tasks = yaml.load(fd)
        except KeyError:
            raise RoleNotFoundError(self.name)

        self.load_parsed_tasks(tasks)

    def load_handlers(self):
        try:
            with self.zipfile.open(os.path.join("roles", self.name, "handlers", "main.yaml"), "r") as fd:
                handlers = yaml.load(fd)
        except KeyError:
            return

        self.load_parsed_handlers(handlers)
