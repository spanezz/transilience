from __future__ import annotations
from typing import Optional, List, Dict, Any, Sequence
import jinja2
import jinja2.meta


def finalize_value(val):
    """
    Jinja2 finalize hook that renders None as the empty string
    """
    # See: http://jinja.pocoo.org/docs/2.10/api/ under "finalize"
    # and https://stackoverflow.com/questions/11146619/suppress-none-output-as-string-in-jinja2
    if val is None:
        return ""
    else:
        return val


class Engine:
    """
    Jinja2 machinery tuned to render text templates
    """
    def __init__(self, template_paths: Optional[List[str]] = None):
        if template_paths is None:
            template_paths = ["."]

        self.env = jinja2.Environment(
                autoescape=False,
                trim_blocks=True,
                finalize=finalize_value,
                loader=jinja2.FileSystemLoader(template_paths))

    def render_string(self, template: str, ctx: Dict[str, Any]) -> str:
        """
        Render a template from a string
        """
        tpl = self.env.from_string(template)
        return tpl.render(**ctx)

    def render_file(self, path: str, ctx: Dict[str, Any]) -> str:
        """
        Render a template from a file, relative to template_paths
        """
        tpl = self.env.get_template(path)
        return tpl.render(**ctx)

    def list_string_template_vars(self, template: str) -> Sequence[str]:
        """
        List the template variables used by this template string
        """
        ast = self.env.parse(template)
        return jinja2.meta.find_undeclared_variables(ast)

    def list_file_template_vars(self, path: str) -> Sequence[str]:
        """
        List the template variables used by this template string
        """
        tpl = self.env.get_template(path)
        with open(tpl.filename, "rt") as fd:
            ast = self.env.parse(fd.read(), tpl.name, tpl.filename)
        return jinja2.meta.find_undeclared_variables(ast)
