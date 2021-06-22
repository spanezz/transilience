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
        cmd = [self.action.find_command('adduser')]

        cmd.append('-D')

        if self.action.uid is not None:
            cmd.append('-u')
            cmd.append(self.action.uid)

        if self.action.group is not None:
            if not self.group_exists(self.action.group):
                raise RuntimeError(f"Group {self.action.group!r} does not exist")
            cmd.append('-G')
            cmd.append(self.action.group)

        if self.action.comment is not None:
            cmd.append('-g')
            cmd.append(self.action.comment)

        if self.action.home is not None:
            cmd.append('-h')
            cmd.append(self.action.home)

        if self.action.shell is not None:
            cmd.append('-s')
            cmd.append(self.action.shell)

        if not self.action.create_home:
            cmd.append('-H')

        if self.action.skeleton is not None:
            cmd.append('-k')
            cmd.append(self.action.skeleton)

        # if self.umask is not None:
        #     cmd.append('-K')
        #     cmd.append('UMASK=' + self.umask)

        if self.action.system:
            cmd.append('-S')

        cmd.append(self.action.name)

        self.action.run_change_command(cmd)

        if self.action.password is not None:
            cmd = [self.action.find_command("chpasswd")]
            cmd.append('--encrypted')
            data = f'{self.action.name}:{self.action.password}'
            self.action.run_change_command(cmd, input=data.encode())

        # Add to additional groups
        if self.action.groups:
            adduser_cmd = self.action.find_command("adduser")
            for group in self.get_groups_set():
                self.action.run_change_command([adduser_cmd, self.action.name, group])

    def remove_user(self):
        cmd = [self.action.find_command('deluser'), self.action.name]
        if self.action.remove:
            cmd.append('--remove-home')
        self.action.run_change_command(cmd)

    def modify_user(self):
        current_groups = self.user_group_membership()
        groups = []
        info = self.user_info()
        add_cmd_bin = self.action.find_command('adduser')
        remove_cmd_bin = self.action.find_command('delgroup')

        # Manage group membership
        if self.action.groups:
            groups = self.get_groups_set()
            group_diff = current_groups.symmetric_difference(groups)

            if group_diff:
                for g in groups:
                    if g in group_diff:
                        self.action.run_change_command([add_cmd_bin, self.action.name, g])

                for g in group_diff:
                    if g not in groups and not self.action.append:
                        self.action.run_change_command([remove_cmd_bin, self.action.name, g])

        # Manage password
        if (self.action.update_password == 'always'
                and self.action.password is not None
                and info[1] != self.action.password):
            cmd = [self.action.find_command('chpasswd'), '--encrypted']
            data = f'{self.action.name}:{self.action.password}'
            self.action.run_change_command(cmd, input=data)
