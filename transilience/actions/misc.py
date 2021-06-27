from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass
from .action import Action, scalar
from . import builtin

if TYPE_CHECKING:
    import transilience.system


@builtin.action(name="noop")
@dataclass
class Noop(Action):
    """
    Do nothing, successfully.
    """
    changed: bool = scalar(False, "Set to True to pretend the action performed changes")

    def action_summary(self):
        return "Do nothing"

    def action_run(self, system: transilience.system.System):
        super().action_run(system)
        if self.changed:
            self.set_changed()


@builtin.action(name="fail")
@dataclass
class Fail(Action):
    """
    Fail with a custom message

    Same as Ansible's
    [builtin.fail](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/fail_module.html).
    """
    msg: str = "Failed as requested from task"

    def action_summary(self):
        return f"Fail: {self.msg}"

    def action_run(self, system: transilience.system.System):
        super().action_run(system)
        raise RuntimeError(self.msg)
