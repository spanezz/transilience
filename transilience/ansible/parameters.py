from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional, List
import os
import re

if TYPE_CHECKING:
    from dataclasses import Field
    from ..role import Role


re_template_start = re.compile(r"{{|{%|{#")
re_single_var = re.compile(r"^{{\s*(\w*)\s*}}$")


class Parameter:
    @classmethod
    def create(cls, f: Optional[Field], value: Any):
        if isinstance(value, str):
            # Hook for templated strings
            #
            # For reference, Jinja2 template detection in Ansible is in
            # template/__init__.py look for Templar.is_possibly_template,
            # Templar.is_template, and is_template
            if re_template_start.search(value):
                mo = re_single_var.match(value)
                if f is not None and f.type == "List[str]":
                    if mo:
                        return ParameterVarReferenceStringList(mo.group(1))
                    else:
                        return ParameterTemplatedStringList(value)
                else:
                    if mo:
                        return ParameterVarReference(mo.group(1))
                    else:
                        return ParameterTemplateString(value)
            elif f.type == "List[str]":
                return ParameterAny(value.split(','))
        elif isinstance(value, int):
            if f.metadata.get("octal"):
                return ParameterOctal(value)
            else:
                return ParameterAny(value)
        elif isinstance(value, list):
            elements = []
            for val in value:
                elements.append(cls.create(None, val))
            return ParameterList(elements)
        else:
            return ParameterAny(value)


class ParameterList(Parameter):
    def __init__(self, parameters: List[Parameter]):
        self.parameters = parameters

    def get_value(self, role: Role):
        return list(p.get_value(role) for p in self.parameters)

    def __repr__(self):
        return f"[{', '.join(repr(p) for p in self.parameters)}]"


class ParameterAny(Parameter):
    def __init__(self, value: Any):
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
            return super().__repr__()


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
