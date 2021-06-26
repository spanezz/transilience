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
    from .conditionals import Conditional
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
        self.conditionals: List[Conditional] = []

        # Build parameter list
        for f in fields(self.action_cls):
            value = args.pop(f.name, None)
            if value is None:
                continue
            self.add_parameter(f, value)

        if args:
            raise RoleNotLoadedError(f"Task {task_info!r} has unrecognized parameters {args!r}")

    def add_parameter(self, f: Field, value: Any):
        self.parameters[f.name] = Parameter.create(f, value)

    def list_role_vars(self, role: Role) -> Sequence[str]:
        """
        List the names of role variables used by this task
        """
        for p in self.parameters.values():
            yield from p.list_role_vars(role)
        for c in self.conditionals:
            yield from c.list_role_vars()

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "task",
            "action": self.transilience_name,
            "parameters": {name: p.to_jsonable() for name, p in self.parameters.items()},
            "ansible_yaml": self.task_info,
            "notify": [h.get_python_name() for h in self.notify],
            "conditionals": [c.to_jsonable() for c in self.conditionals],
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

    def get_python(self, handlers: Optional[Dict[str, str]] = None) -> List[str]:
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

        lines = []
        if self.conditionals:
            if len(self.conditionals) > 1:
                lines.append(f"if {' and '.join(c.get_python_code() for c in self.conditionals)}:")
            else:
                lines.append(f"if {self.conditionals[0].get_python_code()}:")
            lines.append(f"    self.add({', '.join(add_args)})")
        else:
            lines.append(f"self.add({', '.join(add_args)})")

        return lines


class TaskTemplate(Task):
    """
    Task that maps ansible.builtin.template module to a Transilince
    builtin.copy action, plus template rendering on the Role's side
    """
    def __init__(self, args: YamlDict, task_info: YamlDict):
        super().__init__(builtin.copy, args, task_info, "builtin.copy")

    def add_parameter(self, f: Field, value: Any):
        if f.name == "src":
            # TODO: rename in contents
            self.parameters["content"] = ParameterTemplatePath(value)
        else:
            super().add_parameter(f, value)
