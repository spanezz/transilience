# TODO: user backends from Ansible that have not been ported to transilience yet

# Copyright: (c) 2012, Stephen Fromm <sfromm@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import errno
import grp
import calendar
import os
import re
import pty
import pwd
import select
import shutil
import socket
import subprocess
import time
import math

from ansible.module_utils import distro
from ansible.module_utils._text import to_bytes, to_native, to_text
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.sys_info import get_platform_subclass

try:
    import spwd
    HAVE_SPWD = True
except ImportError:
    HAVE_SPWD = False


_HASH_RE = re.compile(r'[^a-zA-Z0-9./=]')


# ===========================================

class OpenBSDUser(User):
    """
    This is a OpenBSD User manipulation class.
    Main differences are that OpenBSD:-
     - has no concept of "system" account.
     - has no force delete user

    This overrides the following methods from the generic class:-
      - create_user()
      - remove_user()
      - modify_user()
    """

    platform = 'OpenBSD'
    distribution = None
    SHADOWFILE = '/etc/master.passwd'

    def create_user(self):
        cmd = [self.module.get_bin_path('useradd', True)]

        if self.uid is not None:
            cmd.append('-u')
            cmd.append(self.uid)

            if self.non_unique:
                cmd.append('-o')

        if self.group is not None:
            if not self.group_exists(self.group):
                self.module.fail_json(msg="Group %s does not exist" % self.group)
            cmd.append('-g')
            cmd.append(self.group)

        if self.groups is not None:
            groups = self.get_groups_set()
            cmd.append('-G')
            cmd.append(','.join(groups))

        if self.comment is not None:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None:
            cmd.append('-d')
            cmd.append(self.home)

        if self.shell is not None:
            cmd.append('-s')
            cmd.append(self.shell)

        if self.login_class is not None:
            cmd.append('-L')
            cmd.append(self.login_class)

        if self.password is not None and self.password != '*':
            cmd.append('-p')
            cmd.append(self.password)

        if self.create_home:
            cmd.append('-m')

            if self.skeleton is not None:
                cmd.append('-k')
                cmd.append(self.skeleton)

            if self.umask is not None:
                cmd.append('-K')
                cmd.append('UMASK=' + self.umask)

        cmd.append(self.name)
        return self.execute_command(cmd)

    def remove_user_userdel(self):
        cmd = [self.module.get_bin_path('userdel', True)]
        if self.remove:
            cmd.append('-r')
        cmd.append(self.name)
        return self.execute_command(cmd)

    def modify_user(self):
        cmd = [self.module.get_bin_path('usermod', True)]
        info = self.user_info()

        if self.uid is not None and info[2] != int(self.uid):
            cmd.append('-u')
            cmd.append(self.uid)

            if self.non_unique:
                cmd.append('-o')

        if self.group is not None:
            if not self.group_exists(self.group):
                self.module.fail_json(msg="Group %s does not exist" % self.group)
            ginfo = self.group_info(self.group)
            if info[3] != ginfo[2]:
                cmd.append('-g')
                cmd.append(self.group)

        if self.groups is not None:
            current_groups = self.user_group_membership()
            groups_need_mod = False
            groups_option = '-S'
            groups = []

            if self.groups == '':
                if current_groups and not self.append:
                    groups_need_mod = True
            else:
                groups = self.get_groups_set()
                group_diff = set(current_groups).symmetric_difference(groups)

                if group_diff:
                    if self.append:
                        for g in groups:
                            if g in group_diff:
                                groups_option = '-G'
                                groups_need_mod = True
                                break
                    else:
                        groups_need_mod = True

            if groups_need_mod:
                cmd.append(groups_option)
                cmd.append(','.join(groups))

        if self.comment is not None and info[4] != self.comment:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None and info[5] != self.home:
            if self.move_home:
                cmd.append('-m')
            cmd.append('-d')
            cmd.append(self.home)

        if self.shell is not None and info[6] != self.shell:
            cmd.append('-s')
            cmd.append(self.shell)

        if self.login_class is not None:
            # find current login class
            user_login_class = None
            userinfo_cmd = [self.module.get_bin_path('userinfo', True), self.name]
            (rc, out, err) = self.execute_command(userinfo_cmd, obey_checkmode=False)

            for line in out.splitlines():
                tokens = line.split()

                if tokens[0] == 'class' and len(tokens) == 2:
                    user_login_class = tokens[1]

            # act only if login_class change
            if self.login_class != user_login_class:
                cmd.append('-L')
                cmd.append(self.login_class)

        if self.password_lock and not info[1].startswith('*'):
            cmd.append('-Z')
        elif self.password_lock is False and info[1].startswith('*'):
            cmd.append('-U')

        if self.update_password == 'always' and self.password is not None \
                and self.password != '*' and info[1] != self.password:
            cmd.append('-p')
            cmd.append(self.password)

        # skip if no changes to be made
        if len(cmd) == 1:
            return (None, '', '')

        cmd.append(self.name)
        return self.execute_command(cmd)


