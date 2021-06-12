from __future__ import annotations
from typing import TYPE_CHECKING, Dict


if TYPE_CHECKING:
    from ..actions import Action
    from .system import PipelineInfo


class Pipeline:
    """
    State about a pipeline
    """
    def __init__(self, id: str):
        self.id = id
        self.failed = False


class LocalPipelineMixin:
    """
    Common functions to execute actions locally as part of a pipeline
    """
    def __init__(self):
        super().__init__()
        self.pipelines: Dict[str, Pipeline] = {}

    def get_pipeline(self, pipeline_id: str) -> Pipeline:
        """
        Create or retrieve a pipeline object for the given pipeline id
        """
        res = self.pipelines.get(pipeline_id)
        if res is None:
            res = Pipeline(pipeline_id)
            self.pipelines[pipeline_id] = res
        return res

    def execute_pipelined(self, action: Action, pipeline: PipelineInfo) -> Action:
        """
        Execute the action locally, returning its result immediately.

        It keeps pipeline metadata into account, and it can choose to skip the
        action or fail it instead of running it.
        """
        pipeline = self.get_pipeline(pipeline.id)

        if pipeline.failed:
            raise RuntimeError("Action aborted because a previous action failed in the same pipeline")

        try:
            return self.execute(action)
        except Exception:
            pipeline.failed = True
            raise
