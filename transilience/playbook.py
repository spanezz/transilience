from __future__ import annotations
from typing import TYPE_CHECKING, Sequence, Union, Type, Optional
import threading
import importlib
import argparse
import inspect
import logging
import json
import sys
import os
try:
    import coloredlogs
except ModuleNotFoundError:
    coloredlogs = None
from transilience.runner import Runner


if TYPE_CHECKING:
    from transilience.hosts import Host
    from .role import Role


class Playbook:
    def __init__(self):
        self.progress = logging.getLogger("progress")
        self.run_context = threading.local()

    def setup_logging(self):
        FORMAT = "%(asctime)-15s %(levelname)s %(name)s %(message)s"
        PROGRESS_FORMAT = "%(asctime)-15s %(message)s"
        if self.args.debug:
            log_level = logging.DEBUG
        elif self.args.verbose:
            log_level = logging.INFO
        else:
            log_level = logging.WARN

        progress_formatter = None
        if coloredlogs is not None:
            coloredlogs.install(level=log_level, fmt=FORMAT, stream=sys.stderr)
            if log_level > logging.INFO:
                progress_formatter = coloredlogs.ColoredFormatter(fmt=PROGRESS_FORMAT)
        else:
            logging.basicConfig(level=log_level, stream=sys.stderr, format=FORMAT)
            if log_level > logging.INFO:
                progress_formatter = logging.Formatter(fmt=PROGRESS_FORMAT)

        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(progress_formatter)
        self.progress.addHandler(handler)
        self.progress.setLevel(logging.INFO)
        self.progress.propagate = False

    def make_argparser(self):
        description = inspect.getdoc(self)
        if not description:
            description = "Provision systems"

        parser = argparse.ArgumentParser(description=description)
        parser.add_argument("-v", "--verbose", action="store_true",
                            help="verbose output")
        parser.add_argument("--debug", action="store_true",
                            help="verbose output")
        parser.add_argument("-C", "--check", action="store_true",
                            help="do not perform changes, but check if changes would be needed")
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--ansible-to-python", action="store", metavar="role",
                           help="print the given Ansible role as Transilience Python code")
        group.add_argument("--ansible-to-ast", action="store", metavar="role",
                           help="print the AST of the given Ansible role as understood by Transilience")
        group.add_argument("--zipapp", action="store", metavar="file.pyz",
                           help="bundle this playbook in a self-contained executable python zipapp")

        return parser

    def hosts(self) -> Sequence[Host]:
        """
        Generate a sequence with all the systems on which the playbook needs to run
        """
        return ()

    def thread_main(self, host: Host):
        """
        Main entry point for per-host threads
        """
        self.run_context.host = host
        self.run_context.runner = Runner(host, check_mode=self.args.check)
        self.start(host)
        self.run_context.runner.main()

    def load_python_role(self, role_name: str) -> Optional[Type[Role]]:
        """
        Try to build a Transilience role from a Python module
        """
        mod = importlib.import_module(f"roles.{role_name}")
        if not hasattr(mod, "Role"):
            return None
        return type(role_name, (mod.Role,), {})

    def load_ansible_role(self, role_name: str) -> Optional[Type[Role]]:
        """
        Try to build a Transilience role from an Ansible YAML role
        """
        from .ansible import RoleLoader, RoleNotFoundError
        try:
            loader = RoleLoader(role_name)
            loader.load()
        except RoleNotFoundError:
            return None
        return loader.get_role_class()

    def load_role(self, role_name: str) -> Type[Role]:
        """
        Load a role by its name
        """
        role = self.load_python_role(role_name)
        if role is not None:
            return role

        role = self.load_ansible_role(role_name)
        if role is not None:
            return role

        raise RuntimeError(f"role {role_name} not found")

    def add_role(self, role_cls: Union[str, Type[Role]], **kw):
        """
        Add a role to this thread's runner
        """
        if not hasattr(self.run_context, "runner"):
            raise RuntimeError(f"{self.__class__.__name__}.add_role cannot be called outside of a host thread")
        if isinstance(role_cls, str):
            role_cls = self.load_role(role_cls)
        self.run_context.runner.add_role(role_cls, **kw)

    def start(self, host: Host):
        """
        Start the playbook on the given runner.

        This method is called once for each system returned by systems()
        """
        raise NotImplementedError(f"{self.__class__.__name__}.start is not implemented")

    def role_to_python(self, name: str, file=None):
        """
        Print the Python code generated from the given Ansible role
        """
        from .ansible import RoleLoader
        loader = RoleLoader(name)
        loader.load()
        print(loader.get_python_code(), file=file)

    def role_to_ast(self, name: str, file=None):
        """
        Print the Python code generated from the given Ansible role
        """
        if file is None:
            file = sys.stdout

        if not hasattr(file, "fileno"):
            indent = None
        elif os.isatty(file.fileno()):
            indent = 2
        else:
            indent = None

        from .ansible import RoleLoader
        loader = RoleLoader(name)
        loader.load()
        json.dump(loader.ansible_role.to_jsonable(), file, indent=indent)

    def main(self):
        parser = self.make_argparser()
        self.args = parser.parse_args()
        self.setup_logging()

        if self.args.ansible_to_python:
            self.role_to_python(self.args.ansible_to_python)
            return

        if self.args.ansible_to_ast:
            self.role_to_ast(self.args.ansible_to_ast)
            return

        # Start all the runners in separate threads
        threads = []
        for host in self.hosts():
            t = threading.Thread(target=self.thread_main, args=(host,))
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()
