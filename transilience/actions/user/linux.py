# Implementation adapter from Ansible's user module, which is Copyright: © 2012,
# Stephen Fromm <sfromm@gmail.com>, and licensed under the GNU General Public
# License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations
from . import backend


class Alpine(backend.User):
    """
    This is the class for use on systems that have adduser, deluser, and
    delgroup commands
    """
    # That was the original comment on Ansible, but then it was only
    # instantiated on Alpine, and indeed on Debian, the arguments passed to
    # adduser are wrong. Linux systems will go with backend.User's basic
    # implementation, except I guess, Alpine

    def create_user(self):
        cmd = [self.find_command('adduser')]

        cmd.append('-D')

        if self.uid is not None:
            cmd.append('-u')
            cmd.append(self.uid)

        if self.group is not None:
            if not self.group_exists(self.group):
                raise RuntimeError(f"Group {self.group!r} does not exist")
            cmd.append('-G')
            cmd.append(self.group)

        if self.comment is not None:
            cmd.append('-g')
            cmd.append(self.comment)

        if self.home is not None:
            cmd.append('-h')
            cmd.append(self.home)

        if self.shell is not None:
            cmd.append('-s')
            cmd.append(self.shell)

        if not self.create_home:
            cmd.append('-H')

        if self.skeleton is not None:
            cmd.append('-k')
            cmd.append(self.skeleton)

        # if self.umask is not None:
        #     cmd.append('-K')
        #     cmd.append('UMASK=' + self.umask)

        if self.system:
            cmd.append('-S')

        cmd.append(self.name)

        self.run_command(cmd)
        self.set_changed()

        if self.password is not None:
            cmd = [self.find_command("chpasswd")]
            cmd.append('--encrypted')
            data = f'{self.name}:{self.password}'
            self.run_command(cmd, input=data.encode())

        # Add to additional groups
        if self.groups:
            adduser_cmd = self.find_command("adduser")
            for group in self.get_groups_set():
                self.run_command([adduser_cmd, self.name, group])

    def remove_user(self):
        cmd = [self.find_command('deluser'), self.name]
        if self.remove:
            cmd.append('--remove-home')
        self.run_command(cmd)
        self.set_changed()

    def modify_user(self):
        current_groups = self.user_group_membership()
        groups = []
        info = self.user_info()
        add_cmd_bin = self.find_command('adduser')
        remove_cmd_bin = self.find_command('delgroup')

        # Manage group membership
        if self.groups:
            groups = self.get_groups_set()
            group_diff = current_groups.symmetric_difference(groups)

            if group_diff:
                for g in groups:
                    if g in group_diff:
                        self.run_command([add_cmd_bin, self.name, g])
                        self.set_changed()

                for g in group_diff:
                    if g not in groups and not self.append:
                        self.run_command([remove_cmd_bin, self.name, g])
                        self.set_changed()

        # Manage password
        if self.update_password == 'always' and self.password is not None and info[1] != self.password:
            cmd = [self.find_command('chpasswd'), '--encrypted']
            data = f'{self.name}:{self.password}'
            self.run_command(cmd, input=data)
            self.set_changed()
