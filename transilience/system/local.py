from __future__ import annotations
from typing import Sequence, Generator, BinaryIO
import collections
import shutil
from .. import actions
from . import System, Pipeline


class LocalPipeline(Pipeline):
    """
    Wrap a sequence of actions, so that when one fails, all the following ones
    will fail
    """
    def __init__(self, system: "Local"):
        self.system = system
        self.failed = False

    def add(self, action: actions.Action):
        def wrapped(system: System) -> actions.Action:
            nonlocal action
            if self.failed:
                raise RuntimeError(f"{action.summary()!r} failed because a previous action failed in the same chain")
            try:
                with action.result.collect():
                    action.run(system)
                return action
            except Exception:
                self.failed = True
                raise
        self.system.pending_actions.append(wrapped)

    def reset(self):
        self.failed = False

    def close(self):
        self.failed = False


class Local(System):
    """
    Work on the local system
    """
    def __init__(self):
        super().__init__()
        self.pending_actions = collections.deque()

    def transfer_file(self, src: str, dst: BinaryIO, **kw):
        """
        Fetch file ``src`` from the controller and write it to the open
        file descriptor ``dst``.
        """
        with open(src, "rb") as fd:
            shutil.copyfileobj(fd, dst)

    def create_pipeline(self) -> "Pipeline":
        return LocalPipeline(self)

    def execute(self, action: actions.Action) -> actions.Action:
        action.run(self)
        return action

    def receive_actions(self) -> Generator[actions.Action, None, None]:
        """
        Receive results of the actions that have been sent so far.

        It is ok to enqueue new actions while this method runs
        """
        while self.pending_actions:
            runner = self.pending_actions.popleft()
            yield runner(self)

    def run_actions(self, action_list: Sequence[actions.Action]) -> Generator[actions.Action, None, None]:
        """
        Run a sequence of provisioning actions in the chroot
        """
        with self.create_pipeline() as pipe:
            for act in action_list:
                pipe.add(act)
        yield from self.receive_actions()
