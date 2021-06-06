from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List
from dataclasses import dataclass, field
import subprocess
from .action import Action

if TYPE_CHECKING:
    import transilience.system


# See https://docs.ansible.com/ansible/latest/collections/ansible/builtin/apt_module.html
@dataclass
class Apt(Action):
    """
    Same as ansible's builtin.apt.

    Not yet implemented:
     - allow_unauthenticated
     - autoclean
     - autoremove
     - cache_valid_time
     - deb
     - default_release
     - dpkg_options
     - fail_on_autoremove
     - force
     - force_apt_get
     - only_upgrade
     - policy_rc_d
     - purge
     - state
     - update_cache
     - update_cache_retries
     - update_cache_retry_max_delay
     - upgrade
    """
    pkg: List[str] = field(default_factory=list)
    state: str = "present"
    install_recommends: Optional[bool] = None

    def all_installed(self, pkgs: List[str]) -> True:
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

    def do_present(self):
        """
        Install the given package(s), if they are not installed yet
        """
        if self.all_installed(self.pkg):
            return

        cmd = ["apt-get", "-y", "install"]
        if self.install_recommends is True:
            cmd.append("--install-recommends")
        elif self.install_recommends is False:
            cmd.append("--no-install-recommends")
        cmd += self.pkg

        self.run_command(cmd)
        self.set_changed()

    def run(self, system: transilience.system.System):
        if self.state == "present":
            self.do_present()
        else:
            # TODO: absent
            # TODO: build-dep
            # TODO: latest
            # TODO: fixed
            raise NotImplementedError(f"{self.__class__}: call with state={self.state!r} is not yet implemented")
