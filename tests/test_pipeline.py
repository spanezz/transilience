from __future__ import annotations
import unittest
import uuid
from transilience.actions import ResultState
from transilience.actions.misc import Noop, Fail
from transilience.unittest import LocalTestMixin
from transilience.system import PipelineInfo


class TestPipeline(LocalTestMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.pipeline_id = str(uuid.uuid4())

    def assertNoop(self, expected: str, changed: bool = False, when=None):
        pipeline_info = PipelineInfo(id=self.pipeline_id, when=when if when is not None else {})
        act = self.system.execute_pipelined(Noop(changed=changed), pipeline_info)
        self.assertEqual(act.result.state, expected)
        return act

    def assertFail(self):
        pipeline_info = PipelineInfo(id=self.pipeline_id)
        act = self.system.execute_pipelined(Fail(msg="test"), pipeline_info)
        self.assertEqual(act.result.state, ResultState.FAILED)
        self.assertTrue(self.system.pipelines[self.pipeline_id].failed)
        self.assertNoop(ResultState.SKIPPED)

    def test_fail(self):
        self.assertNoop(ResultState.NOOP)
        self.assertNoop(ResultState.NOOP)
        self.assertNoop(ResultState.NOOP)
        self.assertFail()
        self.assertNoop(ResultState.SKIPPED)
        self.assertNoop(ResultState.SKIPPED)
        self.assertNoop(ResultState.SKIPPED)
        self.system.pipeline_clear_failed(self.pipeline_id)
        self.assertNoop(ResultState.NOOP)
        self.assertNoop(ResultState.NOOP)
        self.assertNoop(ResultState.NOOP)

    def test_when(self):
        n1 = self.assertNoop(ResultState.NOOP, changed=False)
        n2 = self.assertNoop(ResultState.CHANGED, changed=True)
        n3 = self.assertNoop(ResultState.SKIPPED, when={n1.uuid: [ResultState.CHANGED]}, changed=True)
        self.assertNoop(ResultState.CHANGED, when={n1.uuid: [ResultState.NOOP]}, changed=True)
        self.assertNoop(ResultState.CHANGED, when={n2.uuid: [ResultState.CHANGED]}, changed=True)
        self.assertNoop(ResultState.SKIPPED, when={n2.uuid: [ResultState.NOOP]}, changed=True)
        self.assertNoop(ResultState.CHANGED, when={n3.uuid: [ResultState.SKIPPED]}, changed=True)
        self.assertNoop(ResultState.CHANGED, when={n3.uuid: [ResultState.CHANGED, ResultState.SKIPPED]}, changed=True)
        self.assertNoop(ResultState.SKIPPED, when={n3.uuid: [ResultState.NOOP, ResultState.CHANGED]}, changed=True)

        self.system.pipeline_close(self.pipeline_id)
        self.assertNoop(ResultState.SKIPPED, when={n2.uuid: [ResultState.CHANGED]}, changed=True)
