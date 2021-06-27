from __future__ import annotations
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Sequence
import os
import re

if TYPE_CHECKING:
    from dataclasses import Field
    from ..role import Role


re_template_start = re.compile(r"{{|{%|{#")
re_single_var = re.compile(r"^{{\s*(\w*)\s*}}$")


class Parameter:
    def list_role_vars(self, role: Role) -> Sequence[str]:
        """
        List the name of template variables used by this parameter
        """
        return ()

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
                if f is not None and f.metadata.get("type") == "local_file":
                    if mo:
                        return ParameterVarFileReference(value)
                    else:
                        return ParameterTemplatedFileReference(value)
                elif f is not None and f.type == "List[str]":
                    if mo:
                        return ParameterVarReferenceStringList(mo.group(1))
                    else:
                        return ParameterTemplatedStringList(value)
                else:
                    if mo:
                        return ParameterVarReference(mo.group(1))
                    else:
                        return ParameterTemplateString(value)
            elif f is not None and f.metadata.get("type") == "local_file":
                return ParameterFileReference(value)
            elif f is not None and f.type == "List[str]":
                return ParameterAny(value.split(','))
            else:
                return ParameterAny(value)
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
        elif isinstance(value, dict):
            elements = {}
            for name, val in value.items():
                elements[name] = cls.create(None, val)
            return ParameterDict(elements)
        else:
            return ParameterAny(value)


class ParameterList(Parameter):
    def __init__(self, parameters: List[Parameter]):
        self.parameters = parameters

    def list_role_vars(self, role: Role) -> Sequence[str]:
        for p in self.parameters:
            yield from p.list_role_vars(role)

    def get_value(self, role: Role):
        return [p.get_value(role) for p in self.parameters]

    def __repr__(self):
        return f"[{', '.join(repr(p) for p in self.parameters)}]"

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "list",
            "value": [p.to_jsonable() for p in self.parameters],
        }


class ParameterDict(Parameter):
    def __init__(self, parameters: Dict[str, Parameter]):
        self.parameters = parameters

    def list_role_vars(self, role: Role) -> Sequence[str]:
        for p in self.parameters.values():
            yield from p.list_role_vars(role)

    def get_value(self, role: Role):
        return {name: p.get_value(role) for name, p in self.parameters.items()}

    def __repr__(self):
        parts = []
        for name, p in self.parameters.items():
            parts.append(f"{name!r}: {p!r}")
        return "{" + ', '.join(parts) + "}"

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "dict",
            "value": [{name, p.to_jsonable()} for name, p in self.parameters.items()],
        }


class ParameterAny(Parameter):
    def __init__(self, value: Any):
        self.value = value

    def get_value(self, role: Role):
        return self.value

    def __repr__(self):
        return repr(self.value)

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "scalar",
            "value": self.value,
        }


class ParameterOctal(ParameterAny):
    def __repr__(self):
        if isinstance(self.value, int):
            return f"0o{self.value:o}"
        else:
            return super().__repr__()

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "octal",
            "value": "0o{self.value:o}" if isinstance(self.value, int) else self.value
        }


class ParameterTemplatedStringList(ParameterAny):
    def list_role_vars(self, role: Role) -> Sequence[str]:
        return role.template_engine.list_string_template_vars(self.value)

    def __repr__(self):
        return f"self.render_string({self.value!r}).split(',')"

    def get_value(self, role: Role):
        return role.render_string(self.value).split(',')

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "templated_string_list",
            "value": self.value
        }


class ParameterVarReferenceStringList(ParameterAny):
    def list_role_vars(self, role: Role) -> Sequence[str]:
        yield self.value

    def __repr__(self):
        return f"self.{self.value}.split(',')"

    def get_value(self, role: Role):
        return getattr(role, self.value).split(',')

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "var_reference_string_list",
            "value": self.value
        }


class ParameterTemplatePath(ParameterAny):
    def list_role_vars(self, role: Role) -> Sequence[str]:
        yield from role.template_engine.list_file_template_vars(os.path.join("templates", self.value))

    def __repr__(self):
        path = os.path.join("templates", self.value)
        return f"self.render_file({path!r})"

    def get_value(self, role: Role):
        path = os.path.join("templates", self.value)
        return role.render_file(path)

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "template_path",
            "value": self.value
        }


class ParameterVarReference(ParameterAny):
    def list_role_vars(self, role: Role) -> Sequence[str]:
        yield self.value

    def __repr__(self):
        return f"self.{self.value}"

    def get_value(self, role: Role):
        return getattr(role, self.value)

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "var_reference",
            "value": self.value
        }


class ParameterTemplateString(ParameterAny):
    def list_role_vars(self, role: Role) -> Sequence[str]:
        return role.template_engine.list_string_template_vars(self.value)

    def __repr__(self):
        return f"self.render_string({self.value!r})"

    def get_value(self, role: Role):
        return role.render_string(self.value)

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "template_string",
            "value": self.value
        }


class ParameterVarFileReference(ParameterAny):
    def list_role_vars(self, role: Role) -> Sequence[str]:
        yield self.value

    def __repr__(self):
        return f"self.lookup_file(os.path.join('files', self.{self.value}))"

    def get_value(self, role: Role):
        return role.lookup_file(os.path.join("files", getattr(role, self.value)))

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "var_file_reference",
            "value": self.value
        }


class ParameterTemplatedFileReference(ParameterAny):
    def list_role_vars(self, role: Role) -> Sequence[str]:
        return role.template_engine.list_string_template_vars(self.value)

    def __repr__(self):
        return f"self.lookup_file(os.path.join('files', self.render_string({self.value!r})))"

    def get_value(self, role: Role):
        return role.lookup_file(os.path.join("files", role.render_string(self.value)))

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "templated_file_reference",
            "value": self.value
        }


class ParameterFileReference(ParameterAny):
    def __repr__(self):
        return f"self.lookup_file(os.path.join('files', {self.value!r}))"

    def get_value(self, role: Role):
        return role.lookup_file(os.path.join("files", self.value))

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "parameter",
            "type": "file_reference",
            "value": self.value
        }
