from __future__ import annotations
from typing import TYPE_CHECKING, Dict
from ..actions import ResultState


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
        self.states: Dict[str, str] = {}


class LocalPipelineMixin:
    """
    Common functions to execute actions locally as part of a pipeline
    """
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
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

    def pipeline_clear_failed(self, pipeline_id: str):
        """
        Clear the 'failed' status of a pipeline.

        After this method runs, actions will start being executed again even if
        an action previously failed
        """
        pipeline = self.get_pipeline(pipeline_id)
        pipeline.failed = False

    def pipeline_close(self, pipeline_id: str):
        """
        Dicard state about a pipeline.

        Call this method to cleanup internal state when a pipeline is done
        executing
        """
        self.pipelines.pop(pipeline_id, None)

    def execute_pipelined(self, action: Action, pipeline_info: PipelineInfo) -> Action:
        """
        Execute the action locally, returning its result immediately.

        It keeps pipeline metadata into account, and it can choose to skip the
        action or fail it instead of running it.
        """
        pipeline = self.get_pipeline(pipeline_info.id)

        # Skip if a previous action failed
        if pipeline.failed:
            with action.result.collect():
                action.action_run_pipeline_failed(self)
            pipeline.states[action.uuid] = action.result.state
            return action

        # Check "when" conditions
        for act_uuid, states in pipeline_info.when.items():
            state = pipeline.states.get(act_uuid)
            if state is None or state not in states:
                with action.result.collect():
                    action.action_run_pipeline_skipped(self, "pipeline condition not met")
                pipeline.states[action.uuid] = action.result.state
                return action

        # Execute
        try:
            act = self.execute(action)
        except Exception:
            # Ignore any exception here. They'll be recorded in the action
            # result, and we later check that to fail the pipeline if they
            # happened
            act = action

        if act.result.state == ResultState.FAILED:
            pipeline.failed = True
        pipeline.states[act.uuid] = act.result.state
        return act
