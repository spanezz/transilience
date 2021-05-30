from __future__ import annotations
from dataclasses import dataclass
import logging


@dataclass
class Action:
    name: str

    def __post_init__(self):
        self.log = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

    def run(self):
        raise NotImplementedError(f"run not implemented for action {self.__class__.__name__}: {self.name}")


# https://docs.ansible.com/ansible/latest/collections/index_module.html

# @dataclass
# class AptInstall(Action):
#     packages: Sequence[str]
#     recommends: bool = False
#
#     def run(self, system: System):
#         """
#         Install the given package(s), if they are not installed yet
#         """
#         cmd = ["apt", "-y", "install"]
#         if not self.recommends:
#             cmd.append("--no-install-recommends")
#
#         has_packages = False
#         for pkg in self.packages:
#             if system.has_file("var", "lib", "dpkg", "info", f"{pkg}.list"):
#                 continue
#             cmd.append(pkg)
#             has_packages = True
#
#         if not has_packages:
#             return
#
#         system.run(cmd)
#
#
# @dataclass
# class AptRemove(Action):
#     packages: Sequence[str]
#     purge: bool = False
#
#     def run(self, system: System):
#         """
#         Remove the given packages
#         """
#         cmd = ["apt", "-y", "remove" if self.purge is False else "purge"]
#         for pkg in self.packages:
#             # TODO: check in /var/lib/dpkg if they are already removed/purged
#             cmd.append(pkg)
#         system.run(cmd)
#
#
# @dataclass
# class AptInstallDeb(Action):
#     packages: Sequence[str]
#     recommends: bool = False
#
#     def run(self, system: System):
#         """
#         Install the given package(s), if they are not installed yet
#         """
#         with system.tempdir() as workdir:
#             system_paths = []
#             for package in self.packages:
#                 system.copy_to(package, workdir)
#                 system_paths.append(os.path.join(workdir, os.path.basename(package)))
#
#             cmd = ["apt", "-y", "install"]
#             if not self.recommends:
#                 cmd.append("--no-install-recommends")
#
#             for path in system_paths:
#                 cmd.append(path)
#
#             system.run(cmd)
