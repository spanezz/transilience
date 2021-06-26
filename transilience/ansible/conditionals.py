from __future__ import annotations
from typing import TYPE_CHECKING, Sequence, Callable, Dict, Any, Set
import jinja2.parser
import jinja2.meta
import jinja2.visitor
from jinja2 import nodes

if TYPE_CHECKING:
    from .. import template


class FindVars(jinja2.visitor.NodeVisitor):
    def __init__(self):
        self.found: Set[str] = set()

    def visit_Name(self, node):
        if node.ctx == "load":
            self.found.add(node.name)


def to_python_code(node: nodes.Node) -> str:
    if isinstance(node, nodes.Name):
        if node.ctx == "load":
            return f"self.{node.name}"
        else:
            raise NotImplementedError(f"jinja2 Name nodes with ctx={node.ctx!r} are not supported: {node!r}")
    elif isinstance(node, nodes.Test):
        if node.name == "defined":
            return f"{to_python_code(node.node)} is not None"
        elif node.name == "undefined":
            return f"{to_python_code(node.node)} is None"
        else:
            raise NotImplementedError(f"jinja2 Test nodes with name={node.name!r} are not supported: {node!r}")
    elif isinstance(node, nodes.Not):
        if isinstance(node.node, nodes.Test):
            # Special case match well-known structures for more idiomatic Python
            if node.node.name == "defined":
                return f"{to_python_code(node.node.node)} is None"
            elif node.node.name == "undefined":
                return f"{to_python_code(node.node.node)} is not None"
        elif isinstance(node.node, nodes.Name):
            return f"not {to_python_code(node.node)}"
        return f"not ({to_python_code(node.node)})"
    elif isinstance(node, nodes.Or):
        return f"({to_python_code(node.left)} or {to_python_code(node.right)})"
    elif isinstance(node, nodes.And):
        return f"({to_python_code(node.left)} and {to_python_code(node.right)})"
    else:
        raise NotImplementedError(f"jinja2 {node.__class__} nodes are not supported: {node!r}")


class Conditional:
    """
    An Ansible conditional expression
    """
    def __init__(self, engine: template.Engine, body: str):
        # Original unparsed expression
        self.body: str = body
        # Expression compiled to a callable
        self.expression: Callable = engine.env.compile_expression(body)
        parser = jinja2.parser.Parser(engine.env, body, state='variable')
        self.jinja2_ast: nodes.Node = parser.parse_expression()

    def to_jsonable(self) -> Dict[str, Any]:
        return {
            "node": "conditional",
            "body": self.body,
        }

    def list_role_vars(self) -> Sequence[str]:
        fv = FindVars()
        fv.visit(self.jinja2_ast)
        return fv.found

    def evaluate(self, ctx: Dict[str, Any]):
        ctx = {name: val for name, val in ctx.items() if val is not None}
        return self.expression(**ctx)

    def get_python_code(self) -> str:
        return to_python_code(self.jinja2_ast)
