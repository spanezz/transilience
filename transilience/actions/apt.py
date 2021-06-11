from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Iterator
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


# See https://docs.ansible.com/ansible/latest/collections/ansible/builtin/apt_module.html
@builtin.action(name="apt")
@dataclass
class Apt(Action):
    """
    Same as ansible's builtin.apt.

    force_apt_get is ignored: apt-get is always used

    Not yet implemented:
     - force
     - update_cache_retries
     - update_cache_retry_max_delay
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

    def summary(self):
        if self.state == "present":
            if len(self.name) == 1:
                return f"Install package {self.name[0]}"
            else:
                return f"Install packages {', '.join(self.name)}"
        else:
            return f"{self.__class__}: unknown state {self.state!r}"

    def get_cache_mtime(self) -> int:
        """
        Get the modification time of the apt cache.

        Returns 0 if there is no cache
        """
        try:
            return os.path.getmtime("/var/cache/apt/pkgcache.bin")
        except FileNotFoundError:
            return 0

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
            yield "-o"
            yield f"Dpkg::Options::=--{dpkg_option}"

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

    def all_installed(self, pkgs: List[str]) -> bool:
        """
        Returns True if all the given packages are installed
        """
        cmd = [
            "dpkg-query", "-f", "${Status}\n", "-W"
        ] + pkgs
        res = subprocess.run(cmd, text=True, capture_output=True)
        if res.returncode != 0:
            return False
        for line in res.stdout.splitlines():
            if line.strip() != "install ok installed":
                return False
        return True

    def has_apt_changes(self, stdout: str) -> bool:
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

    # def do_present(self):
    #     """
    #     Install the given package(s), if they are not installed yet
    #     """
    #     if self.all_installed(self.name):
    #         return

    #     cmd = ["apt-get", "-y"]
    #     if self.default_release:
    #         cmd += ["-t=" + self.default_release]
    #     cmd.append("install")
    #     if self.install_recommends is True:
    #         cmd.append("--install-recommends")
    #     elif self.install_recommends is False:
    #         cmd.append("--no-install-recommends")
    #     cmd += self.name

    #     self.run_command(cmd)
    #     self.set_changed()
    #     # TODO: check output to see if something changed
    #     # autoremove: "0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded."
    #     # autoclean: "Del .+"

    def base_apt_command(self) -> List[str]:
        """
        Return a list with the common initial part of apt commands
        """
        cmd = [self.find_command("apt-get"), "-q", "-y"]
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

    def do_deb(self):
        """
        Run apt install with .deb files
        """
        debs = [os.path.abspath(path) for path in self.deb]
        # for path in self.deb:
        #     path = os.path.abspath(path)
        #     # TODO: just parse with dpkg -I {path}
        #     TODO: extract control file and check if already installed
        #     pkg = apt.debfile.DebPackage(deb_file)
        #     pkg_name = get_field_of_deb(m, deb_file, "Package")
        #     pkg_version = get_field_of_deb(m, deb_file, "Version")
        #     if len(apt_pkg.get_architectures()) > 1:
        #         pkg_arch = get_field_of_deb(m, deb_file, "Architecture")
        #         pkg_key = "%s:%s" % (pkg_name, pkg_arch)
        #     else:
        #         pkg_key = pkg_name
        #     try:
        #         installed_pkg = apt.Cache()[pkg_key]
        #         installed_version = installed_pkg.installed.version
        #         if package_version_compare(pkg_version, installed_version) == 0:
        #             # Does not need to down-/upgrade, move on to next package
        #             continue
        #     except Exception:
        #         # Must not be installed, continue with installation
        #         pass
        #     debs.append(path)

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

    def do_install(self, state: str, packages: List[str]):
        """
        Run apt-get install or apt-get build-dep
        """
        if not packages:
            return

        if state in ("latest", "build-dep", "fixed"):
            # Always call apt-get
            pass
        else:
            # Present: maybe we can check what is already present
            for pkg in packages:
                if "*" in pkg or "=" in pkg or ":" in pkg:
                    is_plain = False
                    break
            else:
                is_plain = True

            if is_plain:
                # No wildcards are used: we can definitely check
                if self.all_installed(packages):
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

            apt_mark = shutil.which("apt-mark")
            if apt_mark is None:
                return
            cmd = [apt_mark, "manual"] + packages
            self.run_command(cmd)

    def do_remove(self, packages: List[str]):
        for pkg in packages:
            if "*" in pkg or "=" in pkg or ":" in pkg:
                is_plain = False
                break
        else:
            is_plain = True

        if is_plain:
            ...  # TODO
            # # No wildcards are used: we can definitely check
            # if self.none_installed(packages):
            #     # TODO: in none_installed, check self.purge to see if 'c' state matters
            #     return

        if not packages:
            return

        cmd = self.base_apt_command()

        if self.purge:
            cmd.append("--purge")

        if self.autoremove:
            cmd.append("--auto-remove")

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

    def run(self, system: transilience.system.System):
        cache_updated = False
        if self.update_cache:
            if not self.is_cache_still_valid():
                self.run_command([self.find_command("apt-get"), "-q", "update"])
                cache_updated = True

        # If there is nothing else to do exit. This will set state as
        # changed based on if the cache was updated.
        if not self.name and not self.upgrade and not self.deb:
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
