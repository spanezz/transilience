from __future__ import annotations
from unittest import TestCase
from transilience.ansible.conditionals import Conditional
from transilience import template


class TestConditionals(TestCase):
    def setUp(self):
        super().setUp()
        self.engine = template.Engine()

    def test_var(self):
        c = Conditional(self.engine, "varname")
        self.assertEqual(c.list_role_vars(), set(("varname",)))
        self.assertEqual(c.evaluate({"varname": 3}), 3)
        self.assertIsNone(c.evaluate({"varname": None}))
        self.assertEqual(c.get_python_code(), "self.varname")

    def test_defined(self):
        c = Conditional(self.engine, "varname is defined")
        self.assertEqual(c.list_role_vars(), set(("varname",)))
        self.assertFalse(c.evaluate({}))
        self.assertFalse(c.evaluate({"varname": None}))
        self.assertTrue(c.evaluate({"varname": True}))
        self.assertTrue(c.evaluate({"varname": 0}))
        self.assertEqual(c.get_python_code(), "self.varname is not None")

        c = Conditional(self.engine, "varname is not defined")
        self.assertEqual(c.list_role_vars(), set(("varname",)))
        self.assertTrue(c.evaluate({}))
        self.assertTrue(c.evaluate({"varname": None}))
        self.assertFalse(c.evaluate({"varname": True}))
        self.assertFalse(c.evaluate({"varname": False}))
        self.assertFalse(c.evaluate({"varname": 0}))
        self.assertEqual(c.get_python_code(), "self.varname is None")

        c = Conditional(self.engine, "varname is not defined or not varname")
        self.assertEqual(c.list_role_vars(), set(("varname",)))
        self.assertTrue(c.evaluate({}))
        self.assertTrue(c.evaluate({"varname": None}))
        self.assertTrue(c.evaluate({"varname": False}))
        self.assertTrue(c.evaluate({"varname": 0}))
        self.assertFalse(c.evaluate({"varname": True}))
        self.assertEqual(c.get_python_code(), "(self.varname is None or not self.varname)")

    def test_undefined(self):
        c = Conditional(self.engine, "varname is undefined")
        self.assertEqual(c.list_role_vars(), set(("varname",)))
        self.assertTrue(c.evaluate({}))
        self.assertTrue(c.evaluate({"varname": None}))
        self.assertFalse(c.evaluate({"varname": True}))
        self.assertFalse(c.evaluate({"varname": 0}))
        self.assertEqual(c.get_python_code(), "self.varname is None")

        c = Conditional(self.engine, "varname is not undefined")
        self.assertEqual(c.list_role_vars(), set(("varname",)))
        self.assertFalse(c.evaluate({}))
        self.assertFalse(c.evaluate({"varname": None}))
        self.assertTrue(c.evaluate({"varname": True}))
        self.assertTrue(c.evaluate({"varname": False}))
        self.assertTrue(c.evaluate({"varname": 0}))
        self.assertEqual(c.get_python_code(), "self.varname is not None")

        c = Conditional(self.engine, "varname is not undefined and varname")
        self.assertEqual(c.list_role_vars(), set(("varname",)))
        self.assertFalse(c.evaluate({}))
        self.assertFalse(c.evaluate({"varname": None}))
        self.assertFalse(c.evaluate({"varname": False}))
        self.assertFalse(c.evaluate({"varname": 0}))
        self.assertTrue(c.evaluate({"varname": True}))
        self.assertEqual(c.get_python_code(), "(self.varname is not None and self.varname)")
