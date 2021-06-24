from __future__ import annotations
from typing import TYPE_CHECKING, Type, Dict, Any, List, Optional, Callable
from dataclasses import fields
import shlex
import re
import os
import yaml
from ..actions import builtin, facts
from ..role import Role, with_facts
from .parameters import Parameter, ParameterTemplatePath

if TYPE_CHECKING:
    from dataclasses import Field
    from ..actions import Action
    YamlDict = Dict[str, Any]

# Currently supported:
#  - actions in Transilience's builtin.* namespace
#  - arguments not supported by the Transilience action are detected and raise an exception
#  - template action (without block_start_string, block_end_string,
#    lstrip_blocks, newline_sequence, output_encoding, trim_blocks, validate,
#    variable_end_string, variable_start_string)
#  - jinja templates in string parameters (not yet in strings contained inside
#    lists and dicts)
#  - variables from facts provided by transilience.actions.facts.Platform
#  - notify/handlers if defined inside thet same role (cannot notify
#    handlers from other roles)


class RoleNotFoundError(Exception):
    pass


class RoleNotLoadedError(Exception):
    pass


class Task:
    """
    Information extracted from a task in an Ansible playbook
    """
    def __init__(self, action_cls: Type[Action], args: YamlDict, task_info: YamlDict, transilience_name: str):
        self.action_cls = action_cls
        self.parameters: Dict[str, Parameter] = {}
        self.task_info = task_info
        self.transilience_name = transilience_name

        # Build parameter list
        for f in fields(self.action_cls):
            value = args.pop(f.name, None)
            if value is None:
                continue
            self.parameters[f.name] = self.make_parameter(f, value)

        if args:
            raise RoleNotLoadedError(f"Task {task_info!r} has unrecognized parameters {args!r}")

    def make_parameter(self, f: Field, value: Any):
        return Parameter.create(f, value)

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

        if name == "template":
            return TaskTemplate(args, task_info)
        else:
            action_cls = getattr(builtin, name, None)
            if action_cls is None:
                raise RoleNotLoadedError(f"Action builtin.{name} not available in Transilience")

            transilience_name = f"builtin.{name}"

            return cls(action_cls, args, task_info, transilience_name)

    def get_start_func(self, handlers: Optional[Dict[str, Callable[[], None]]] = None):
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
            args = {name: p.get_value(role) for name, p in self.parameters.items()}
            role.add(self.action_cls(**args), name=self.task_info.get("name"), notify=notify_classes)
        return starter

    def get_python(self, handlers: Optional[Dict[str, str]] = None) -> str:
        if handlers is None:
            handlers = {}

        fmt_args = []
        for name, parm in self.parameters.items():
            fmt_args.append(f"{name}={parm!r}")
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


class TaskTemplate(Task):
    def __init__(self, args: YamlDict, task_info: YamlDict):
        super().__init__(builtin.copy, args, task_info, "builtin.copy")

    def make_parameter(self, f: Field, value: Any):
        if f.name == "src":
            return ParameterTemplatePath(value)
        else:
            return super().make_parameter(f, value)


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
