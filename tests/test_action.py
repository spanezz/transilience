from __future__ import annotations
from dataclasses import dataclass
import unittest
import json
from transilience.actions import Action, builtin


class TestAction(unittest.TestCase):
    def test_serialize_json(self):
        act = builtin.copy(content="'\"♥\x00".encode(), dest="/tmp/test")
        encoded = json.dumps(act.serialize_for_json())

        dec = Action.deserialize_from_json(json.loads(encoded))

        self.assertEqual(dec.content, act.content)
