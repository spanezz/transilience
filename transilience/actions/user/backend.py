# Implementation adapter from Ansible's user module, which is Copyright: © 2012,
# Stephen Fromm <sfromm@gmail.com>, and licensed under the GNU General Public
# License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

# TODO: this module (and its platform specific specializations) still has a lot
#       of redundant operations left over from Ansible, and it could use a good
#       redesign

from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Set
import subprocess
import select
import shutil
import errno
import time
import pwd
import grp
import pty
import os
import re

try:
    import spwd
    HAVE_SPWD = True
except ImportError:
    HAVE_SPWD = False

if TYPE_CHECKING:
    from .action import User

# : for delimiter, * for disable user, ! for lock user
re_pw_special_chars = re.compile(r":\*!")
_HASH_RE = re.compile(r'[^a-zA-Z0-9./=]')


class Generic:
    """
    This is a generic User manipulation class that is subclassed
    based on platform.

    A subclass may wish to override the following action methods:

     * create_user()
     * remove_user()
     * modify_user()
     * ssh_key_gen()
     * get_ssh_key_fingerprint()
     * user_exists()
    """
    def __init__(self, action: User):
        self.action = action

    def get_platform(self):
        raise NotImplementedError(f"{self.__class__.__name__}.get_platform is not implemented")

    def get_passwordfile(self):
        # PASSWORDFILE
        return '/etc/passwd'

    def get_shadowfile(self):
        # SHADOWFILE
        return '/etc/shadow'

    def get_shadowfile_expire_index(self):
        # SHADOWFILE_EXPIRE_INDEX
        return 7

    def get_login_defs(self):
        # LOGIN_DEFS
        return '/etc/login.defs'

    def get_date_format(self):
        # DATE_FORMAT
        return '%Y-%m-%d'

    def backup_shadow(self):
        shadowfile = self.get_shadowfile()
        if shadowfile:
            return self.backup_file(shadowfile)

    def create_user(self):
        # by default we use the create_user_useradd method
        self.create_user_useradd()

    def remove_user(self):
        # by default we use the remove_user_userdel method
        self.remove_user_userdel()

    def modify_user(self):
        # by default we use the modify_user_usermod method
        self.modify_user_usermod()

    def check_password_encrypted(self):
        # Darwin needs cleartext password, so skip validation
        if self.action.password and self.get_platform() != 'Darwin':
            maybe_invalid = False

            # Allow setting certain passwords in order to disable the account
            if self.action.password in ['*', '!', '*************']:
                maybe_invalid = False
            else:
                # : for delimiter, * for disable user, ! for lock user
                # these characters are invalid in the password
                if re_pw_special_chars.search(self.action.password):
                    maybe_invalid = True
                if '$' not in self.action.password:
                    maybe_invalid = True
                else:
                    fields = self.action.password.split("$")
                    if len(fields) >= 3:
                        # contains character outside the crypto constraint
                        if _HASH_RE.search(fields[-1]):
                            maybe_invalid = True
                        # md5
                        if fields[1] == '1' and len(fields[-1]) != 22:
                            maybe_invalid = True
                        # sha256
                        if fields[1] == '5' and len(fields[-1]) != 43:
                            maybe_invalid = True
                        # sha512
                        if fields[1] == '6' and len(fields[-1]) != 86:
                            maybe_invalid = True
                    else:
                        maybe_invalid = True
            if maybe_invalid:
                self.log.warning("The input password appears not to have been hashed. "
                                 "The 'password' argument must be encrypted for this module to work properly.")

    def user_exists(self):
        # The pwd module does not distinguish between local and directory accounts.
        # It's output cannot be used to determine whether or not an account exists locally.
        # It returns True if the account exists locally or in the directory, so instead
        # look in the local PASSWORD file for an existing account.
        if self.action.local:
            passwordfile = self.get_passwordfile()
            if not os.path.exists(passwordfile):
                raise RuntimeError(f"'local' is True but unable to find local account file {passwordfile} to parse.")

            exists = False
            name_test = (self.action.name + ":").encode()
            with open(passwordfile, 'rb') as fd:
                for line in reversed(fd.readlines()):
                    if line.startswith(name_test):
                        exists = True
                        break

            if not exists:
                self.log.warning(
                    f"'local' is True and user {self.action.name!r} was not found in {passwordfile!r}. "
                    "The local user account may already exist if the local account database exists "
                    f"somewhere other than {passwordfile!r}.")

            return exists
        else:
            try:
                if pwd.getpwnam(self.action.name):
                    return True
            except KeyError:
                return False

    def get_pwd_info(self) -> Optional[pwd.struct_passwd]:
        if not self.user_exists():
            return None
        return pwd.getpwnam(self.action.name)

    def user_info(self) -> Optional[pwd.struct_passwd]:
        if not self.user_exists():
            return None
        info = pwd.getpwnam(self.action.name)
        if len(info.pw_passwd) in (0, 1):
            info = pwd.struct_passwd(
                    (info[0], self.user_password()[0]) + info[2:])
        return info

    def user_password(self):
        passwd = ''
        expires = ''
        if HAVE_SPWD:
            try:
                passwd = spwd.getspnam(self.action.name)[1]
                expires = spwd.getspnam(self.action.name)[7]
                return passwd, expires
            except KeyError:
                return passwd, expires
            except OSError as e:
                # Python 3.6 raises PermissionError instead of KeyError
                # Due to absence of PermissionError in python2.7 need to check
                # errno
                if e.errno in (errno.EACCES, errno.EPERM, errno.ENOENT):
                    return passwd, expires
                raise

        if not self.user_exists():
            return passwd, expires
        elif self.get_shadowfile():
            passwd, expires = self.parse_shadow_file()

        return passwd, expires

    def parse_shadow_file(self):
        passwd = ''
        expires = ''
        shadowfile = self.get_shadowfile()
        shadowfile_expire_index = self.get_shadowfile_expire_index()
        if os.path.exists(shadowfile) and os.access(shadowfile, os.R_OK):
            with open(shadowfile, 'rt') as f:
                match = self.action.name + ":"
                for line in f:
                    if line.startswith(match):
                        passwd = line.split(':')[1]
                        expires = line.split(':')[shadowfile_expire_index] or -1
        return passwd, expires

    def group_exists(self, group: str):
        try:
            # Try group as a gid first
            grp.getgrgid(int(group))
            return True
        except (ValueError, KeyError):
            try:
                grp.getgrnam(group)
                return True
            except KeyError:
                return False

    def group_info(self, group: str) -> Optional[grp.struct_group]:
        try:
            # Try group as a gid first
            return grp.getgrgid(int(group))
        except (ValueError, KeyError):
            try:
                return grp.getgrnam(group)
            except KeyError:
                return None

    def user_group_membership(self, exclude_primary=True) -> List[str]:
        """
        Return a list of groups the user belongs to
        """
        groups: List[str] = []
        info = self.get_pwd_info()
        for group in grp.getgrall():
            if self.action.name in group.gr_mem:
                # Exclude the user's primary group by default
                if not exclude_primary:
                    groups.append(group[0])
                else:
                    if info.pw_gid != group.gr_gid:
                        groups.append(group.gr_name)

        return groups

    def get_groups_set(self, remove_existing=True) -> Set[str]:
        if not self.action.groups:
            return set()
        info = self.user_info()
        groups = set()
        for g in self.action.groups:
            if not self.group_exists(g):
                raise ValueError(f"Group {g!r} does not exist")
            if not info or not remove_existing or self.action.group_info(g).gr_gid != info.pw_gid:
                groups.add(g)
        return groups

    def remove_user_userdel(self):
        if self.action.local:
            cmd = [self.action.find_command('luserdel')]
        else:
            cmd = [self.action.find_command('userdel')]

        if self.action.force and not self.action.local:
            cmd.append('-f')
        if self.action.remove:
            cmd.append('-r')
        cmd.append(self.action.name)

        self.action.set_changed()
        self.action.run_command(cmd)

    def create_user_useradd(self):
        if self.action.local:
            cmd = [self.action.find_command('luseradd')]
            lgroupmod_cmd = self.action.find_command('lgroupmod')
            lchage_cmd = self.action.find_command('lchage')
        else:
            cmd = [self.action.find_command('useradd')]

        if self.action.uid is not None:
            cmd.append('-u')
            cmd.append(self.action.uid)

            if self.action.non_unique:
                cmd.append('-o')

        if self.action.seuser is not None:
            cmd.append('-Z')
            cmd.append(self.action.seuser)
        if self.action.group is not None:
            if not self.group_exists(self.action.group):
                raise RuntimeError(f"Group {self.action.group!r} does not exist")
            cmd.append('-g')
            cmd.append(self.action.group)
        elif self.group_exists(self.action.name):
            # use the -N option (no user group) if a group already
            # exists with the same name as the user to prevent
            # errors from useradd trying to create a group when
            # USERGROUPS_ENAB is set in /etc/login.defs.
            if os.path.exists('/etc/redhat-release'):
                if self.action.local:
                    cmd.append('-n')
                else:
                    cmd.append('-N')
            else:
                cmd.append('-N')

        if self.action.groups:
            groups = self.get_groups_set()
            if not self.action.local:
                cmd.append('-G')
                cmd.append(','.join(groups))

        if self.action.comment is not None:
            cmd.append('-c')
            cmd.append(self.action.comment)

        if self.action.home is not None:
            if self.action.create_home:
                self.create_homedir(self.action.home)
            cmd.append('-d')
            cmd.append(self.action.home)

        if self.action.shell is not None:
            cmd.append('-s')
            cmd.append(self.action.shell)

        if self.action.expires is not None and not self.action.local:
            cmd.append('-e')
            if self.action.expires < 0:
                cmd.append('')
            else:
                cmd.append(
                        time.strftime(
                            self.get_date_format(), time.gmtime(self.action.expires)))

        if self.action.password is not None:
            cmd.append('-p')
            if self.action.password_lock:
                cmd.append('!' + self.action.password)
            else:
                cmd.append(self.action.password)

        cmd.append('-M')

        if self.action.system:
            cmd.append('-r')

        cmd.append(self.action.name)

        self.action.run_command(cmd)
        self.action.set_changed()

        if not self.action.local:
            return

        if self.action.expires is not None:
            if self.action.expires < 0:
                lexpires = -1
            else:
                # Convert seconds since Epoch to days since Epoch
                lexpires = self.action.expires // 86400
            self.action.run_command([lchage_cmd, '-E', str(lexpires), self.action.name])

        if not self.action.groups:
            return

        for add_group in groups:
            self.action.run_command([lgroupmod_cmd, '-M', self.action.name, add_group])

    def _check_usermod_append(self, usermod_path: str):
        """
        check if this version of usermod can append groups
        """
        # for some reason, usermod --help cannot be used by non root
        # on RH/Fedora, due to lack of execute bit for others
        if not os.access(usermod_path, os.X_OK):
            return False

        cmd = [usermod_path, '--help']
        res = self.action.run_command(cmd, check=False, capture_output=True, text=True)
        helpout = res.stdout + res.stderr

        # check if --append exists
        for line in helpout.split('\n'):
            if line.lstrip().startswith('-a, --append'):
                return True

        return False

    def modify_user_usermod(self):
        if self.action.local:
            cmd = [self.action.find_command('lusermod')]
            lgroupmod_cmd = self.action.find_command('lgroupmod')
            lgroupmod_add = set()
            lgroupmod_del = set()
            lchage_cmd = self.action.find_command('lchage')
            lexpires = None
        else:
            cmd = ['usermod']

        info = self.user_info()
        has_append = self._check_usermod_append(cmd[0])

        if self.action.uid is not None and info.pw_uid != int(self.action.uid):
            cmd.append('-u')
            cmd.append(self.action.uid)

            if self.action.non_unique:
                cmd.append('-o')

        if self.action.group is not None:
            if not self.group_exists(self.action.group):
                raise RuntimeError(f"Group {self.action.group!r} does not exist")
            ginfo = self.action.group_info(self.action.group)
            if info.pw_gid != ginfo.gr_gid:
                cmd.append('-g')
                cmd.append(self.action.group)

        if self.action.groups is not None:
            # get a list of all groups for the user, including the primary
            current_groups = self.user_group_membership(exclude_primary=False)
            groups_need_mod = False
            groups = set()

            if not self.action.groups:
                if current_groups and not self.action.append:
                    groups_need_mod = True
            else:
                groups = self.get_groups_set(remove_existing=False)
                group_diff = current_groups.symmetric_difference(groups)

                if group_diff:
                    if self.action.append:
                        for g in groups:
                            if g in group_diff:
                                if has_append:
                                    cmd.append('-a')
                                groups_need_mod = True
                                break
                    else:
                        groups_need_mod = True

            if groups_need_mod:
                if self.action.local:
                    if self.action.append:
                        lgroupmod_add = groups.difference(current_groups)
                        lgroupmod_del = set()
                    else:
                        lgroupmod_add = groups.difference(current_groups)
                        lgroupmod_del = set(current_groups).difference(groups)
                else:
                    if self.action.append and not has_append:
                        cmd.append('-A')
                        cmd.append(','.join(group_diff))
                    else:
                        cmd.append('-G')
                        cmd.append(','.join(groups))

        if self.action.comment is not None and info.pw_gecos != self.action.comment:
            cmd.append('-c')
            cmd.append(self.action.comment)

        if self.action.home is not None and info.pw_dir != self.action.home:
            cmd.append('-d')
            cmd.append(self.action.home)
            if self.action.move_home:
                cmd.append('-m')

        if self.action.shell is not None and info.pw_shell != self.action.shell:
            cmd.append('-s')
            cmd.append(self.action.shell)

        if self.action.expires is not None:
            current_expires = int(self.user_password()[1])

            if self.action.expires < 0:
                if current_expires >= 0:
                    if self.action.local:
                        lexpires = -1
                    else:
                        cmd.append('-e')
                        cmd.append('')
            else:
                # Convert days since Epoch to seconds since Epoch as struct_time
                current_expire_date = time.gmtime(current_expires * 86400)
                expire_date = time.gmtime(self.action.expires)

                # Current expires is negative or we compare year, month, and day only
                if current_expires < 0 or current_expire_date[:3] != expire_date[:3]:
                    if self.action.local:
                        # Convert seconds since Epoch to days since Epoch
                        lexpires = int(self.action.expires) // 86400
                    else:
                        cmd.append('-e')
                        cmd.append(time.strftime(self.get_date_format(), expire_date))

        # Lock if no password or unlocked, unlock only if locked
        if self.action.password_lock and not info.pw_passwd.startswith('!'):
            cmd.append('-L')
        elif self.action.password_lock is False and info.pw_passwd.startswith('!'):
            # usermod will refuse to unlock a user with no password, module shows 'changed' regardless
            cmd.append('-U')

        if (self.action.update_password == 'always' and self.action.password is not None and
                info.pw_passwd.lstrip('!') != self.action.password.lstrip('!')):
            # Remove options that are mutually exclusive with -p
            cmd = [c for c in cmd if c not in ['-U', '-L']]
            cmd.append('-p')
            if self.action.password_lock:
                # Lock the account and set the hash in a single command
                cmd.append('!' + self.action.password)
            else:
                cmd.append(self.action.password)

        # skip if no usermod changes to be made
        if len(cmd) > 1:
            cmd.append(self.action.name)
            self.action.run_command(cmd)
            self.action.set_changed()

        if not self.action.local:
            return

        if lexpires is not None:
            self.action.run_command([lchage_cmd, '-E', str(lexpires), self.action.name])
            self.action.set_changed()

        if not lgroupmod_add == 0 and not lgroupmod_del:
            return

        for add_group in lgroupmod_add:
            self.action.run_command([lgroupmod_cmd, '-M', self.action.name, add_group])
            self.action.set_changed()

        for del_group in lgroupmod_del:
            self.action.run_command([lgroupmod_cmd, '-m', self.action.name, del_group])
            self.action.set_changed()

    def chown_homedir(self, uid, gid, path):
        os.chown(path, uid, gid)
        for root, dirs, files in os.walk(path):
            for d in dirs:
                os.chown(os.path.join(root, d), uid, gid)
            for f in files:
                os.chown(os.path.join(root, f), uid, gid)

    def create_homedir(self, path: str):
        if os.path.exists(path):
            return

        if self.action.skeleton is not None:
            skeleton = self.action.skeleton
        else:
            skeleton = '/etc/skel'

        if os.path.exists(skeleton):
            shutil.copytree(skeleton, path, symlinks=True)
        else:
            os.makedirs(path)

        # umask_string = None
        # # If an umask was set take it from there
        # if self.umask is not None:
        #     umask_string = self.umask
        # else:
        #     # try to get umask from /etc/login.defs
        #     if os.path.exists(self.LOGIN_DEFS):
        #         with open(self.LOGIN_DEFS, 'r') as f:
        #             for line in f:
        #                 m = re.match(r'^UMASK\s+(\d+)$', line)
        #                 if m:
        #                     umask_string = m.group(1)

        # # set correct home mode if we have a umask
        # if umask_string is not None:
        #     umask = int(umask_string, 8)
        #     mode = 0o777 & ~umask
        #     try:
        #         os.chmod(path, mode)
        #     except OSError as e:
        #         self.module.exit_json(failed=True, msg="%s" % to_native(e))

    def get_ssh_key_path(self) -> str:
        info = self.user_info()
        if os.path.isabs(self.action.ssh_key_file):
            ssh_key_file = self.action.ssh_key_file
        else:
            if not os.path.exists(info.pw_dir):
                raise RuntimeError(f'User {self.action.name!r} home directory does not exist')
            ssh_key_file = os.path.join(info.pw_dir, self.action.ssh_key_file)
        return ssh_key_file

    def ssh_key_gen(self):
        info = self.user_info()
        overwrite = None
        ssh_key_file = self.get_ssh_key_path()
        ssh_dir = os.path.dirname(ssh_key_file)
        if not os.path.exists(ssh_dir):
            os.mkdir(ssh_dir, 0o700)
            os.chown(ssh_dir, info.pw_uid, info.pw_gid)
            self.action.set_changed()
        if os.path.exists(ssh_key_file):
            if self.action.force:
                # ssh-keygen doesn't support overwriting the key interactively, so send 'y' to confirm
                overwrite = b'y'
            else:
                self.log.warning('Key %s already exists, use "force: yes" to overwrite', ssh_key_file)
                return
        cmd = [self.action.find_command('ssh-keygen')]
        cmd.append('-t')
        cmd.append(self.action.ssh_key_type)
        if self.ssh_bits > 0:
            cmd.append('-b')
            cmd.append(self.action.ssh_key_bits)
        cmd.append('-C')
        cmd.append(self.action.ssh_key_comment)
        cmd.append('-f')
        cmd.append(ssh_key_file)
        if self.action.ssh_key_passphrase is not None:
            master_in_fd, slave_in_fd = pty.openpty()
            master_out_fd, slave_out_fd = pty.openpty()
            master_err_fd, slave_err_fd = pty.openpty()
            env = os.environ.copy()
            env['LC_ALL'] = 'C'
            p = subprocess.Popen(cmd,
                                 stdin=slave_in_fd,
                                 stdout=slave_out_fd,
                                 stderr=slave_err_fd,
                                 preexec_fn=os.setsid,
                                 env=env)
            out_buffer = b''
            err_buffer = b''
            while p.poll() is None:
                r, w, e = select.select([master_out_fd, master_err_fd], [], [], 1)
                first_prompt = b'Enter passphrase (empty for no passphrase):'
                second_prompt = b'Enter same passphrase again'
                prompt = first_prompt
                for fd in r:
                    if fd == master_out_fd:
                        chunk = os.read(master_out_fd, 10240)
                        out_buffer += chunk
                        if prompt in out_buffer:
                            os.write(master_in_fd, self.action.ssh_key_passphrase.encode() + b'\r')
                            prompt = second_prompt
                    else:
                        chunk = os.read(master_err_fd, 10240)
                        err_buffer += chunk
                        if prompt in err_buffer:
                            os.write(master_in_fd, self.action.ssh_key_passphrase.encode() + b'\r')
                            prompt = second_prompt
                    if b'Overwrite (y/n)?' in out_buffer or b'Overwrite (y/n)?' in err_buffer:
                        # The key was created between us checking for existence and now
                        self.log.warning("Key %s already exists", self.action.ssh_key_file)
                        return
            self.action.set_changed()
        else:
            cmd.append('-N')
            cmd.append('')
            self.action.run_command(cmd, input=overwrite)
            self.action.set_changed()

        # If the keys were successfully created, we should be able
        # to tweak ownership.
        os.chown(ssh_key_file, info.pw_uid, info.pw_gid)
        os.chown(ssh_key_file + '.pub', info.pw_uid, info.pw_gid)

    def get_ssh_key_fingerprint(self) -> str:
        cmd = [self.action.find_command('ssh-keygen')]
        cmd.append('-l')
        cmd.append('-f')
        cmd.append(self.get_ssh_key_path())
        res = self.action.run_command(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return res.stdout.strip()
        else:
            return res.stderr.strip()

    def get_ssh_public_key(self) -> str:
        ssh_public_key_file = self.get_ssh_key_path() + ".pub"
        try:
            with open(ssh_public_key_file, 'rt') as fd:
                return fd.read().strip()
        except FileNotFoundError:
            return None

    def set_password_expire_max(self):
        if HAVE_SPWD and self.action.password_expire_max == spwd.getspnam(self.action.name).sp_max:
            return

        cmd = [self.action.find_command("chage")]
        cmd.append('-M')
        cmd.append(self.action.password_expire_max)
        cmd.append(self.action.name)
        self.action.run_command(cmd)
        self.action.set_changed()

    def set_password_expire_min(self):
        if HAVE_SPWD and self.action.password_expire_min == spwd.getspnam(self.action.name).sp_min:
            return

        cmd = [self.action.find_command("chage")]
        cmd.append('-m')
        cmd.append(self.action.password_expire_min)
        cmd.append(self.action.name)
        self.action.run_command(cmd)
        self.action.set_changed()

    def do_absent(self):
        if self.user_exists():
            self.remove_user()

    def do_present(self):
        if not self.user_exists():
            # Check to see if the provided home path contains parent directories
            # that do not exist.
            path_needs_parents = False
            if self.action.home and self.action.create_home:
                parent = os.path.dirname(self.action.home)
                if not os.path.isdir(parent):
                    path_needs_parents = True

            self.create_user()

            # If the home path had parent directories that needed to be created,
            # make sure file permissions are correct in the created home directory.
            if path_needs_parents:
                info = self.user_info()
                if info is not False:
                    self.chown_homedir(info.pw_uid, info.pw_gid, self.action.home)
        else:
            # modify user (note: this function is check mode aware)
            self.modify_user()
            # result['append'] = user.append
            # result['move_home'] = user.move_home
        if self.action.password is not None:
            self.action.password = 'NOT_LOGGING_PASSWORD'

    def do_update(self):
        info = self.user_info()
        if not info:
            raise RuntimeError(f"failed to look up user {self.action.name!r}")

        self.action.uid = info.pw_uid
        self.action.group = str(info.pw_gid)
        self.action.comment = info.pw_gecos
        self.action.home = info.pw_dir
        self.action.shell = info.pw_shell

        # handle missing homedirs
        if not os.path.exists(self.action.home) and self.action.create_home:
            self.create_homedir(self.action.home)
            self.chown_homedir(info.pw_uid, info.pw_gid, self.action.home)
            self.action.set_changed()

        # deal with ssh key
        if self.action.generate_ssh_key:
            # generate ssh key (note: this function is check mode aware)
            self.action.ssh_key_gen()
            self.action.ssh_key_fingerprint = self.get_ssh_key_fingerprint()
            self.action.ssh_key_file = self.get_ssh_key_path()
            self.action.ssh_key_pubkey = self.get_ssh_public_key()

        # deal with password expire max
        if self.action.password_expire_max:
            if self.user_exists():
                self.set_password_expire_max()

        # deal with password expire min
        if self.action.password_expire_min:
            if self.user_exists():
                self.set_password_expire_min()
