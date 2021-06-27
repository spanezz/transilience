from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass
import subprocess
import platform
import socket
import shutil
import re
from .facts import Facts

if TYPE_CHECKING:
    import transilience.system


# i86pc is a Solaris and derivatives-ism
SOLARIS_I86_RE_PATTERN = r'i([3456]86|86pc)'
solaris_i86_re = re.compile(SOLARIS_I86_RE_PATTERN)


# From ansible/module_utils/facts/system/platform.py
@dataclass
class Platform(Facts):
    """
    Facts from the platform module
    """
    ansible_system: Optional[str] = None
    ansible_kernel: Optional[str] = None
    ansible_kernel: Optional[str] = None
    ansible_kernel_version: Optional[str] = None
    ansible_machine: Optional[str] = None
    ansible_python_version: Optional[str] = None
    ansible_fqdn: Optional[str] = None
    ansible_hostname: Optional[str] = None
    ansible_nodename: Optional[str] = None
    ansible_domain: Optional[str] = None
    ansible_userspace_bits: Optional[str] = None
    ansible_architecture: Optional[str] = None
    ansible_userspace_architecture: Optional[str] = None
    ansible_machine_id: Optional[str] = None

    def action_summary(self):
        return "gather platform facts"

    def action_run(self, system: transilience.system.System):
        super().action_run(system)
        # platform.system() can be Linux, Darwin, Java, or Windows
        self.ansible_system = platform.system()
        self.ansible_kernel = platform.release()
        self.ansible_kernel_version = platform.version()
        self.ansible_machine = platform.machine()

        self.ansible_python_version = platform.python_version()

        self.ansible_fqdn = socket.getfqdn()
        self.ansible_hostname = platform.node().split('.')[0]
        self.ansible_nodename = platform.node()

        self.ansible_domain = '.'.join(self.ansible_fqdn.split('.')[1:])

        arch_bits = platform.architecture()[0]

        self.ansible_userspace_bits = arch_bits.replace('bit', '')
        if self.ansible_machine == 'x86_64':
            self.ansible_architecture = self.ansible_machine
            if self.ansible_userspace_bits == '64':
                self.ansible_userspace_architecture = 'x86_64'
            elif self.ansible_userspace_bits == '32':
                self.ansible_userspace_architecture = 'i386'
        elif solaris_i86_re.search(self.ansible_machine):
            self.ansible_architecture = 'i386'
            if self.ansible_userspace_bits == '64':
                self.ansible_userspace_architecture = 'x86_64'
            elif self.ansible_userspace_bits == '32':
                self.ansible_userspace_architecture = 'i386'
        else:
            self.ansible_architecture = self.ansible_machine

        if self.ansible_system == 'AIX':
            # Attempt to use getconf to figure out architecture
            # fall back to bootinfo if needed
            getconf_bin = shutil.which('getconf')
            if getconf_bin:
                res = subprocess.run([getconf_bin, "MACHINE_ARCHITECTURE"], capture_output=True, text=True)
                if res.returncode == 0:
                    data = res.stdout.splitlines()
                    self.ansible_architecture = data[0]
            else:
                bootinfo_bin = shutil.which('bootinfo')
                if bootinfo_bin is not None:
                    res = subprocess.run([bootinfo_bin, '-p'], capture_output=True, text=True)
                    if res.returncode == 0:
                        data = res.stdout.splitlines()
                        self.ansible_architecture = data[0]
        elif self.ansible_system == 'OpenBSD':
            self.ansible_architecture = platform.uname()[5]

        machine_id = None
        for path in ("/var/lib/dbus/machine-id", "/etc/machine-id"):
            try:
                with open(path, "rt") as fd:
                    machine_id = next(fd).strip()
                break
            except FileNotFoundError:
                pass

        if machine_id:
            self.ansible_machine_id = machine_id
