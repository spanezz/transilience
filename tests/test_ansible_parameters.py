from __future__ import annotations
from typing import Dict, Any, ContextManager
from contextlib import contextmanager
from unittest import TestCase
import tempfile
import os
from transilience.ansible import parameters
from transilience.template import Engine


class MockRole:
    def __init__(self, **role_vars: Dict[str, Any]):
        self.vars = role_vars
        for k, v in role_vars.items():
            setattr(self, k, v)
        self.template_engine = Engine()
        self.lookup_file_path = None

    def render_string(self, value: str) -> str:
        return self.template_engine.render_string(value, self.vars)

    def render_file(self, path: str) -> str:
        return self.template_engine.render_file(path, self.vars)

    def lookup_file(self, path: str) -> str:
        if self.lookup_file_path is None:
            return path
        else:
            return self.lookup_file_path

    @contextmanager
    def template(self, contents: str) -> ContextManager[str]:
        old_engine = self.template_engine
        with tempfile.TemporaryDirectory() as workdir:
            tpl_dir = os.path.join(workdir, "templates")
            os.makedirs(tpl_dir)
            tpl_file = os.path.join(tpl_dir, "tmp.html")
            with open(tpl_file, "wt") as fd:
                fd.write(contents)
            try:
                self.template_engine = Engine([workdir])
                self.lookup_file_path = workdir
                yield "tmp.html"
            finally:
                self.template_engine = old_engine
                self.lookup_file_path = None


class TestParameters(TestCase):
    def test_any(self):
        role = MockRole()
        P = parameters.ParameterAny

        for value in (None, "string", 123, 0o123, [1, 2, 3], {"a": "b"}):
            p = P(value)
            self.assertEqual(repr(p), repr(value))
            self.assertEqual(p.get_value(None), value)
            self.assertEqual(list(p.list_role_vars(role)), [])

    def test_octal(self):
        role = MockRole()
        P = parameters.ParameterOctal

        p = P(None)
        self.assertEqual(repr(p), "None")
        self.assertEqual(p.get_value(None), None)
        self.assertEqual(list(p.list_role_vars(role)), [])

        p = P("ugo+rx")
        self.assertEqual(repr(p), "'ugo+rx'")
        self.assertEqual(p.get_value(None), "ugo+rx")
        self.assertEqual(list(p.list_role_vars(role)), [])

        p = P(0o755)
        self.assertEqual(repr(p), "0o755")
        self.assertEqual(p.get_value(None), 0o755)
        self.assertEqual(list(p.list_role_vars(role)), [])

    def test_templated_string_list(self):
        role = MockRole(b="rendered")
        P = parameters.ParameterTemplatedStringList

        p = P("a,{{b}},c")
        self.assertEqual(repr(p), "self.render_string('a,{{b}},c').split(',')")
        self.assertEqual(p.get_value(role), ["a", "rendered", "c"])
        self.assertEqual(set(p.list_role_vars(role)), {"b"})

    def test_var_reference_string_list(self):
        role = MockRole(varname="a,b,c")
        P = parameters.ParameterVarReferenceStringList

        p = P("varname")
        self.assertEqual(repr(p), "self.varname.split(',')")
        self.assertEqual(p.get_value(role), ["a", "b", "c"])
        self.assertEqual(set(p.list_role_vars(role)), {"varname"})

    def test_template_path(self):
        role = MockRole(b="rendered")
        P = parameters.ParameterTemplatePath

        with role.template("test:{{b}}") as fname:
            p = P(fname)
            self.assertEqual(repr(p), f"self.render_file('templates/{fname}')")
            self.assertEqual(p.get_value(role), "test:rendered")
            self.assertEqual(set(p.list_role_vars(role)), {"b"})

    def test_var_reference(self):
        role = MockRole(varname="a,b,c")
        P = parameters.ParameterVarReference

        p = P("varname")
        self.assertEqual(repr(p), "self.varname")
        self.assertEqual(p.get_value(role), "a,b,c")
        self.assertEqual(set(p.list_role_vars(role)), {"varname"})

    def test_template_string(self):
        role = MockRole(b="rendered")
        P = parameters.ParameterTemplateString

        p = P("a,{{b}},c")
        self.assertEqual(repr(p), "self.render_string('a,{{b}},c')")
        self.assertEqual(p.get_value(role), "a,rendered,c")
        self.assertEqual(set(p.list_role_vars(role)), {"b"})

    def test_parameter_list(self):
        role = MockRole(b="rendered")
        p = parameters.ParameterList([
            parameters.ParameterAny("foo"),
            parameters.ParameterOctal(0o644),
            parameters.ParameterTemplatedStringList("a,{{b}}"),
            parameters.ParameterVarReference("b"),
            parameters.ParameterList([
                parameters.ParameterAny("bar"),
                parameters.ParameterAny(32),
                parameters.ParameterAny(False),
            ]),
        ])

        self.assertEqual(
                repr(p), "['foo', 0o644, self.render_string('a,{{b}}').split(','), self.b, ['bar', 32, False]]")
        self.assertEqual(p.get_value(role), ['foo', 0o644, ['a', 'rendered'], 'rendered', ['bar', 32, False]])
        self.assertEqual(set(p.list_role_vars(role)), {"b"})

    def test_parameter_dict(self):
        role = MockRole(b="rendered")
        p = parameters.ParameterDict({
            "a": parameters.ParameterAny("foo"),
            "b": parameters.ParameterOctal(0o644),
            "c": parameters.ParameterTemplatedStringList("a,{{b}}"),
            "d": parameters.ParameterVarReference("b"),
            "e": parameters.ParameterList([
                    parameters.ParameterAny("bar"),
                    parameters.ParameterAny(32),
                    parameters.ParameterAny(False),
                 ]),
        })

        self.assertEqual(
                repr(p),
                "{'a': 'foo', 'b': 0o644, 'c': self.render_string('a,{{b}}').split(','),"
                " 'd': self.b, 'e': ['bar', 32, False]}")
        self.assertEqual(p.get_value(role), {
            'a': 'foo',
            'b': 0o644,
            'c': ['a', 'rendered'],
            'd': 'rendered',
            'e': ['bar', 32, False],
        })
        self.assertEqual(set(p.list_role_vars(role)), {"b"})
