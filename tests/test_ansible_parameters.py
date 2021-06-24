from __future__ import annotations
from typing import Dict, Any
from unittest import TestCase
from functools import partial
from transilience.ansible import parameters
from transilience.template import Engine


class MockRole:
    def __init__(self, **role_vars: Dict[str, Any]):
        self.vars = role_vars
        for k, v in role_vars.items():
            setattr(self, k, v)
        self.template_engine = Engine()

    def render_string(self, value: str):
        return self.template_engine.render_string(value, self.vars)

    def render_file(self, path: str):
        return f"RENDERED:{path}"


class TestParameters(TestCase):
    def test_any(self):
        P = partial(parameters.ParameterAny, "name")

        for value in (None, "string", 123, 0o123, [1, 2, 3], {"a": "b"}):
            p = P(value)
            self.assertEqual(repr(p), repr(value))
            self.assertEqual(p.get_value(None), value)

    def test_octal(self):
        P = partial(parameters.ParameterOctal, "name")

        p = P(None)
        self.assertEqual(repr(p), "None")
        self.assertEqual(p.get_value(None), None)

        p = P("ugo+rx")
        self.assertEqual(repr(p), "'ugo+rx'")
        self.assertEqual(p.get_value(None), "ugo+rx")

        p = P(0o755)
        self.assertEqual(repr(p), "0o755")
        self.assertEqual(p.get_value(None), 0o755)

    def test_templated_string_list(self):
        role = MockRole(b="rendered")
        P = partial(parameters.ParameterTemplatedStringList, "name")

        p = P("a,{{b}},c")
        self.assertEqual(repr(p), "self.render_string('a,{{b}},c').split(',')")
        self.assertEqual(p.get_value(role), ["a", "rendered", "c"])

    def test_var_reference_string_list(self):
        role = MockRole(varname="a,b,c")
        P = partial(parameters.ParameterVarReferenceStringList, "name")

        p = P("varname")
        self.assertEqual(repr(p), "self.varname.split(',')")
        self.assertEqual(p.get_value(role), ["a", "b", "c"])

    def test_template_path(self):
        role = MockRole()
        P = partial(parameters.ParameterTemplatePath, "name")

        p = P("path/file")
        self.assertEqual(repr(p), "self.render_file('templates/path/file')")
        self.assertEqual(p.get_value(role), "RENDERED:templates/path/file")

    def test_var_reference(self):
        role = MockRole(varname="a,b,c")
        P = partial(parameters.ParameterVarReference, "name")

        p = P("varname")
        self.assertEqual(repr(p), "self.varname")
        self.assertEqual(p.get_value(role), "a,b,c")

    def test_template_string(self):
        role = MockRole(b="rendered")
        P = partial(parameters.ParameterTemplateString, "name")

        p = P("a,{{b}},c")
        self.assertEqual(repr(p), "self.render_string('a,{{b}},c')")
        self.assertEqual(p.get_value(role), "a,rendered,c")