class NetBSDUser(User):
    """
    This is a NetBSD User manipulation class.
    Main differences are that NetBSD:-
     - has no concept of "system" account.
     - has no force delete user


    This overrides the following methods from the generic class:-
      - create_user()
      - remove_user()
      - modify_user()
    """

    platform = 'NetBSD'
    distribution = None
    SHADOWFILE = '/etc/master.passwd'

    def create_user(self):
        cmd = [self.module.get_bin_path('useradd', True)]

        if self.uid is not None:
            cmd.append('-u')
            cmd.append(self.uid)

            if self.non_unique:
                cmd.append('-o')

        if self.group is not None:
            if not self.group_exists(self.group):
                self.module.fail_json(msg="Group %s does not exist" % self.group)
            cmd.append('-g')
            cmd.append(self.group)

        if self.groups is not None:
            groups = self.get_groups_set()
            if len(groups) > 16:
                self.module.fail_json(msg="Too many groups (%d) NetBSD allows for 16 max." % len(groups))
            cmd.append('-G')
            cmd.append(','.join(groups))

        if self.comment is not None:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None:
            cmd.append('-d')
            cmd.append(self.home)

        if self.shell is not None:
            cmd.append('-s')
            cmd.append(self.shell)

        if self.login_class is not None:
            cmd.append('-L')
            cmd.append(self.login_class)

        if self.password is not None:
            cmd.append('-p')
            cmd.append(self.password)

        if self.create_home:
            cmd.append('-m')

            if self.skeleton is not None:
                cmd.append('-k')
                cmd.append(self.skeleton)

            if self.umask is not None:
                cmd.append('-K')
                cmd.append('UMASK=' + self.umask)

        cmd.append(self.name)
        return self.execute_command(cmd)

    def remove_user_userdel(self):
        cmd = [self.module.get_bin_path('userdel', True)]
        if self.remove:
            cmd.append('-r')
        cmd.append(self.name)
        return self.execute_command(cmd)

    def modify_user(self):
        cmd = [self.module.get_bin_path('usermod', True)]
        info = self.user_info()

        if self.uid is not None and info[2] != int(self.uid):
            cmd.append('-u')
            cmd.append(self.uid)

            if self.non_unique:
                cmd.append('-o')

        if self.group is not None:
            if not self.group_exists(self.group):
                self.module.fail_json(msg="Group %s does not exist" % self.group)
            ginfo = self.group_info(self.group)
            if info[3] != ginfo[2]:
                cmd.append('-g')
                cmd.append(self.group)

        if self.groups is not None:
            current_groups = self.user_group_membership()
            groups_need_mod = False
            groups = []

            if self.groups == '':
                if current_groups and not self.append:
                    groups_need_mod = True
            else:
                groups = self.get_groups_set()
                group_diff = set(current_groups).symmetric_difference(groups)

                if group_diff:
                    if self.append:
                        for g in groups:
                            if g in group_diff:
                                groups = set(current_groups).union(groups)
                                groups_need_mod = True
                                break
                    else:
                        groups_need_mod = True

            if groups_need_mod:
                if len(groups) > 16:
                    self.module.fail_json(msg="Too many groups (%d) NetBSD allows for 16 max." % len(groups))
                cmd.append('-G')
                cmd.append(','.join(groups))

        if self.comment is not None and info[4] != self.comment:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None and info[5] != self.home:
            if self.move_home:
                cmd.append('-m')
            cmd.append('-d')
            cmd.append(self.home)

        if self.shell is not None and info[6] != self.shell:
            cmd.append('-s')
            cmd.append(self.shell)

        if self.login_class is not None:
            cmd.append('-L')
            cmd.append(self.login_class)

        if self.update_password == 'always' and self.password is not None and info[1] != self.password:
            cmd.append('-p')
            cmd.append(self.password)

        if self.password_lock and not info[1].startswith('*LOCKED*'):
            cmd.append('-C yes')
        elif self.password_lock is False and info[1].startswith('*LOCKED*'):
            cmd.append('-C no')

        # skip if no changes to be made
        if len(cmd) == 1:
            return (None, '', '')

        cmd.append(self.name)
        return self.execute_command(cmd)


