from __future__ import annotations
from dataclasses import dataclass
from .action import Action
from . import builtin


@builtin.action(name="noop")
@dataclass
class Noop(Action):
    """
    Do nothing, successfully
    """
    def summary(self):
        return "Do nothing"
