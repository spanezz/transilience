from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass
from .action import Action
from . import builtin

if TYPE_CHECKING:
    import transilience.system


@builtin.action(name="noop")
@dataclass
class Noop(Action):
    """
    Do nothing, successfully
    """
    changed: bool = False

    def summary(self):
        return "Do nothing"

    def run(self, system: transilience.system.System):
        super().run(system)
        if self.changed:
            self.set_changed()


@builtin.action(name="fail")
@dataclass
class Fail(Action):
    """
    Fail with a custom message
    """
    msg: str = "Failed as requested from task"

    def summary(self):
        return f"Fail: {self.msg}"

    def run(self, system: transilience.system.System):
        super().run(system)
        raise RuntimeError(self.msg)