class SunOS(User):
    """
    This is a SunOS User manipulation class - The main difference between
    this class and the generic user class is that Solaris-type distros
    don't support the concept of a "system" account and we need to
    edit the /etc/shadow file manually to set a password. (Ugh)

    This overrides the following methods from the generic class:-
      - create_user()
      - remove_user()
      - modify_user()
      - user_info()
    """

    platform = 'SunOS'
    distribution = None
    SHADOWFILE = '/etc/shadow'
    USER_ATTR = '/etc/user_attr'

    def get_password_defaults(self):
        # Read password aging defaults
        try:
            minweeks = ''
            maxweeks = ''
            warnweeks = ''
            with open("/etc/default/passwd", 'r') as f:
                for line in f:
                    line = line.strip()
                    if (line.startswith('#') or line == ''):
                        continue
                    m = re.match(r'^([^#]*)#(.*)$', line)
                    if m:  # The line contains a hash / comment
                        line = m.group(1)
                    key, value = line.split('=')
                    if key == "MINWEEKS":
                        minweeks = value.rstrip('\n')
                    elif key == "MAXWEEKS":
                        maxweeks = value.rstrip('\n')
                    elif key == "WARNWEEKS":
                        warnweeks = value.rstrip('\n')
        except Exception as err:
            self.module.fail_json(msg="failed to read /etc/default/passwd: %s" % to_native(err))

        return (minweeks, maxweeks, warnweeks)

    def remove_user(self):
        cmd = [self.module.get_bin_path('userdel', True)]
        if self.remove:
            cmd.append('-r')
        cmd.append(self.name)

        return self.execute_command(cmd)

    def create_user(self):
        cmd = [self.module.get_bin_path('useradd', True)]

        if self.uid is not None:
            cmd.append('-u')
            cmd.append(self.uid)

            if self.non_unique:
                cmd.append('-o')

        if self.group is not None:
            if not self.group_exists(self.group):
                self.module.fail_json(msg="Group %s does not exist" % self.group)
            cmd.append('-g')
            cmd.append(self.group)

        if self.groups is not None:
            groups = self.get_groups_set()
            cmd.append('-G')
            cmd.append(','.join(groups))

        if self.comment is not None:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None:
            cmd.append('-d')
            cmd.append(self.home)

        if self.shell is not None:
            cmd.append('-s')
            cmd.append(self.shell)

        if self.create_home:
            cmd.append('-m')

            if self.skeleton is not None:
                cmd.append('-k')
                cmd.append(self.skeleton)

            if self.umask is not None:
                cmd.append('-K')
                cmd.append('UMASK=' + self.umask)

        if self.profile is not None:
            cmd.append('-P')
            cmd.append(self.profile)

        if self.authorization is not None:
            cmd.append('-A')
            cmd.append(self.authorization)

        if self.role is not None:
            cmd.append('-R')
            cmd.append(self.role)

        cmd.append(self.name)

        (rc, out, err) = self.execute_command(cmd)
        if rc is not None and rc != 0:
            self.module.fail_json(name=self.name, msg=err, rc=rc)

        if not self.module.check_mode:
            # we have to set the password by editing the /etc/shadow file
            if self.password is not None:
                self.backup_shadow()
                minweeks, maxweeks, warnweeks = self.get_password_defaults()
                try:
                    lines = []
                    with open(self.SHADOWFILE, 'rb') as f:
                        for line in f:
                            line = to_native(line, errors='surrogate_or_strict')
                            fields = line.strip().split(':')
                            if not fields[0] == self.name:
                                lines.append(line)
                                continue
                            fields[1] = self.password
                            fields[2] = str(int(time.time() // 86400))
                            if minweeks:
                                try:
                                    fields[3] = str(int(minweeks) * 7)
                                except ValueError:
                                    # mirror solaris, which allows for any value in this field, and ignores anything that is not an int.
                                    pass
                            if maxweeks:
                                try:
                                    fields[4] = str(int(maxweeks) * 7)
                                except ValueError:
                                    # mirror solaris, which allows for any value in this field, and ignores anything that is not an int.
                                    pass
                            if warnweeks:
                                try:
                                    fields[5] = str(int(warnweeks) * 7)
                                except ValueError:
                                    # mirror solaris, which allows for any value in this field, and ignores anything that is not an int.
                                    pass
                            line = ':'.join(fields)
                            lines.append('%s\n' % line)
                    with open(self.SHADOWFILE, 'w+') as f:
                        f.writelines(lines)
                except Exception as err:
                    self.module.fail_json(msg="failed to update users password: %s" % to_native(err))

        return (rc, out, err)

    def modify_user_usermod(self):
        cmd = [self.module.get_bin_path('usermod', True)]
        cmd_len = len(cmd)
        info = self.user_info()

        if self.uid is not None and info[2] != int(self.uid):
            cmd.append('-u')
            cmd.append(self.uid)

            if self.non_unique:
                cmd.append('-o')

        if self.group is not None:
            if not self.group_exists(self.group):
                self.module.fail_json(msg="Group %s does not exist" % self.group)
            ginfo = self.group_info(self.group)
            if info[3] != ginfo[2]:
                cmd.append('-g')
                cmd.append(self.group)

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
                    new_groups.update(current_groups)
                cmd.append(','.join(new_groups))

        if self.comment is not None and info[4] != self.comment:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None and info[5] != self.home:
            if self.move_home:
                cmd.append('-m')
            cmd.append('-d')
            cmd.append(self.home)

        if self.shell is not None and info[6] != self.shell:
            cmd.append('-s')
            cmd.append(self.shell)

        if self.profile is not None and info[7] != self.profile:
            cmd.append('-P')
            cmd.append(self.profile)

        if self.authorization is not None and info[8] != self.authorization:
            cmd.append('-A')
            cmd.append(self.authorization)

        if self.role is not None and info[9] != self.role:
            cmd.append('-R')
            cmd.append(self.role)

        # modify the user if cmd will do anything
        if cmd_len != len(cmd):
            cmd.append(self.name)
            (rc, out, err) = self.execute_command(cmd)
            if rc is not None and rc != 0:
                self.module.fail_json(name=self.name, msg=err, rc=rc)
        else:
            (rc, out, err) = (None, '', '')

        # we have to set the password by editing the /etc/shadow file
        if self.update_password == 'always' and self.password is not None and info[1] != self.password:
            self.backup_shadow()
            (rc, out, err) = (0, '', '')
            if not self.module.check_mode:
                minweeks, maxweeks, warnweeks = self.get_password_defaults()
                try:
                    lines = []
                    with open(self.SHADOWFILE, 'rb') as f:
                        for line in f:
                            line = to_native(line, errors='surrogate_or_strict')
                            fields = line.strip().split(':')
                            if not fields[0] == self.name:
                                lines.append(line)
                                continue
                            fields[1] = self.password
                            fields[2] = str(int(time.time() // 86400))
                            if minweeks:
                                fields[3] = str(int(minweeks) * 7)
                            if maxweeks:
                                fields[4] = str(int(maxweeks) * 7)
                            if warnweeks:
                                fields[5] = str(int(warnweeks) * 7)
                            line = ':'.join(fields)
                            lines.append('%s\n' % line)
                    with open(self.SHADOWFILE, 'w+') as f:
                        f.writelines(lines)
                    rc = 0
                except Exception as err:
                    self.module.fail_json(msg="failed to update users password: %s" % to_native(err))

        return (rc, out, err)

    def user_info(self):
        info = super(SunOS, self).user_info()
        if info:
            info += self._user_attr_info()
        return info

    def _user_attr_info(self):
        info = [''] * 3
        with open(self.USER_ATTR, 'r') as file_handler:
            for line in file_handler:
                lines = line.strip().split('::::')
                if lines[0] == self.name:
                    tmp = dict(x.split('=') for x in lines[1].split(';'))
                    info[0] = tmp.get('profiles', '')
                    info[1] = tmp.get('auths', '')
                    info[2] = tmp.get('roles', '')
        return info


class DarwinUser(User):
    """
    This is a Darwin macOS User manipulation class.
    Main differences are that Darwin:-
      - Handles accounts in a database managed by dscl(1)
      - Has no useradd/groupadd
      - Does not create home directories
      - User password must be cleartext
      - UID must be given
      - System users must ben under 500

    This overrides the following methods from the generic class:-
      - user_exists()
      - create_user()
      - remove_user()
      - modify_user()
    """
    platform = 'Darwin'
    distribution = None
    SHADOWFILE = None

    dscl_directory = '.'

    fields = [
        ('comment', 'RealName'),
        ('home', 'NFSHomeDirectory'),
        ('shell', 'UserShell'),
        ('uid', 'UniqueID'),
        ('group', 'PrimaryGroupID'),
        ('hidden', 'IsHidden'),
    ]

    def __init__(self, module):

        super(DarwinUser, self).__init__(module)

        # make the user hidden if option is set or deffer to system option
        if self.hidden is None:
            if self.system:
                self.hidden = 1
        elif self.hidden:
            self.hidden = 1
        else:
            self.hidden = 0

        # add hidden to processing if set
        if self.hidden is not None:
            self.fields.append(('hidden', 'IsHidden'))

    def _get_dscl(self):
        return [self.module.get_bin_path('dscl', True), self.dscl_directory]

    def _list_user_groups(self):
        cmd = self._get_dscl()
        cmd += ['-search', '/Groups', 'GroupMembership', self.name]
        (rc, out, err) = self.execute_command(cmd, obey_checkmode=False)
        groups = []
        for line in out.splitlines():
            if line.startswith(' ') or line.startswith(')'):
                continue
            groups.append(line.split()[0])
        return groups

    def _get_user_property(self, property):
        '''Return user PROPERTY as given my dscl(1) read or None if not found.'''
        cmd = self._get_dscl()
        cmd += ['-read', '/Users/%s' % self.name, property]
        (rc, out, err) = self.execute_command(cmd, obey_checkmode=False)
        if rc != 0:
            return None
        # from dscl(1)
        # if property contains embedded spaces, the list will instead be
        # displayed one entry per line, starting on the line after the key.
        lines = out.splitlines()
        # sys.stderr.write('*** |%s| %s -> %s\n' %  (property, out, lines))
        if len(lines) == 1:
            return lines[0].split(': ')[1]
        else:
            if len(lines) > 2:
                return '\n'.join([lines[1].strip()] + lines[2:])
            else:
                if len(lines) == 2:
                    return lines[1].strip()
                else:
                    return None

    def _get_next_uid(self, system=None):
        '''
        Return the next available uid. If system=True, then
        uid should be below of 500, if possible.
        '''
        cmd = self._get_dscl()
        cmd += ['-list', '/Users', 'UniqueID']
        (rc, out, err) = self.execute_command(cmd, obey_checkmode=False)
        if rc != 0:
            self.module.fail_json(
                msg="Unable to get the next available uid",
                rc=rc,
                out=out,
                err=err
            )

        max_uid = 0
        max_system_uid = 0
        for line in out.splitlines():
            current_uid = int(line.split(' ')[-1])
            if max_uid < current_uid:
                max_uid = current_uid
            if max_system_uid < current_uid and current_uid < 500:
                max_system_uid = current_uid

        if system and (0 < max_system_uid < 499):
            return max_system_uid + 1
        return max_uid + 1

    def _change_user_password(self):
        '''Change password for SELF.NAME against SELF.PASSWORD.

        Please note that password must be cleartext.
        '''
        # some documentation on how is stored passwords on OSX:
        # http://blog.lostpassword.com/2012/07/cracking-mac-os-x-lion-accounts-passwords/
        # http://null-byte.wonderhowto.com/how-to/hack-mac-os-x-lion-passwords-0130036/
        # http://pastebin.com/RYqxi7Ca
        # on OSX 10.8+ hash is SALTED-SHA512-PBKDF2
        # https://pythonhosted.org/passlib/lib/passlib.hash.pbkdf2_digest.html
        # https://gist.github.com/nueh/8252572
        cmd = self._get_dscl()
        if self.password:
            cmd += ['-passwd', '/Users/%s' % self.name, self.password]
        else:
            cmd += ['-create', '/Users/%s' % self.name, 'Password', '*']
        (rc, out, err) = self.execute_command(cmd)
        if rc != 0:
            self.module.fail_json(msg='Error when changing password', err=err, out=out, rc=rc)
        return (rc, out, err)

    def _make_group_numerical(self):
        '''Convert SELF.GROUP to is stringed numerical value suitable for dscl.'''
        if self.group is None:
            self.group = 'nogroup'
        try:
            self.group = grp.getgrnam(self.group).gr_gid
        except KeyError:
            self.module.fail_json(msg='Group "%s" not found. Try to create it first using "group" module.' % self.group)
        # We need to pass a string to dscl
        self.group = str(self.group)

    def __modify_group(self, group, action):
        '''Add or remove SELF.NAME to or from GROUP depending on ACTION.
        ACTION can be 'add' or 'remove' otherwise 'remove' is assumed. '''
        if action == 'add':
            option = '-a'
        else:
            option = '-d'
        cmd = ['dseditgroup', '-o', 'edit', option, self.name, '-t', 'user', group]
        (rc, out, err) = self.execute_command(cmd)
        if rc != 0:
            self.module.fail_json(msg='Cannot %s user "%s" to group "%s".'
                                      % (action, self.name, group), err=err, out=out, rc=rc)
        return (rc, out, err)

    def _modify_group(self):
        '''Add or remove SELF.NAME to or from GROUP depending on ACTION.
        ACTION can be 'add' or 'remove' otherwise 'remove' is assumed. '''

        rc = 0
        out = ''
        err = ''
        changed = False

        current = set(self._list_user_groups())
        if self.groups is not None:
            target = set(self.groups.split(','))
        else:
            target = set([])

        if self.append is False:
            for remove in current - target:
                (_rc, _out, _err) = self.__modify_group(remove, 'delete')
                rc += rc
                out += _out
                err += _err
                changed = True

        for add in target - current:
            (_rc, _out, _err) = self.__modify_group(add, 'add')
            rc += _rc
            out += _out
            err += _err
            changed = True

        return (rc, out, err, changed)

    def _update_system_user(self):
        '''Hide or show user on login window according SELF.SYSTEM.

        Returns 0 if a change has been made, None otherwise.'''

        plist_file = '/Library/Preferences/com.apple.loginwindow.plist'

        # http://support.apple.com/kb/HT5017?viewlocale=en_US
        cmd = ['defaults', 'read', plist_file, 'HiddenUsersList']
        (rc, out, err) = self.execute_command(cmd, obey_checkmode=False)
        # returned value is
        # (
        #   "_userA",
        #   "_UserB",
        #   userc
        # )
        hidden_users = []
        for x in out.splitlines()[1:-1]:
            try:
                x = x.split('"')[1]
            except IndexError:
                x = x.strip()
            hidden_users.append(x)

        if self.system:
            if self.name not in hidden_users:
                cmd = ['defaults', 'write', plist_file, 'HiddenUsersList', '-array-add', self.name]
                (rc, out, err) = self.execute_command(cmd)
                if rc != 0:
                    self.module.fail_json(msg='Cannot user "%s" to hidden user list.' % self.name, err=err, out=out, rc=rc)
                return 0
        else:
            if self.name in hidden_users:
                del (hidden_users[hidden_users.index(self.name)])

                cmd = ['defaults', 'write', plist_file, 'HiddenUsersList', '-array'] + hidden_users
                (rc, out, err) = self.execute_command(cmd)
                if rc != 0:
                    self.module.fail_json(msg='Cannot remove user "%s" from hidden user list.' % self.name, err=err, out=out, rc=rc)
                return 0

    def user_exists(self):
        '''Check is SELF.NAME is a known user on the system.'''
        cmd = self._get_dscl()
        cmd += ['-list', '/Users/%s' % self.name]
        (rc, out, err) = self.execute_command(cmd, obey_checkmode=False)
        return rc == 0

    def remove_user(self):
        '''Delete SELF.NAME. If SELF.FORCE is true, remove its home directory.'''
        info = self.user_info()

        cmd = self._get_dscl()
        cmd += ['-delete', '/Users/%s' % self.name]
        (rc, out, err) = self.execute_command(cmd)

        if rc != 0:
            self.module.fail_json(msg='Cannot delete user "%s".' % self.name, err=err, out=out, rc=rc)

        if self.force:
            if os.path.exists(info[5]):
                shutil.rmtree(info[5])
                out += "Removed %s" % info[5]

        return (rc, out, err)

    def create_user(self, command_name='dscl'):
        cmd = self._get_dscl()
        cmd += ['-create', '/Users/%s' % self.name]
        (rc, out, err) = self.execute_command(cmd)
        if rc != 0:
            self.module.fail_json(msg='Cannot create user "%s".' % self.name, err=err, out=out, rc=rc)

        self._make_group_numerical()
        if self.uid is None:
            self.uid = str(self._get_next_uid(self.system))

        # Homedir is not created by default
        if self.create_home:
            if self.home is None:
                self.home = '/Users/%s' % self.name
            if not self.module.check_mode:
                if not os.path.exists(self.home):
                    os.makedirs(self.home)
                self.chown_homedir(int(self.uid), int(self.group), self.home)

        # dscl sets shell to /usr/bin/false when UserShell is not specified
        # so set the shell to /bin/bash when the user is not a system user
        if not self.system and self.shell is None:
            self.shell = '/bin/bash'

        for field in self.fields:
            if field[0] in self.__dict__ and self.__dict__[field[0]]:

                cmd = self._get_dscl()
                cmd += ['-create', '/Users/%s' % self.name, field[1], self.__dict__[field[0]]]
                (rc, _out, _err) = self.execute_command(cmd)
                if rc != 0:
                    self.module.fail_json(msg='Cannot add property "%s" to user "%s".' % (field[0], self.name), err=err, out=out, rc=rc)

                out += _out
                err += _err
                if rc != 0:
                    return (rc, _out, _err)

        (rc, _out, _err) = self._change_user_password()
        out += _out
        err += _err

        self._update_system_user()
        # here we don't care about change status since it is a creation,
        # thus changed is always true.
        if self.groups:
            (rc, _out, _err, changed) = self._modify_group()
            out += _out
            err += _err
        return (rc, out, err)

    def modify_user(self):
        changed = None
        out = ''
        err = ''

        if self.group:
            self._make_group_numerical()

        for field in self.fields:
            if field[0] in self.__dict__ and self.__dict__[field[0]]:
                current = self._get_user_property(field[1])
                if current is None or current != to_text(self.__dict__[field[0]]):
                    cmd = self._get_dscl()
                    cmd += ['-create', '/Users/%s' % self.name, field[1], self.__dict__[field[0]]]
                    (rc, _out, _err) = self.execute_command(cmd)
                    if rc != 0:
                        self.module.fail_json(
                            msg='Cannot update property "%s" for user "%s".'
                                % (field[0], self.name), err=err, out=out, rc=rc)
                    changed = rc
                    out += _out
                    err += _err
        if self.update_password == 'always' and self.password is not None:
            (rc, _out, _err) = self._change_user_password()
            out += _out
            err += _err
            changed = rc

        if self.groups:
            (rc, _out, _err, _changed) = self._modify_group()
            out += _out
            err += _err

            if _changed is True:
                changed = rc

        rc = self._update_system_user()
        if rc == 0:
            changed = rc

        return (changed, out, err)


class AIX(User):
    """
    This is a AIX User manipulation class.

    This overrides the following methods from the generic class:-
      - create_user()
      - remove_user()
      - modify_user()
      - parse_shadow_file()
    """

    platform = 'AIX'
    distribution = None
    SHADOWFILE = '/etc/security/passwd'

    def remove_user(self):
        cmd = [self.module.get_bin_path('userdel', True)]
        if self.remove:
            cmd.append('-r')
        cmd.append(self.name)

        return self.execute_command(cmd)

    def create_user_useradd(self, command_name='useradd'):
        cmd = [self.module.get_bin_path(command_name, True)]

        if self.uid is not None:
            cmd.append('-u')
            cmd.append(self.uid)

        if self.group is not None:
            if not self.group_exists(self.group):
                self.module.fail_json(msg="Group %s does not exist" % self.group)
            cmd.append('-g')
            cmd.append(self.group)

        if self.groups is not None and len(self.groups):
            groups = self.get_groups_set()
            cmd.append('-G')
            cmd.append(','.join(groups))

        if self.comment is not None:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None:
            cmd.append('-d')
            cmd.append(self.home)

        if self.shell is not None:
            cmd.append('-s')
            cmd.append(self.shell)

        if self.create_home:
            cmd.append('-m')

            if self.skeleton is not None:
                cmd.append('-k')
                cmd.append(self.skeleton)

            if self.umask is not None:
                cmd.append('-K')
                cmd.append('UMASK=' + self.umask)

        cmd.append(self.name)
        (rc, out, err) = self.execute_command(cmd)

        # set password with chpasswd
        if self.password is not None:
            cmd = []
            cmd.append(self.module.get_bin_path('chpasswd', True))
            cmd.append('-e')
            cmd.append('-c')
            self.execute_command(cmd, data="%s:%s" % (self.name, self.password))

        return (rc, out, err)

    def modify_user_usermod(self):
        cmd = [self.module.get_bin_path('usermod', True)]
        info = self.user_info()

        if self.uid is not None and info[2] != int(self.uid):
            cmd.append('-u')
            cmd.append(self.uid)

        if self.group is not None:
            if not self.group_exists(self.group):
                self.module.fail_json(msg="Group %s does not exist" % self.group)
            ginfo = self.group_info(self.group)
            if info[3] != ginfo[2]:
                cmd.append('-g')
                cmd.append(self.group)

        if self.groups is not None:
            current_groups = self.user_group_membership()
            groups_need_mod = False
            groups = []

            if self.groups == '':
                if current_groups and not self.append:
                    groups_need_mod = True
            else:
                groups = self.get_groups_set()
                group_diff = set(current_groups).symmetric_difference(groups)

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
                cmd.append(','.join(groups))

        if self.comment is not None and info[4] != self.comment:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None and info[5] != self.home:
            if self.move_home:
                cmd.append('-m')
            cmd.append('-d')
            cmd.append(self.home)

        if self.shell is not None and info[6] != self.shell:
            cmd.append('-s')
            cmd.append(self.shell)

        # skip if no changes to be made
        if len(cmd) == 1:
            (rc, out, err) = (None, '', '')
        else:
            cmd.append(self.name)
            (rc, out, err) = self.execute_command(cmd)

        # set password with chpasswd
        if self.update_password == 'always' and self.password is not None and info[1] != self.password:
            cmd = []
            cmd.append(self.module.get_bin_path('chpasswd', True))
            cmd.append('-e')
            cmd.append('-c')
            (rc2, out2, err2) = self.execute_command(cmd, data="%s:%s" % (self.name, self.password))
        else:
            (rc2, out2, err2) = (None, '', '')

        if rc is not None:
            return (rc, out + out2, err + err2)
        else:
            return (rc2, out + out2, err + err2)

    def parse_shadow_file(self):
        """Example AIX shadowfile data:
        nobody:
                password = *

        operator1:
                password = {ssha512}06$xxxxxxxxxxxx....
                lastupdate = 1549558094

        test1:
                password = *
                lastupdate = 1553695126

        """

        b_name = to_bytes(self.name)
        b_passwd = b''
        b_expires = b''
        if os.path.exists(self.SHADOWFILE) and os.access(self.SHADOWFILE, os.R_OK):
            with open(self.SHADOWFILE, 'rb') as bf:
                b_lines = bf.readlines()

            b_passwd_line = b''
            b_expires_line = b''
            try:
                for index, b_line in enumerate(b_lines):
                    # Get password and lastupdate lines which come after the username
                    if b_line.startswith(b'%s:' % b_name):
                        b_passwd_line = b_lines[index + 1]
                        b_expires_line = b_lines[index + 2]
                        break

                # Sanity check the lines because sometimes both are not present
                if b' = ' in b_passwd_line:
                    b_passwd = b_passwd_line.split(b' = ', 1)[-1].strip()

                if b' = ' in b_expires_line:
                    b_expires = b_expires_line.split(b' = ', 1)[-1].strip()

            except IndexError:
                self.module.fail_json(msg='Failed to parse shadow file %s' % self.SHADOWFILE)

        passwd = to_native(b_passwd)
        expires = to_native(b_expires) or -1
        return passwd, expires


class HPUX(User):
    """
    This is a HP-UX User manipulation class.

    This overrides the following methods from the generic class:-
      - create_user()
      - remove_user()
      - modify_user()
    """

    platform = 'HP-UX'
    distribution = None
    SHADOWFILE = '/etc/shadow'

    def create_user(self):
        cmd = ['/usr/sam/lbin/useradd.sam']

        if self.uid is not None:
            cmd.append('-u')
            cmd.append(self.uid)

            if self.non_unique:
                cmd.append('-o')

        if self.group is not None:
            if not self.group_exists(self.group):
                self.module.fail_json(msg="Group %s does not exist" % self.group)
            cmd.append('-g')
            cmd.append(self.group)

        if self.groups is not None and len(self.groups):
            groups = self.get_groups_set()
            cmd.append('-G')
            cmd.append(','.join(groups))

        if self.comment is not None:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None:
            cmd.append('-d')
            cmd.append(self.home)

        if self.shell is not None:
            cmd.append('-s')
            cmd.append(self.shell)

        if self.password is not None:
            cmd.append('-p')
            cmd.append(self.password)

        if self.create_home:
            cmd.append('-m')
        else:
            cmd.append('-M')

        if self.system:
            cmd.append('-r')

        cmd.append(self.name)
        return self.execute_command(cmd)

    def remove_user(self):
        cmd = ['/usr/sam/lbin/userdel.sam']
        if self.force:
            cmd.append('-F')
        if self.remove:
            cmd.append('-r')
        cmd.append(self.name)
        return self.execute_command(cmd)

    def modify_user(self):
        cmd = ['/usr/sam/lbin/usermod.sam']
        info = self.user_info()

        if self.uid is not None and info[2] != int(self.uid):
            cmd.append('-u')
            cmd.append(self.uid)

            if self.non_unique:
                cmd.append('-o')

        if self.group is not None:
            if not self.group_exists(self.group):
                self.module.fail_json(msg="Group %s does not exist" % self.group)
            ginfo = self.group_info(self.group)
            if info[3] != ginfo[2]:
                cmd.append('-g')
                cmd.append(self.group)

        if self.groups is not None:
            current_groups = self.user_group_membership()
            groups_need_mod = False
            groups = []

            if self.groups == '':
                if current_groups and not self.append:
                    groups_need_mod = True
            else:
                groups = self.get_groups_set(remove_existing=False)
                group_diff = set(current_groups).symmetric_difference(groups)

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

        if self.comment is not None and info[4] != self.comment:
            cmd.append('-c')
            cmd.append(self.comment)

        if self.home is not None and info[5] != self.home:
            cmd.append('-d')
            cmd.append(self.home)
            if self.move_home:
                cmd.append('-m')

        if self.shell is not None and info[6] != self.shell:
            cmd.append('-s')
            cmd.append(self.shell)

        if self.update_password == 'always' and self.password is not None and info[1] != self.password:
            cmd.append('-F')
            cmd.append('-p')
            cmd.append(self.password)

        # skip if no changes to be made
        if len(cmd) == 1:
            return (None, '', '')

        cmd.append(self.name)
        return self.execute_command(cmd)
