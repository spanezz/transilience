from __future__ import annotations
from typing import Type, Dict, TextIO
import dataclasses
import contextlib
import importlib
import argparse
import inspect
import sys
from transilience.actions import Action


def document(module: str, to_document: Dict[str, Type[Action]], file=TextIO):
    print(f"""# {module}

Documentation of the actions provided in module `{module}`.

""", file=file)

    for name, action in sorted(to_document.items()):
        doc = inspect.getdoc(action)
        print(f"""## {name}

{doc}

Parameters:
""", file=file)

        for field in sorted(dataclasses.fields(action), key=lambda x: x.name):
            if field.name in ("uuid", "result"):
                continue
            field_doc = f"* {field.name} [`{field.type}`]"
            if field.default is not dataclasses.MISSING:
                field_doc += f" = `{field.default!r}`"
            fdoc = field.metadata.get("doc")
            if fdoc is not None:
                field_doc += ": " + fdoc
            print(field_doc, file=file)

        print(file=file)



@contextlib.contextmanager
def output(args):
    if args.output:
        with open(args.output, "wt") as fd:
            yield fd
    else:
        yield sys.stdout


def main():
    parser = argparse.ArgumentParser(description="Generate documentation about transilience actions")
    parser.add_argument("-o", "--output", action="store", help="output file (default: stdout)")
    parser.add_argument("module", action="store", nargs="?", default="transilience.actions.builtin",
                        help="module containing the actions to document (default: %(default)s)")
    args = parser.parse_args()

    try:
        mod = importlib.import_module(args.module)
    except ModuleNotFoundError:
        modname, _, member = args.module.rpartition(".")
        mod = importlib.import_module(modname)
        mod = getattr(mod, member)

    to_document: Dict[str, Type[Action]] = {}
    for name, value in inspect.getmembers(mod):
        if not isinstance(value, type):
            continue
        if not issubclass(value, Action):
            continue
        to_document[name] = value

    with output(args) as fd:
        document(args.module, to_document, fd)


if __name__ == "__main__":
    sys.exit(main())
