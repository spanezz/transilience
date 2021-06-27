from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Iterator, Dict, Tuple, Union
from dataclasses import dataclass, field
import contextlib
import subprocess
import tempfile
import shutil
import time
import os
import re
from .action import Action
from . import builtin

if TYPE_CHECKING:
    import transilience.system


re_apt_results = re.compile(
        br"^(?P<upgraded>\d+) upgraded, (?P<new>\d+) newly installed,"
        br" (?P<removed>\d+) to remove and (?P<held>\d+) not upgraded.$")

# Package names (both source and binary, see Package) must consist only
# of lower case letters ("a-z"), digits ("0-9"), plus ("+") and minus
# ("-") signs, and periods ("."). They must be at least two characters
# long and must start with an alphanumeric character.
re_pkg_name = re.compile(r"(?P<name>[a-z0-9][a-z0-9+.-]+)(?::(?P<arch>\w+))?(?:=(?P<ver>.+))?")


class DpkgStatus:
    """
    Information about the current status of packages
    """
    def __init__(self, path="/var/lib/dpkg/status"):
        self.path = path
        # Modification time of path the last time we read it
        self.mtime: float = None
        # Package status indexed by package (name, arch): (version, status)
        self.packages: Dict[Tuple[str, str], Tuple[str, str]] = {}
        # Read the default architecture for the system
        res = subprocess.run(["dpkg", "--print-architecture"], check=True, text=True, capture_output=True)
        self.arch = res.stdout.strip()

    def status(self, package: str, arch: Optional[str] = None) -> Union[Tuple[None, None], Tuple[str, str]]:
        """
        Find the current status of a package.

        Returns (None, None) if not found, or (version, status) if found
        """
        arches: Tuple[str, ...]
        if arch is None:
            arches = (self.arch, "all")
        else:
            arches = (arch,)
        for a in arches:
            res = self.packages.get((package, a))
            if res is not None:
                return res
        return None, None

    def update(self):
        """
        Reload the dpkg status if it has changed on disk
        """
        try:
            dpkg_mtime = os.path.getmtime(self.path)
        except FileNotFoundError:
            self.packages = {}
            self.mtime = None
            return

        if self.mtime is not None and dpkg_mtime < self.mtime:
            # Cache hit
            return

        self.load_status()
        self.mtime = dpkg_mtime

    def load_status(self):
        """
        Parse dpkg's status file
        """
        # We can cut a lot of corners here, since we only need a specific
        # subset of the file contents. Particularly, we don't need multiline
        # fields, and we can just match field headers and paragraph breaks
        packages = {}
        with open(self.path, "rb") as fd:
            package: Optional[bytes] = None
            version: Optional[bytes] = None
            arch: Optional[bytes] = None
            status: Optional[bytes] = None
            for line in fd:
                if line == b"\n":
                    if package is not None:
                        packages[(package, arch)] = (version, status)
                    package = None
                    version = None
                    arch = None
                    status = None
                elif line.startswith(b"Package: "):
                    package = line[9:-1].decode()
                elif line.startswith(b"Version: "):
                    version = line[9:-1].decode()
                elif line.startswith(b"Architecture: "):
                    arch = line[14:-1].decode()
                elif line.startswith(b"Status: "):
                    status = line[8:-1].decode()
            if package is not None:
                packages[(package, arch)] = (version, status)
        self.packages = packages


