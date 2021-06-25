from __future__ import annotations
from typing import TYPE_CHECKING, Type, Dict, Any, Optional, Callable, Sequence
from dataclasses import fields
import shlex
from ..actions import builtin
from ..role import Role
from .parameters import Parameter, ParameterTemplatePath
from .exceptions import RoleNotLoadedError

if TYPE_CHECKING:
    from dataclasses import Field
    from ..actions import Action
    YamlDict = Dict[str, Any]


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

    def list_role_vars(self, role: Role) -> Sequence[str]:
        """
        List the names of role variables used by this task
        """
        for p in self.parameters.values():
            yield from p.list_role_vars(role)

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
