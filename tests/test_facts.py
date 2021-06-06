from __future__ import annotations
import unittest
import platform
from transilience.unittest import LocalTestMixin
from transilience.actions import facts


class TestFacts(LocalTestMixin, unittest.TestCase):
    def load_facts(self, facts_cls):
        res = list(self.system.run_actions([facts_cls(name="gather_facts")]))
        self.assertEqual(len(res), 1)
        self.assertIsInstance(res[0], facts_cls)
        self.assertFalse(res[0].changed)
        return res[0].facts

    def test_platform(self):
        res = self.load_facts(facts.Platform)
        self.assertEqual(res["system"], platform.system())
