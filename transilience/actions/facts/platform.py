from __future__ import annotations
from typing import TYPE_CHECKING
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
    def summary(self):
        return "gather platform facts"

    def run(self, system: transilience.system.System):
        super().run(system)
        facts = {}
        # platform.system() can be Linux, Darwin, Java, or Windows
        facts['system'] = platform.system()
        facts['kernel'] = platform.release()
        facts['kernel_version'] = platform.version()
        facts['machine'] = platform.machine()

        facts['python_version'] = platform.python_version()

        facts['fqdn'] = socket.getfqdn()
        facts['hostname'] = platform.node().split('.')[0]
        facts['nodename'] = platform.node()

        facts['domain'] = '.'.join(facts['fqdn'].split('.')[1:])

        arch_bits = platform.architecture()[0]

        facts['userspace_bits'] = arch_bits.replace('bit', '')
        if facts['machine'] == 'x86_64':
            facts['architecture'] = facts['machine']
            if facts['userspace_bits'] == '64':
                facts['userspace_architecture'] = 'x86_64'
            elif facts['userspace_bits'] == '32':
                facts['userspace_architecture'] = 'i386'
        elif solaris_i86_re.search(facts['machine']):
            facts['architecture'] = 'i386'
            if facts['userspace_bits'] == '64':
                facts['userspace_architecture'] = 'x86_64'
            elif facts['userspace_bits'] == '32':
                facts['userspace_architecture'] = 'i386'
        else:
            facts['architecture'] = facts['machine']

        if facts['system'] == 'AIX':
            # Attempt to use getconf to figure out architecture
            # fall back to bootinfo if needed
            getconf_bin = shutil.which('getconf')
            if getconf_bin:
                res = subprocess.run([getconf_bin, "MACHINE_ARCHITECTURE"], capture_output=True, text=True)
                if res.returncode == 0:
                    data = res.stdout.splitlines()
                    facts['architecture'] = data[0]
            else:
                bootinfo_bin = shutil.which('bootinfo')
                if bootinfo_bin is not None:
                    res = subprocess.run([bootinfo_bin, '-p'], capture_output=True, text=True)
                    if res.returncode == 0:
                        data = res.stdout.splitlines()
                        facts['architecture'] = data[0]
        elif facts['system'] == 'OpenBSD':
            facts['architecture'] = platform.uname()[5]

        machine_id = None
        for path in ("/var/lib/dbus/machine-id", "/etc/machine-id"):
            try:
                with open(path, "rt") as fd:
                    machine_id = next(fd).strip()
                break
            except FileNotFoundError:
                pass

        if machine_id:
            facts["machine_id"] = machine_id

        self.facts = facts
