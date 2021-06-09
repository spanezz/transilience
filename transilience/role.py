from __future__ import annotations
from typing import TYPE_CHECKING, Sequence, Optional
from transilience import actions

if TYPE_CHECKING:
    from .runner import Runner


class Role:
    def __init__(self):
        self.name: Optional[str] = None
        self.template_engine = None
        self.runner: "Runner" = None

    def set_runner(self, runner: "Runner"):
        self.runner = runner
        self.template_engine = runner.template_engine

    def start_chain(self, chain: Sequence[actions.Action]):
        self.runner.enqueue_chain(self, chain)

    def main(self):
        raise NotImplementedError(f"{self.__class__}.start not implemented")

    def notify_done(self, action: actions.Action):
        pass
