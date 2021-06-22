from __future__ import annotations
from typing import TYPE_CHECKING, Type, Dict, Any
import os
import yaml
import shlex
from .actions import builtin, facts
from .role import Role, with_facts

if TYPE_CHECKING:
    from .action import Action


class RoleNotFoundError(Exception):
    pass


class RoleNotLoadedError(Exception):
    pass


class RoleAction:
    def __init__(self, task: Dict[str, Any]):
        self.task = task
        self.action_cls: Type[Action]

        candidates = []
        for key in task.keys():
            if key in ("name", "args"):
                continue
            candidates.append(key)

        if len(candidates) != 1:
            raise RoleNotLoadedError(f"could not find a known module in task {task!r}")

        modname = candidates[0]
        if modname.startswith("ansible.builtin."):
            name = modname[16:]
            res = getattr(builtin, name, None)
            if res is None:
                raise RoleNotLoadedError(f"Action builtin.{name} (from {modname}) not available in Transilience")
            self.action_cls = res
            self.transilience_name = f"builtin.{name}"
        else:
            res = getattr(builtin, modname, None)
            if res is None:
                raise RoleNotLoadedError(f"Action builtin.{name} not available in Transilience")
            self.action_cls = res
            self.transilience_name = f"builtin.{modname}"

        self.action_args = task[modname]

        if self.action_cls == builtin.command:
            # Fixups for command
            if isinstance(self.action_args, str):
                self.action_args = {"argv": shlex.split(self.action_args)}
            task_args = self.task.get("args")
            if task_args is not None:
                self.action_args.update(task_args)

        # TODO: notify
        # TODO: jinja2 markup in string args
        # TODO: template
        # TODO: file lookup for copy source

    def get_start_func(self):
        def starter(role: Role):
            role.add(self.action_cls(**self.action_args), name=self.task.get("name"))
        return starter

    def get_python(self) -> str:
        fmt_args = []
        for k, v in self.action_args.items():
            if k == "mode" and isinstance(v, int):
                fmt_args.append(f"{k}=0o{v:o}")
            else:
                fmt_args.append(f"{k}={v!r}")
        act_args = ", ".join(fmt_args)

        add_args = [
            f"{self.transilience_name}({act_args})",
            f"name={self.task['name']!r}"
        ]

        return f"self.add({', '.join(add_args)})"


class RoleLoader:
    def __init__(self, name: str):
        self.name = name
        self.root = os.path.join("roles", name)
        self.main_tasks = []

    def load_tasks(self):
        tasks_file = os.path.join(self.root, "tasks", "main.yaml")

        try:
            with open(tasks_file, "rt") as fd:
                tasks = yaml.load(fd)
        except FileNotFoundError:
            raise RoleNotFoundError(self.name)

        for task_info in tasks:
            self.main_tasks.append(RoleAction(task_info))

    def get_role_class(self) -> Type[Role]:
        start_funcs = []
        for role_action in self.main_tasks:
            start_funcs.append(role_action.get_start_func())

        def role_main(self):
            for func in start_funcs:
                func(self)

        role_cls = type(self.name, (Role,), {
            "start": lambda host: None,
            "all_facts_available": role_main
        })
        role_cls = with_facts(facts.Platform)(role_cls)

        return role_cls

    def get_python_code(self) -> str:
        lines = [
            "from __future__ import annotations",
            "from typing import Dict, Any",
            "from dataclasses import field",
            "from transilience import role",
            "from transilience.actions import builtin, facts",
            "",
            "@role.with_facts([facts.Platform])",
            "class Role(role.Role):",
            "    def all_facts_available(self):",
        ]

        for role_action in self.main_tasks:
            lines.append(" " * 8 + role_action.get_python())

        code = "\n".join(lines)

        try:
            from yapf.yapflib import yapf_api
        except ModuleNotFoundError:
            return code
        code, changed = yapf_api.FormatCode(code)
        return code