@builtin.action(name="apt")
@dataclass
class Apt(Action):
    """
    Same as Ansible's
    [builtin.apt](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/apt_module.html).

    `force_apt_get` is ignored: `apt-get` is always used.

    Not yet implemented:

     * force
     * update_cache_retries
     * update_cache_retry_max_delay
    """
    name: List[str] = field(default_factory=list)
    deb: List[str] = field(default_factory=list)
    state: str = "present"
    install_recommends: Optional[bool] = None
    upgrade: str = "no"
    force_apt_get: bool = False  # Ignored
    default_release: Optional[str] = None
    update_cache: bool = False
    cache_valid_time: int = 0
    autoremove: bool = False
    autoclean: bool = False
    fail_on_autoremove: bool = False
    allow_unauthenticated: bool = False
    dpkg_options: List[str] = field(default_factory=lambda: ["force-confdef", "force-confold"])
    policy_rc_d: Optional[int] = None
    only_upgrade: bool = False
    purge: bool = False

    def __post_init__(self):
        super().__post_init__()
        if self.cache_valid_time:
            self.update_cache = True

        if self.deb and self.state != "present":
            raise NotImplementedError("deb currently only supports state=present")

        for package in self.name:
            if package.count('=') > 1:
                raise ValueError(f"invalid package name: {package!r}")
            if self.state == "latest" and '=' in package:
                raise RuntimeError(f"cannot use version numbers when state=latest: {package!r}")

    def action_summary(self):
        if self.state == "present":
            if len(self.name) == 1:
                return f"Install package {self.name[0]}"
            else:
                return f"Install packages {', '.join(self.name)}"
        else:
            return f"{self.__class__}: unknown state {self.state!r}"

    def get_cache_mtime(self) -> float:
        """
        Get the modification time of the apt cache.

        Returns 0 if there is no cache
        """
        try:
            return os.path.getmtime("/var/cache/apt/pkgcache.bin")
        except FileNotFoundError:
            return 0.0

    def is_cache_still_valid(self) -> bool:
        """
        Check cache_valid_time against the cache modification time.

        Returns True if cache_valid_time is set, the cache exists, and its
        mtime is less than cache_valid_mtime seconds ago
        """
        if not self.cache_valid_time:
            return False
        return self.get_cache_mtime() + self.cache_valid_time >= time.time()

    def expand_dpkg_options(self) -> Iterator[str]:
        """
        Turn the short version dpkg options passed as arguments into options for apt
        """
        for dpkg_option in self.dpkg_options:
            yield f"--option=Dpkg::Options::=--{dpkg_option}"

    @contextlib.contextmanager
    def stash(self, path: str):
        """
        Move aside a file while this context manager runs.

        If the file does not exist, does nothing
        """
        if not os.path.exists(path):
            try:
                yield
            finally:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
            return

        with tempfile.NamedTemporaryFile(prefix=path, delete=False) as tf:
            tf.close()

            try:
                os.rename(path, tf.name)
            except Exception:
                os.unlink(tf.name)
                raise

            try:
                yield
            finally:
                os.rename(tf.name, path)

    @contextlib.contextmanager
    def install_policy_rc_d(self):
        """
        Set up a /usr/sbin/policy-rc.d file to prevent starting services during
        install/upgrades
        """
        # See https://people.debian.org/~hmh/invokerc.d-policyrc.d-specification.txt
        if self.policy_rc_d is None:
            yield
            return

        path = '/usr/sbin/policy-rc.d'
        with self.stash(path):
            with open('/usr/sbin/policy-rc.d', 'wt') as fd:
                print("#!/bin/sh", file=fd)
                print(f"exit {self.policy_rc_d:d}", file=fd)
            os.chmod(path, 0o0755)
            yield

    def has_apt_changes(self, stdout: bytes) -> bool:
        """
        Parse apt output to see if changes were reported
        """
        for line in stdout.splitlines():
            mo = re_apt_results.match(line)
            if not mo:
                continue
            if (int(mo.group("upgraded")) > 0 or int(mo.group("new")) > 0 or
                    int(mo.group("removed")) > 0):
                return True
        return False

    def find_apt_get(self) -> str:
        """
        Return the path to apt-get.

        This is in a separate function to make it easier to mock
        """
        return self.find_command("apt-get")

    def base_apt_command(self) -> List[str]:
        """
        Return a list with the common initial part of apt commands
        """
        cmd = [self.find_apt_get(), "-q", "-y"]
        if self.check:
            cmd.append("--simulate")
        cmd.extend(self.expand_dpkg_options())
        return cmd

    def do_upgrade(self, mode=None):
        """
        Run apt-get upgrade
        """
        if mode is None:
            mode = self.upgrade

        cmd = self.base_apt_command()

        if self.fail_on_autoremove:
            cmd.append("--no-remove")

        if self.allow_unauthenticated:
            cmd.append("--allow-unauthenticated")

        if mode in ("dist", "full"):
            cmd.append("dist-upgrade")
        elif mode in ("safe", "yes"):
            cmd += ["upgrade", "--with-new-pkgs"]

        if self.autoremove:
            cmd.append("--auto-remove")

        if self.default_release:
            cmd += ["-t", self.default_release]

        with self.install_policy_rc_d():
            res = self.run_command(cmd, capture_output=True)

        if self.has_apt_changes(res.stdout):
            self.set_changed()

    def get_deb_info(self, path: str) -> Tuple[str, str, str]:
        """
        Return (package, version, arch) information from a .deb file
        """
        res = subprocess.run(["dpkg", "-I", path], capture_output=True, check=True)
        package: Optional[str] = None
        version: Optional[str] = None
        arch: Optional[str] = None
        for line in res.stdout.splitlines():
            if line.startswith(b" Package: "):
                package = line[10:].decode()
            elif line.startswith(b" Version: "):
                version = line[10:].decode()
            elif line.startswith(b" Architecture: "):
                arch = line[15:].decode()
        if package is None:
            raise RuntimeError(f"{path!r} contains no Package information")
        if version is None:
            raise RuntimeError(f"{path!r} contains no Version information")
        if arch is None:
            raise RuntimeError(f"{path!r} contains no Architecture information")
        return package, version, arch

    def do_deb(self):
        """
        Run apt install with .deb files
        """
        debs = [os.path.abspath(path) for path in self.deb]
        for path in self.deb:
            path = os.path.abspath(path)
            package, version, arch = self.get_deb_info(path)
            dpkg_version, dpkg_status = self._dpkg_cache.status(package, arch)
            if dpkg_version == version and dpkg_status == "install ok installed":
                continue
            debs.append(path)

        if not debs:
            return

        cmd = self.base_apt_command()

        if self.only_upgrade:
            cmd.append("--only-upgrade")

        if self.fail_on_autoremove:
            cmd.append('--no-remove')

        if self.default_release:
            cmd += ["-t", self.default_release]

        if self.install_recommends is True:
            cmd.append("--install-recommends")
        elif self.install_recommends is False:
            cmd.append("--no-install-recommends")

        if self.allow_unauthenticated:
            cmd.append("--allow-unauthenticated")

        cmd.append("install")

        cmd += debs

        with self.install_policy_rc_d():
            res = self.run_command(cmd, capture_output=True)

        if self.has_apt_changes(res.stdout):
            self.set_changed()

    def filter_packages_to_install(self, packages: List[str]) -> List[str]:
        """
        Return a filtered version of packages with all packages already
        installed
        """
        self._dpkg_cache.update()

        filtered_packages: List[str] = []

        for pkg in packages:
            if "*" in pkg:
                filtered_packages.append(pkg)
                continue

            mo = re_pkg_name.match(pkg)
            if not mo:
                raise RuntimeError(f"Invalid package name: {pkg!r}")

            name = mo.group("name")
            version = mo.group("ver") or None
            arch = mo.group("arch") or None

            dpkg_version, dpkg_status = self._dpkg_cache.status(name, arch)
            if dpkg_version is None:
                # Not installed
                filtered_packages.append(pkg)
            elif version is not None and version != dpkg_version:
                # Installed but with a different version
                filtered_packages.append(pkg)
            elif dpkg_status != "install ok installed":
                filtered_packages.append(pkg)

        return filtered_packages

    def mark_manually_installed(self, packages: List[str]):
        """
        Mark the given packages as manually installed
        """
        apt_mark = shutil.which("apt-mark")
        if apt_mark is None:
            return
        cmd = [apt_mark, "manual"] + packages
        self.run_command(cmd)

    def do_install(self, state: str, packages: List[str]):
        """
        Run apt-get install or apt-get build-dep
        """
        if state not in ("latest", "build-dep", "fixed"):
            packages = self.filter_packages_to_install(packages)

        if not packages:
            return

        cmd = self.base_apt_command()

        if self.only_upgrade:
            cmd.append("--only-upgrade")

        if self.fail_on_autoremove:
            cmd.append('--no-remove')

        if self.default_release:
            cmd += ["-t=" + self.default_release]

        if self.install_recommends is True:
            cmd.append("--install-recommends")
        elif self.install_recommends is False:
            cmd.append("--no-install-recommends")

        if self.allow_unauthenticated:
            cmd.append("--allow-unauthenticated")

        if state == "build-dep":
            cmd.append("build-dep")
        else:
            if state == "fixed":
                cmd.append("--fix-broken")
            if self.autoremove:
                cmd.append("--auto-remove")
            cmd.append("install")

        cmd.extend(packages)

        with self.install_policy_rc_d():
            res = self.run_command(cmd, capture_output=True)

        if self.has_apt_changes(res.stdout):
            self.set_changed()

            if state == "build-dep":
                return

            self.mark_manually_installed(packages)

    def filter_packages_to_remove(self, packages: List[str]) -> List[str]:
        """
        Return a filtered version of packages with all packages already
        removed
        """
        self._dpkg_cache.update()

        filtered_packages: List[str] = []

        for pkg in packages:
            if "*" in pkg:
                filtered_packages.append(pkg)
                continue

            mo = re_pkg_name.match(pkg)
            if not mo:
                raise RuntimeError(f"Invalid package name: {pkg!r}")

            name = mo.group("name")
            # version = mo.group("ver") or None
            arch = mo.group("arch") or None

            dpkg_version, dpkg_status = self._dpkg_cache.status(name, arch)
            if dpkg_version is None:
                # Not installed
                continue

            if not self.purge and dpkg_status == "deinstall ok config-files":
                # Removed, not purged, but purge was not requested
                continue

            filtered_packages.append(pkg)

        return filtered_packages

    def do_remove(self, packages: List[str]):
        packages = self.filter_packages_to_remove(packages)
        if not packages:
            return

        cmd = self.base_apt_command()

        if self.purge:
            cmd.append("--purge")

        if self.autoremove:
            cmd.append("--auto-remove")

        cmd.append("remove")

        cmd.extend(packages)

        with self.install_policy_rc_d():
            res = self.run_command(cmd, capture_output=True)

        if self.has_apt_changes(res.stdout):
            self.set_changed()

    def do_clean(self, operation: str):
        cmd = self.base_apt_command()
        if self.purge:
            cmd.append("--purge")
        cmd.append(operation)

        with self.install_policy_rc_d():
            res = self.run_command(cmd, capture_output=True)

        if operation == "autoclean":
            for line in res.stdout.splitlines():
                if line.startswith("Del "):
                    self.set_changed()
                    break
        else:
            if self.has_apt_changes(res.stdout):
                self.set_changed()

    def action_run(self, system: transilience.system.System):
        super().action_run(system)
        self._dpkg_cache = system.get_action_cache(Apt, DpkgStatus)

        cache_updated = False
        if self.update_cache:
            if not self.is_cache_still_valid():
                cmd = [self.find_apt_get()]
                if self.check:
                    cmd.append("--simulate")
                cmd += ("-q", "update")
                self.run_command(cmd, capture_output=True)
                cache_updated = True

        # If there is nothing else to do exit. This will set state as
        # changed based on if the cache was updated.
        if not self.name and self.upgrade == "no" and not self.deb:
            if cache_updated:
                self.set_changed()
            return

        if self.upgrade != "no":
            self.do_upgrade()

        if self.deb:
            # TODO: do we want to download debs, when we can copy them to the
            #       remote system and install them?
            # if '://' in p['deb']:
            #     p['deb'] = fetch_file(module, p['deb'])
            self.do_deb()

        packages = self.name
        try:
            packages.remove("*")
            all_installed = True
        except ValueError:
            all_installed = False

        if self.state == "latest" and all_installed:
            if packages:
                raise RuntimeError("unable to install additional packages when upgrading all installed packages")
            self.do_upgrade("yes")

        if not packages:
            if self.autoclean:
                self.do_clean("autoclean")
            if self.autoremove:
                self.do_clean("autoremove")
        else:
            if self.state in ('latest', 'present', 'build-dep', 'fixed'):
                self.do_install(self.state, packages)
            elif self.state == 'absent':
                self.do_remove(packages)
            else:
                raise NotImplementedError(
                        f"{self.__class__}: call with state={self.state!r} is not implemented")
