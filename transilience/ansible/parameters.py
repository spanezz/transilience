from __future__ import annotations
from typing import TYPE_CHECKING, Any
import os
import re

if TYPE_CHECKING:
    from dataclasses import Field
    from ..role import Role


re_template_start = re.compile(r"{{|{%|{#")
re_single_var = re.compile(r"^{{\s*(\w*)\s*}}$")


class Parameter:
    def __init__(self, name: str):
        self.name = name

    @classmethod
    def create(self, f: Field, value: Any):
        if isinstance(value, str):
            # Hook for templated strings
            #
            # For reference, Jinja2 template detection in Ansible is in
            # template/__init__.py look for Templar.is_possibly_template,
            # Templar.is_template, and is_template
            if re_template_start.search(value):
                mo = re_single_var.match(value)
                if f.type == "List[str]":
                    if mo:
                        return ParameterVarReferenceStringList(f.name, mo.group(1))
                    else:
                        return ParameterTemplatedStringList(f.name, value)
                else:
                    if mo:
                        return ParameterVarReference(f.name, mo.group(1))
                    else:
                        return ParameterTemplateString(f.name, value)
            elif f.type == "List[str]":
                return ParameterAny(f.name, value.split(','))
        elif isinstance(value, int):
            if f.metadata.get("octal"):
                return ParameterOctal(f.name, value)
            else:
                return ParameterAny(f.name, value)
        else:
            return ParameterAny(f.name, value)


class ParameterAny(Parameter):
    def __init__(self, name: str, value: Any):
        super().__init__(name)
        self.value = value

    def get_value(self, role: Role):
        return self.value

    def __repr__(self):
        return repr(self.value)


class ParameterOctal(ParameterAny):
    def __repr__(self):
        if isinstance(self.value, int):
            return f"0o{self.value:o}"
        else:
            super().__repr__()


class ParameterTemplatedStringList(ParameterAny):
    def __repr__(self):
        return f"self.render_string({self.value!r}).split(',')"

    def get_value(self, role: Role):
        return role.render_string(self.value).split(',')


class ParameterVarReferenceStringList(ParameterAny):
    def __repr__(self):
        return f"self.{self.value}.split(',')"

    def get_value(self, role: Role):
        return getattr(role, self.value).split(',')


class ParameterTemplatePath(ParameterAny):
    def __repr__(self):
        path = os.path.join("templates", self.value)
        return f"self.render_file({path!r})"

    def get_value(self, role: Role):
        return role.render_file(os.path.join("templates", self.value))


class ParameterVarReference(ParameterAny):
    def __repr__(self):
        return f"self.{self.value}"

    def get_value(self, role: Role):
        return getattr(role, self.value)


class ParameterTemplateString(ParameterAny):
    def __repr__(self):
        return f"self.render_string({self.value!r})"

    def get_value(self, role: Role):
        return role.render_string(self.value)
