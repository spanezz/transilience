from __future__ import annotations
import unittest
import platform
from transilience.unittest import LocalTestMixin
from transilience.actions import facts, ResultState


class TestFacts(LocalTestMixin, unittest.TestCase):
    def load_facts(self, facts_cls):
        res = list(self.system.run_actions([facts_cls()]))
        self.assertEqual(len(res), 1)
        self.assertIsInstance(res[0], facts_cls)
        self.assertEqual(res[0].result.state, ResultState.NOOP)
        return res[0]

    def test_platform(self):
        res = self.load_facts(facts.Platform)
        self.assertEqual(res.ansible_system, platform.system())
