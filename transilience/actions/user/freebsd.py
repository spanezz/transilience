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
        if self.password_lock and not info.pw_passwd.startswith('*LOCKED*'):
            cmd = [self.find_command('pw'), 'lock', self.name]
            if self.uid is not None and info.pw_uid != self.uid:
                cmd.append('-u')
                cmd.append(str(self.uid))
            self.run_command(cmd)
            self.set_changed()
        elif self.password_lock is False and info.pw_passwd.startswith('*LOCKED*'):
            cmd = [self.find_command('pw'), 'unlock', self.name]
            if self.uid is not None and info.pw_uid != self.uid:
                cmd.append('-u')
                cmd.append(str(self.uid))
            self.run_command(cmd)
            self.set_changed()

    def remove_user(self):
        cmd = [self.find_command("pw"), 'userdel', '-n', self.name]
        if self.remove:
            cmd.append('-r')
        self.run_command(cmd)
        self.set_changed()

    def create_user(self):
        cmd = [self.find_command("pw"), 'useradd', '-n', self.name]

        if self.uid is not None:
            cmd.append('-u')
            cmd.append(str(self.uid))
            if self.non_unique:
                cmd.append('-o')

        if self.comment is not None:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None:
            cmd.append('-d')
            cmd.append(self.home)

        if self.group is not None:
            if not self.group_exists(self.group):
                raise RuntimeError(f"Group {self.group!r} does not exist")
            cmd.append('-g')
            cmd.append(self.group)

        if self.groups is not None:
            groups = self.get_groups_set()
            cmd.append('-G')
            cmd.append(','.join(groups))

        if self.create_home:
            cmd.append('-m')

            if self.skeleton is not None:
                cmd.append('-k')
                cmd.append(self.skeleton)

            # if self.umask is not None:
            #     cmd.append('-K')
            #     cmd.append('UMASK=' + self.umask)

        if self.shell is not None:
            cmd.append('-s')
            cmd.append(self.shell)

        if self.login_class is not None:
            cmd.append('-L')
            cmd.append(self.login_class)

        if self.expires is not None:
            cmd.append('-e')
            if self.expires < 0:
                cmd.append('0')
            else:
                cmd.append(str(self.expires))

        # system cannot be handled currently - should we error if its requested?
        # create the user
        self.run_command(cmd)
        self.set_changed()

        # we have to set the password in a second command
        if self.password is not None:
            cmd = [self.find_command('chpass'), '-p', self.password, self.name]
            self.run_command(cmd)

        # we have to lock/unlock the password in a distinct command
        self._handle_lock()

    def modify_user(self):
        cmd = [self.find_command("pw"), 'usermod', '-n', self.name]
        cmd_len = len(cmd)
        info = self.user_info()

        if self.uid is not None and info.pw_uid != self.uid:
            cmd.append('-u')
            cmd.append(str(self.uid))

            if self.non_unique:
                cmd.append('-o')

        if self.comment is not None and info.pw_gecos != self.comment:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None:
            if (info.pw_dir != self.home and self.move_home) or (not os.path.exists(self.home) and self.create_home):
                cmd.append('-m')
            if info.pw_dir != self.home:
                cmd.append('-d')
                cmd.append(self.home)

            if self.skeleton is not None:
                cmd.append('-k')
                cmd.append(self.skeleton)

            # if self.umask is not None:
            #     cmd.append('-K')
            #     cmd.append('UMASK=' + self.umask)

        if self.group is not None:
            if not self.group_exists(self.group):
                raise RuntimeError(f"Group {self.group!r} does not exist")
            ginfo = self.group_info(self.group)
            if info.pw_gid != ginfo.gr_gid:
                cmd.append('-g')
                cmd.append(self.group)

        if self.shell is not None and info.pw_shell != self.shell:
            cmd.append('-s')
            cmd.append(self.shell)

        if self.login_class is not None:
            # find current login class
            user_login_class = None
            shadowfile = self.get_shadowfile()
            if os.path.exists(shadowfile) and os.access(shadowfile, os.R_OK):
                with open(shadowfile, 'rt') as fd:
                    match = self.name + ":"
                    for line in fd:
                        if line.startswith(match):
                            user_login_class = line.split(':')[4]

            # act only if login_class change
            if self.login_class != user_login_class:
                cmd.append('-L')
                cmd.append(self.login_class)

        if self.groups is not None:
            current_groups = self.user_group_membership()
            groups = self.get_groups_set()

            group_diff = set(current_groups).symmetric_difference(groups)
            groups_need_mod = False

            if group_diff:
                if self.append:
                    for g in groups:
                        if g in group_diff:
                            groups_need_mod = True
                            break
                else:
                    groups_need_mod = True

            if groups_need_mod:
                cmd.append('-G')
                new_groups = groups
                if self.append:
                    new_groups = groups | set(current_groups)
                cmd.append(','.join(new_groups))

        if self.expires is not None:
            current_expires = int(self.user_password()[1])

            # If expiration is negative or zero and the current expiration is greater than zero, disable expiration.
            # In OpenBSD, setting expiration to zero disables expiration. It does not expire the account.
            if self.expires <= 0:
                if current_expires > 0:
                    cmd.append('-e')
                    cmd.append('0')
            else:
                # Convert days since Epoch to seconds since Epoch as struct_time
                current_expire_date = time.gmtime(current_expires)

                # Current expires is negative or we compare year, month, and day only
                if current_expires <= 0 or current_expire_date[:3] != time.gmtime(self.expires)[:3]:
                    cmd.append('-e')
                    cmd.append(str(self.expires))

        # modify the user if cmd will do anything
        if cmd_len != len(cmd):
            self.run_command(cmd)
            self.set_changed()

        # we have to set the password in a second command
        if (self.update_password == 'always' and self.password is not None and
                info.pw_passwd.lstrip('*LOCKED*') != self.password.lstrip('*LOCKED*')):
            cmd = [self.find_command('chpass'), '-p', self.password, self.name]
            self.run_command(cmd)

        # we have to lock/unlock the password in a distinct command
        self._handle_lock()
