from __future__ import annotations
from typing import Sequence
from dataclasses import dataclass
import os
from .system import System


@dataclass
class Action:
    name: str

    def run(self, system: System):
        raise NotImplementedError(f"run not implemented for action {self.__class__.__name__}: {self.name}")


@dataclass
class AptInstall(Action):
    packages: Sequence[str]
    recommends: bool = False

    def run(self, system: System):
        """
        Install the given package(s), if they are not installed yet
        """
        cmd = ["apt", "-y", "install"]
        if not self.recommends:
            cmd.append("--no-install-recommends")

        has_packages = False
        for pkg in self.packages:
            if system.has_file("var", "lib", "dpkg", "info", f"{pkg}.list"):
                continue
            cmd.append(pkg)
            has_packages = True

        if not has_packages:
            return

        system.run(cmd)


@dataclass
class AptInstallDeb(Action):
    packages: Sequence[str]
    recommends: bool = False

    def run(self, system: System):
        """
        Install the given package(s), if they are not installed yet
        """
        with system.tempdir() as workdir:
            system_paths = []
            for package in self.packages:
                system.copy_to(package, workdir)
                system_paths.append(os.path.join(workdir, os.path.basename(package)))

            cmd = ["apt", "-y", "install"]
            if not self.recommends:
                cmd.append("--no-install-recommends")

            for path in system_paths:
                cmd.append(path)

            system.run(cmd)
