from __future__ import annotations
from typing import Union, Type
import unittest
from transilience.actions import ResultState, builtin
from transilience.actions.misc import Noop
from transilience.system import PipelineInfo
from transilience.role import Role
from transilience.runner import PendingAction


class MockRunner:
    def __init__(self):
        self.pending = []
        self.template_engine = None

    def add_role(self, role_cls: Union[str, Type[Role]], **kw):
        name = role_cls.__name__
        role = role_cls(**kw)
        role.name = name
        role.set_runner(self)
        role.start()
        return role

    def add_pending_action(self, pending: PendingAction, pipeline_info: PipelineInfo):
        self.pending.append((pending, pipeline_info))


class TestRole(unittest.TestCase):
    def test_add_simple(self):
        class TestRole(Role):
            def start(self):
                self.add(builtin.noop())

        runner = MockRunner()
        role = runner.add_role(TestRole)
        self.assertEqual(len(runner.pending), 1)
        pa, pi = runner.pending[0]
        self.assertIsInstance(pa.action, Noop)
        self.assertIsNone(pa.name)
        self.assertEqual(pa.notify, [])
        self.assertEqual(pa.then, [])
        self.assertEqual(pi.id, role.uuid)

    def test_add_named(self):
        class TestRole(Role):
            def start(self):
                self.add(builtin.noop(), name="test")

        runner = MockRunner()
        role = runner.add_role(TestRole)
        self.assertEqual(len(runner.pending), 1)
        pa, pi = runner.pending[0]
        self.assertIsInstance(pa.action, Noop)
        self.assertEqual(pa.name, "test")
        self.assertEqual(pa.notify, [])
        self.assertEqual(pa.then, [])
        self.assertEqual(pi.id, role.uuid)

    def test_add_notify(self):
        class TestRole(Role):
            def start(self):
                self.add(builtin.noop(), notify=[TestRole])

        runner = MockRunner()
        role = runner.add_role(TestRole)
        self.assertEqual(len(runner.pending), 1)
        pa, pi = runner.pending[0]
        self.assertIsInstance(pa.action, Noop)
        self.assertIsNone(pa.name)
        self.assertEqual(pa.notify, [TestRole])
        self.assertEqual(pa.then, [])
        self.assertEqual(pi.id, role.uuid)

    def test_add_notify_with(self):
        class TestRole(Role):
            def start(self):
                with self.notify(TestRole):
                    self.add(builtin.noop(), notify=[Role])

        runner = MockRunner()
        role = runner.add_role(TestRole)
        self.assertEqual(len(runner.pending), 1)
        pa, pi = runner.pending[0]
        self.assertIsInstance(pa.action, Noop)
        self.assertIsNone(pa.name)
        self.assertEqual(pa.notify, [TestRole, Role])
        self.assertEqual(pa.then, [])
        self.assertEqual(pi.id, role.uuid)

    def test_add_when(self):
        class TestRole(Role):
            def start(self):
                a = self.add(builtin.noop())
                self.add(builtin.noop(), when={a: ResultState.CHANGED})

        runner = MockRunner()
        runner.add_role(TestRole)
        self.assertEqual(len(runner.pending), 2)
        pa, pi = runner.pending[1]
        self.assertIsInstance(pa.action, Noop)
        self.assertIsNone(pa.name)
        self.assertEqual(pa.notify, [])
        self.assertEqual(pa.then, [])
        self.assertEqual(pi.when, {runner.pending[0][0].action.uuid: [ResultState.CHANGED]})

    def test_add_when_with(self):
        class TestRole(Role):
            def start(self):
                a = self.add(builtin.noop())
                with self.when({a: ResultState.CHANGED}):
                    self.add(builtin.noop())

        runner = MockRunner()
        runner.add_role(TestRole)
        self.assertEqual(len(runner.pending), 2)
        pa, pi = runner.pending[1]
        self.assertIsInstance(pa.action, Noop)
        self.assertIsNone(pa.name)
        self.assertEqual(pa.notify, [])
        self.assertEqual(pa.then, [])
        self.assertEqual(pi.when, {runner.pending[0][0].action.uuid: [ResultState.CHANGED]})


class TestFacts(unittest.TestCase):
    pass
