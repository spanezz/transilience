from __future__ import annotations
from typing import TYPE_CHECKING, Type, Dict, Any, List, Optional, Callable
import shlex
import re
import os
import yaml
from .actions import builtin, facts
from .role import Role, with_facts

if TYPE_CHECKING:
    from .action import Action
    YamlDict = Dict[str, Any]


class RoleNotFoundError(Exception):
    pass


class RoleNotLoadedError(Exception):
    pass


class Task:
    def __init__(self, action_cls: Type[Action], args: YamlDict, task_info: YamlDict, transilience_name: str):
        self.action_cls = action_cls
        self.args = args
        self.task_info = task_info
        self.transilience_name = transilience_name

    @classmethod
    def create(cls, task_info: YamlDict):
        candidates = []
        for key in task_info.keys():
            if key in ("name", "args", "notify"):
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

        action_cls = getattr(builtin, name, None)
        if action_cls is None:
            raise RoleNotLoadedError(f"Action builtin.{name} (from {modname}) not available in Transilience")

        transilience_name = f"builtin.{name}"

        if action_cls == builtin.apt:
            # Fixups for apt: in ansible name can be a comma separated string
            if isinstance(args.get("name"), str):
                args["name"] = args["name"].split(',')

        return cls(action_cls, args, task_info, transilience_name)

        # TODO: template
        # TODO: jinja2 markup in string args
        # TODO: file lookup for copy source
        # TODO: role arguments? Vars? (vars from facts are supported)

    def get_start_func(self, handlers: Optional[Dict[str, Callable[None, []]]] = None):
        # If this task calls handlers, fetch the corresponding handler classes
        notify = self.task_info.get("notify")
        if not notify:
            notify_classes = None
        else:
            notify_classes = []
            if isinstance(notify, str):
                notify = [notify]
            for name in notify:
                notify_classes.append(handlers[name])

        def starter(role: Role):
            role.add(self.action_cls(**self.args), name=self.task_info.get("name"), notify=notify_classes)
        return starter

    def get_python(self, handlers: Optional[Dict[str, str]] = None) -> str:
        if handlers is None:
            handlers = {}

        fmt_args = []
        for k, v in self.args.items():
            if k == "mode" and isinstance(v, int):
                fmt_args.append(f"{k}=0o{v:o}")
            else:
                fmt_args.append(f"{k}={v!r}")
        act_args = ", ".join(fmt_args)

        add_args = [
            f"{self.transilience_name}({act_args})",
            f"name={self.task_info['name']!r}"
        ]

        notify = self.task_info.get("notify")
        if notify:
            if isinstance(notify, str):
                notify = [notify]
            notify_classes = []
            for n in notify:
                notify_classes.append(handlers[n])
            if len(notify_classes) == 1:
                add_args.append(f"notify={notify_classes[0]}")
            else:
                add_args.append(f"notify=[{', '.join(notify_classes)}]")

        return f"self.add({', '.join(add_args)})"


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
            role_cls = with_facts(facts.Platform)(role_cls)
        else:
            role_cls = type(self.name, (Role,), {
                "start": role_main
            })

        return role_cls

    def get_python_code_module(self) -> List[str]:
        lines = [
            "from __future__ import annotations",
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
        if self.with_facts:
            lines.append("@role.with_facts([facts.Platform])")

        if name is None:
            name = self.get_python_name()

        lines.append(f"class {name}(role.Role):")

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
