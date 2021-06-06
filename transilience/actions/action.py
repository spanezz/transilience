from __future__ import annotations
from typing import TYPE_CHECKING, List, Dict, Any
from dataclasses import dataclass, asdict, field
import subprocess
import importlib
import logging
import shlex
import uuid
import os

if TYPE_CHECKING:
    import transilience.system


@dataclass
class Action:
    name: str
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    changed: bool = False

    def __post_init__(self):
        self.log = logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}")

    def set_changed(self):
        """
        Mark that this action has changed something
        """
        self.changed = True

    def run_command(self, cmd: List[str], check=True, **kw) -> subprocess.CompletedProcess:
        """
        Run the given command inside the chroot
        """
        self.log.debug("%s: running %s", self.name, " ".join(shlex.quote(x) for x in cmd))
        if "env" not in kw:
            kw["env"] = dict(os.environ)
            kw["env"]["LANG"] = "C"
        return subprocess.run(cmd, check=check, **kw)

    def run(self, system: transilience.system.System):
        pass

    def serialize(self) -> Dict[str, Any]:
        """
        Serialize this action as a dict
        """
        d = asdict(self)
        d["__action__"] = f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        return d

    @classmethod
    def deserialize(cls, serialized: Dict[str, Any]) -> "Action":
        """
        Deserialize an action form a dict
        """
        action_name = serialized.pop("__action__", None)
        if action_name is None:
            raise ValueError(f"action {serialized!r} has no '__action__' element")
        mod_name, _, cls_name = action_name.rpartition(".")
        mod = importlib.import_module(mod_name)
        action_cls = getattr(mod, cls_name, None)
        if action_cls is None:
            raise ValueError(f"action {action_name!r} not found in transilience.actions")
        if not issubclass(action_cls, Action):
            raise ValueError(f"action {action_name!r} is not an subclass of transilience.actions.Action")
        return action_cls(**serialized)

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
