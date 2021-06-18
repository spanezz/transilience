from __future__ import annotations
from typing import Sequence, Generator, BinaryIO, Optional
import collections
import shutil
import uuid
from .. import actions
from .system import System, PipelineInfo
from .pipeline import LocalPipelineMixin


class LocalExecuteMixin:
    """
    System implementation to execute actions locally
    """
    def execute(self, action: actions.Action) -> actions.Action:
        with action.result.collect():
            action.run(self)
        return action


class Local(LocalExecuteMixin, LocalPipelineMixin, System):
    """
    Work on the local system
    """
    def __init__(self, name: Optional[str] = None):
        if name is None:
            name = "local"
        super().__init__(name)
        self.pending_actions = collections.deque()

    def transfer_file(self, src: str, dst: BinaryIO, **kw):
        """
        Fetch file ``src`` from the controller and write it to the open
        file descriptor ``dst``.
        """
        with open(src, "rb") as fd:
            shutil.copyfileobj(fd, dst)

    def run_actions(self, action_list: Sequence[actions.Action]) -> Generator[actions.Action, None, None]:
        """
        Run a sequence of provisioning actions in the chroot
        """
        pipeline = PipelineInfo(str(uuid.uuid4()))
        for act in action_list:
            yield self.execute_pipelined(act, pipeline)

    def send_pipelined(self, action: actions.Action, pipeline_info: PipelineInfo):
        """
        Execute this action as part of a pipeline
        """
        self.pending_actions.append((action, pipeline_info))

    def receive_pipelined(self) -> Generator[actions.Action, None, None]:
        """
        Receive results of the actions that have been sent so far.

        It is ok to enqueue new actions while this method runs
        """
        while self.pending_actions:
            yield self.execute_pipelined(*self.pending_actions.popleft())
