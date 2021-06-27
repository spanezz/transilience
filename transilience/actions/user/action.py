from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List
from dataclasses import dataclass, field
import platform
import shlex
import os
from .. import builtin
from ..action import Action

if TYPE_CHECKING:
    import transilience.system
    from . import backend


@builtin.action(name="user")
@dataclass
class User(Action):
    """
    Same as Ansible's
    [builtin.user](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/user_module.html)
    """
    name: Optional[str] = None
    state: str = "present"
    uid: Optional[int] = None
    hidden: Optional[bool] = None
    non_unique: bool = False
    seuser: Optional[str] = None
    group: Optional[str] = None
    groups: List[str] = field(default_factory=list)
    comment: Optional[str] = None
    shell: Optional[str] = None
    password: Optional[str] = None
    password_expire_max: Optional[int] = None
    password_expire_min: Optional[int] = None
    password_lock: Optional[bool] = None
    force: bool = False
    remove: bool = False
    create_home: bool = True
    move_home: bool = False
    skeleton: Optional[str] = None
    system: bool = False
    login_class: Optional[str] = None
    append: bool = False
    generate_ssh_key: bool = False
    ssh_key_bits: Optional[int] = None
    ssh_key_comment: Optional[str] = None
    ssh_key_file: Optional[str] = None
    ssh_key_passphrase: Optional[str] = None
    ssh_key_type: str = "rsa"
    ssh_key_fingerprint: Optional[str] = None  # Result only
    ssh_key_pubkey: Optional[str] = None  # Result only
    authorization: Optional[str] = None
    home: Optional[str] = None
    expires: Optional[float] = None
    local: bool = False
    profile: Optional[str] = None
    role: Optional[str] = None
    update_password: str = "always"

    def __post_init__(self):
        super().__post_init__()
        if self.name is None:
            raise TypeError(f"{self.__class__}.name cannot be None")

        # FIXME: not documented?
        # self.umask = module.params['umask']
        # if self.umask is not None and self.local:
        #     module.fail_json(msg="'umask' can not be used with 'local'")

        # if self.expires is not None:
        #     try:
        #         self.expires = time.gmtime(module.params['expires'])
        #     except Exception as e:
        #         module.fail_json(msg="Invalid value for 'expires' %s: %s" % (self.expires, to_native(e)))

        if self.ssh_key_file is None:
            self.ssh_key_file = os.path.join(".ssh", f"id_{self.ssh_key_type}")

        if not self.groups and self.append:
            raise ValueError("'append' is set, but no 'groups' are specified. Use 'groups' for appending new groups")

    def action_summary(self):
        if self.state == 'absent':
            return f"Remove user {self.name!r}"
        else:
            return f"Create user {self.name!r}"

    def get_backend(self) -> backend.Generic:
        system = platform.system()
        if system == "Linux":
            distribution: Optional[str]
            try:
                with open("/etc/os-release", "rt") as fd:
                    for line in fd:
                        k, v = line.split("=", 1)
                        if k == "ID":
                            distribution = shlex.split(v)[0]
                            break
                    else:
                        distribution = None
            except FileNotFoundError:
                distribution = None

            if distribution == "alpine":
                from . import linux
                return linux.Alpine(self)
            else:
                from . import backend
                return backend.Generic(self)
        if system in ('FreeBSD', 'DragonFly'):
            from . import freebsd
            return freebsd.Generic(self)
        else:
            raise NotImplementedError(f"User backend for {system!r} platform is not available")

    def run_change_command(self, cmd: List[str], input: Optional[bytes] = None):
        if not self.check:
            self.run_command(cmd, input=input)
        self.set_changed()

    def run(self, system: transilience.system.System):
        super().run(system)

        backend = self.get_backend()

        backend.check_password_encrypted()

        if self.state == 'absent':
            backend.do_absent()
        elif self.state == 'present':
            backend.do_present()

        if backend.user_exists() and self.state == 'present':
            backend.do_update()

        # deal with password expire max
        if self.password_expire_max:
            if backend.user_exists():
                backend.set_password_expire_max()

        # deal with password expire min
        if self.password_expire_min:
            if backend.user_exists():
                backend.set_password_expire_min()
