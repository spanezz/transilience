# Implementation adapter from Ansible's user module, which is Copyright: © 2012,
# Stephen Fromm <sfromm@gmail.com>, and licensed under the GNU General Public
# License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import annotations
import time
import os
from . import backend


class User(backend.User):
    """
    This is a FreeBSD User manipulation class - it uses the pw command
    to manipulate the user database, followed by the chpass command
    to change the password.
    """
    def get_shadowfile(self):
        return '/etc/master.passwd'

    def get_shadowfile_expire_index(self):
        return 6

    def get_date_format(self):
        return '%d-%b-%Y'

    def _handle_lock(self):
        info = self.user_info()
        if self.action.password_lock and not info.pw_passwd.startswith('*LOCKED*'):
            cmd = [self.action.find_command('pw'), 'lock', self.action.name]
            if self.action.uid is not None and info.pw_uid != self.action.uid:
                cmd.append('-u')
                cmd.append(str(self.action.uid))
            self.action.run_change_command(cmd)
        elif self.action.password_lock is False and info.pw_passwd.startswith('*LOCKED*'):
            cmd = [self.action.find_command('pw'), 'unlock', self.action.name]
            if self.action.uid is not None and info.pw_uid != self.action.uid:
                cmd.append('-u')
                cmd.append(str(self.action.uid))
            self.action.run_change_command(cmd)

    def remove_user(self):
        cmd = [self.action.find_command("pw"), 'userdel', '-n', self.action.name]
        if self.action.remove:
            cmd.append('-r')
        self.action.run_change_command(cmd)

    def create_user(self):
        cmd = [self.action.find_command("pw"), 'useradd', '-n', self.action.name]

        if self.action.uid is not None:
            cmd.append('-u')
            cmd.append(str(self.action.uid))
            if self.action.non_unique:
                cmd.append('-o')

        if self.action.comment is not None:
            cmd.append('-c')
            cmd.append(self.action.comment)

        if self.action.home is not None:
            cmd.append('-d')
            cmd.append(self.action.home)

        if self.action.group is not None:
            if not self.group_exists(self.action.group):
                raise RuntimeError(f"Group {self.action.group!r} does not exist")
            cmd.append('-g')
            cmd.append(self.action.group)

        if self.action.groups is not None:
            groups = self.get_groups_set()
            cmd.append('-G')
            cmd.append(','.join(groups))

        if self.action.create_home:
            cmd.append('-m')

            if self.action.skeleton is not None:
                cmd.append('-k')
                cmd.append(self.action.skeleton)

            # if self.umask is not None:
            #     cmd.append('-K')
            #     cmd.append('UMASK=' + self.umask)

        if self.action.shell is not None:
            cmd.append('-s')
            cmd.append(self.action.shell)

        if self.action.login_class is not None:
            cmd.append('-L')
            cmd.append(self.action.login_class)

        if self.action.expires is not None:
            cmd.append('-e')
            if self.action.expires < 0:
                cmd.append('0')
            else:
                cmd.append(str(self.action.expires))

        # system cannot be handled currently - should we error if its requested?
        # create the user
        self.action.run_change_command(cmd)

        # we have to set the password in a second command
        if self.action.password is not None:
            cmd = [self.action.find_command('chpass'), '-p', self.action.password, self.action.name]
            self.action.run_change_command(cmd)

        # we have to lock/unlock the password in a distinct command
        self._handle_lock()

    def modify_user(self):
        cmd = [self.action.find_command("pw"), 'usermod', '-n', self.action.name]
        cmd_len = len(cmd)
        info = self.user_info()

        if self.action.uid is not None and info.pw_uid != self.action.uid:
            cmd.append('-u')
            cmd.append(str(self.action.uid))

            if self.action.non_unique:
                cmd.append('-o')

        if self.action.comment is not None and info.pw_gecos != self.action.comment:
            cmd.append('-c')
            cmd.append(self.action.comment)

        if self.action.home is not None:
            if ((info.pw_dir != self.action.home and self.action.move_home)
                    or (not os.path.exists(self.action.home) and self.action.create_home)):
                cmd.append('-m')
            if info.pw_dir != self.action.home:
                cmd.append('-d')
                cmd.append(self.action.home)

            if self.action.skeleton is not None:
                cmd.append('-k')
                cmd.append(self.action.skeleton)

            # if self.umask is not None:
            #     cmd.append('-K')
            #     cmd.append('UMASK=' + self.umask)

        if self.action.group is not None:
            if not self.group_exists(self.action.group):
                raise RuntimeError(f"Group {self.action.group!r} does not exist")
            ginfo = self.action.group_info(self.action.group)
            if info.pw_gid != ginfo.gr_gid:
                cmd.append('-g')
                cmd.append(self.action.group)

        if self.action.shell is not None and info.pw_shell != self.action.shell:
            cmd.append('-s')
            cmd.append(self.action.shell)

        if self.action.login_class is not None:
            # find current login class
            user_login_class = None
            shadowfile = self.get_shadowfile()
            if os.path.exists(shadowfile) and os.access(shadowfile, os.R_OK):
                with open(shadowfile, 'rt') as fd:
                    match = self.action.name + ":"
                    for line in fd:
                        if line.startswith(match):
                            user_login_class = line.split(':')[4]

            # act only if login_class change
            if self.action.login_class != user_login_class:
                cmd.append('-L')
                cmd.append(self.action.login_class)

        if self.action.groups is not None:
            current_groups = self.user_group_membership()
            groups = self.get_groups_set()

            group_diff = set(current_groups).symmetric_difference(groups)
            groups_need_mod = False

            if group_diff:
                if self.action.append:
                    for g in groups:
                        if g in group_diff:
                            groups_need_mod = True
                            break
                else:
                    groups_need_mod = True

            if groups_need_mod:
                cmd.append('-G')
                new_groups = groups
                if self.action.append:
                    new_groups = groups | set(current_groups)
                cmd.append(','.join(new_groups))

        if self.action.expires is not None:
            current_expires = int(self.user_password()[1])

            # If expiration is negative or zero and the current expiration is greater than zero, disable expiration.
            # In OpenBSD, setting expiration to zero disables expiration. It does not expire the account.
            if self.action.expires <= 0:
                if current_expires > 0:
                    cmd.append('-e')
                    cmd.append('0')
            else:
                # Convert days since Epoch to seconds since Epoch as struct_time
                current_expire_date = time.gmtime(current_expires)

                # Current expires is negative or we compare year, month, and day only
                if current_expires <= 0 or current_expire_date[:3] != time.gmtime(self.action.expires)[:3]:
                    cmd.append('-e')
                    cmd.append(str(self.action.expires))

        # modify the user if cmd will do anything
        if cmd_len != len(cmd):
            self.action.run_change_command(cmd)

        # we have to set the password in a second command
        if (self.action.update_password == 'always' and self.action.password is not None and
                info.pw_passwd.lstrip('*LOCKED*') != self.action.password.lstrip('*LOCKED*')):
            cmd = [self.action.find_command('chpass'), '-p', self.action.password, self.action.name]
            self.action.run_change_command(cmd)

        # we have to lock/unlock the password in a distinct command
        self._handle_lock()
