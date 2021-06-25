from __future__ import annotations
from typing import TYPE_CHECKING, Type, Dict, Any, Optional, Callable, Sequence, List
from dataclasses import fields
from ..actions import builtin
from ..role import Role
from .parameters import Parameter, ParameterTemplatePath
from .exceptions import RoleNotLoadedError

if TYPE_CHECKING:
    from dataclasses import Field
    from ..actions import Action
    from .role import AnsibleRole
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
        # List of python names of handler roles notified by this task
        self.notify: List[AnsibleRole] = []

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

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "task",
            "action": self.transilience_name,
            "parameters": {name: p.to_jsonable() for name, p in self.parameters.items()},
            "ansible_yaml": self.task_info,
            "notify": [h.get_python_name() for h in self.notify],
        }

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

        if len(self.notify) == 1:
            add_args.append(f"notify={self.notify[0].get_python_name()}")
        elif len(self.notify) > 1:
            add_args.append(f"notify=[{', '.join(n.get_python_name() for n in self.notify)}]")

        return f"self.add({', '.join(add_args)})"


class TaskTemplate(Task):
    """
    Task that maps ansible.builtin.template module to a Transilince
    builtin.copy action, plus template rendering on the Role's side
    """
    def __init__(self, args: YamlDict, task_info: YamlDict):
        super().__init__(builtin.copy, args, task_info, "builtin.copy")

    def make_parameter(self, f: Field, value: Any):
        if f.name == "src":
            return ParameterTemplatePath(value)
        else:
            return super().make_parameter(f, value)
