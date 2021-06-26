from __future__ import annotations
from typing import Union, Type
from dataclasses import dataclass
import unittest
import tempfile
import os
from transilience.actions import ResultState, builtin
from transilience.actions.misc import Noop
from transilience.actions.facts import Facts
from transilience.system import PipelineInfo
from transilience.role import Role, with_facts
from transilience.runner import PendingAction


class MockRunner:
    def __init__(self):
        self.pending = []
        self.template_engine = None

    def add_role(self, role_cls: Union[str, Type[Role]], **kw):
        name = role_cls.__name__
        kw.setdefault("name", name)
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
        r = runner.add_role(TestRole)
        self.assertEqual(len(runner.pending), 1)
        pa, pi = runner.pending[0]
        self.assertIsInstance(pa.action, Noop)
        self.assertIsNone(pa.name)
        self.assertEqual(pa.notify, [])
        self.assertEqual(pa.then, [])
        self.assertEqual(pi.id, r.uuid)

    def test_add_named(self):
        class TestRole(Role):
            def start(self):
                self.add(builtin.noop(), name="test")

        runner = MockRunner()
        r = runner.add_role(TestRole)
        self.assertEqual(len(runner.pending), 1)
        pa, pi = runner.pending[0]
        self.assertIsInstance(pa.action, Noop)
        self.assertEqual(pa.name, "test")
        self.assertEqual(pa.notify, [])
        self.assertEqual(pa.then, [])
        self.assertEqual(pi.id, r.uuid)

    def test_add_notify(self):
        class TestRole(Role):
            def start(self):
                self.add(builtin.noop(), notify=[TestRole])

        runner = MockRunner()
        r = runner.add_role(TestRole)
        self.assertEqual(len(runner.pending), 1)
        pa, pi = runner.pending[0]
        self.assertIsInstance(pa.action, Noop)
        self.assertIsNone(pa.name)
        self.assertEqual(pa.notify, [TestRole])
        self.assertEqual(pa.then, [])
        self.assertEqual(pi.id, r.uuid)

    def test_add_notify_with(self):
        class TestRole(Role):
            def start(self):
                with self.notify(TestRole):
                    self.add(builtin.noop(), notify=[Role])

        runner = MockRunner()
        r = runner.add_role(TestRole)
        self.assertEqual(len(runner.pending), 1)
        pa, pi = runner.pending[0]
        self.assertIsInstance(pa.action, Noop)
        self.assertIsNone(pa.name)
        self.assertEqual(pa.notify, [TestRole, Role])
        self.assertEqual(pa.then, [])
        self.assertEqual(pi.id, r.uuid)

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

    def test_template_paths(self):
        with tempfile.TemporaryDirectory() as workdir:
            template_dir = os.path.join(workdir, "roles", "test", "templates")
            os.makedirs(template_dir)

            with open(os.path.join(template_dir, "tpl.html"), "wt") as fd:
                fd.write("Test: {{testvar}}")

            role = Role(name="test", role_assets_root=os.path.join(workdir, "roles", "test"))

            self.assertEqual(role.render_file("templates/tpl.html", testvar=42), "Test: 42")
            self.assertEqual(role.template_engine.list_file_template_vars("templates/tpl.html"), {"testvar"})


class TestFacts(unittest.TestCase):
    def test_inherit(self):
        @dataclass
        class F1(Facts):
            value1: int = 1

        @dataclass
        class F2(Facts):
            value2: int = 2

        @with_facts(F1)
        class Role1(Role):
            value3: int = 3

        @with_facts(F2)
        class Role2(Role1):
            value4: int = 4

        self.assertEqual(Role2._facts, (F1, F2))
        r = Role2(name="test")
        self.assertEqual(r.value1, 1)
        self.assertEqual(r.value2, 2)
        self.assertEqual(r.value3, 3)
        self.assertEqual(r.value4, 4)

    def test_inherit1(self):
        @dataclass
        class F1(Facts):
            value1: int = 1

        @with_facts(F1)
        class Role1(Role):
            value3: int = 3

        @dataclass
        class Role2(Role1):
            value4: int = 4

        self.assertEqual(Role2._facts, (F1,))
        r = Role2(name="test")
        self.assertEqual(r.value1, 1)
        self.assertEqual(r.value3, 3)
        self.assertEqual(r.value4, 4)

    def test_inherit_unique(self):
        @dataclass
        class F1(Facts):
            value1: int = 1

        @dataclass
        class F2(Facts):
            value2: int = 2

        @with_facts([F1, F2])
        class Role1(Role):
            value3: int = 3

        @with_facts([F2, F1])
        class Role2(Role1):
            value4: int = 4

        self.assertEqual(Role2._facts, (F1, F2))
        r = Role2(name="test")
        self.assertEqual(r.value1, 1)
        self.assertEqual(r.value2, 2)
        self.assertEqual(r.value3, 3)
        self.assertEqual(r.value4, 4)
