# Implementation adapted from Ansible's user module, which is Copyright: ©
# 2012, Michael DeHaan <michael.dehaan@gmail.com>, and licensed under the GNU
# General Public License v3.0+ (see COPYING or
# https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List, Union
from dataclasses import dataclass, field
import contextlib
import subprocess
import shutil
import shlex
import re
import os
from .action import Action
from . import builtin

if TYPE_CHECKING:
    import transilience.system

re_shasum = re.compile(f"^[0-9a-f]{40}$")


@builtin.action(name="git")
@dataclass
class Git(Action):
    """
    Same as Ansible's
    [builtin.git](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/git_module.html).

    Not yet implemented:
     - accept_hostkey
     - archive
     - archive_prefix
     - bare
     - clone
     - depth
     - dest
     - executable
     - force
     - gpg_whitelist
     - key_file
     - recursive
     - reference
     - refspec
     - remote
     - repo
     - separate_git_dir
     - single_branch
     - ssh_opts
     - track_submodules
     - umask
     - update
     - verify_commit
     - version
    """
    accept_hostkey: bool = False
    archive: Optional[str] = None
    archive_prefix: Optional[str] = None
    bare: bool = False
    clone: bool = True
    depth: Optional[int] = None
    dest: Optional[str] = None
    executable: Optional[str] = None
    force: bool = False
    gpg_whitelist: List[str] = field(default_factory=list)
    key_file: Optional[str] = None
    recursive: bool = True
    reference: Optional[str] = None
    refspec: Optional[str] = None
    remote: str = "origin"
    repo: Optional[str] = None
    separate_git_dir: Optional[str] = None
    single_branch: bool = False
    ssh_opts: Union[str, List[str]] = field(default_factory=list)
    track_submodules: bool = False
    umask: Optional[int] = None
    update: bool = True
    verify_commit: bool = False
    version: str = "HEAD"

    @contextlib.contextmanager
    def set_umask(self):
        """
        Set the umask if needed
        """
        if self.umask is None:
            yield
        else:
            old_umask = os.umask(self.umask)
            try:
                yield
            finally:
                os.umask(old_umask)

    def get_repo_path(self):
        if self.bare:
            repo_path = self.dest
        else:
            repo_path = os.path.join(self.dest, '.git')

        # Check if the .git is a file. if it is a file, it means that the
        # repository is in an external directory respective to the working copy
        # (e.g. we are in a submodule structure)
        if os.path.isfile(repo_path):
            with open(repo_path, 'r') as fd:
                for line in fd:
                    key, val = line.split(": ", 1)
                    if key == "gitdir":
                        gitdir = val.strip()
                        break
                else:
                    gitdir = None

            if gitdir is None:
                raise RuntimeError("'gitdir:' entry not found in submodule's .git file")

            # There is a possibility for the .git file to have an absolute path
            if os.path.isabs(gitdir):
                repo_path = gitdir
            else:
                head, tail = os.path.split(repo_path)
                if tail == ".git":
                    repo_path = os.path.join(head, gitdir)
                else:
                    repo_path = os.path.join(repo_path, gitdir)

            if not os.path.isdir(repo_path):
                raise ValueError(f'{repo_path!r} is not a directory')

        return repo_path

    def relocate_repo(self, repo_dir: str, old_repo_dir: str, worktree_dir: str = None):
        if os.path.exists(repo_dir):
            raise RuntimeError(f"separate_git_dir path {repo_dir!r} already exists")

        if worktree_dir is None:
            return

        self.log.info("%s: moving .git directory from %r to %r", self.old_repo_dir, self.repo_dir)
        dot_git_file_path = os.path.join(worktree_dir, '.git')
        try:
            shutil.move(old_repo_dir, repo_dir)
        except (IOError, OSError) as err:
            raise RuntimeError(f"Unable to move git dir: {err}")

        try:
            # FIXME: this code (from Ansible) will trash other contents in the
            #        file. Are submodules supposed to only contain 'gitdir:'
            #        entries?
            with open(dot_git_file_path, 'w') as fd:
                fd.write(f'gitdir: {repo_dir}')
            self.set_changed()
        except (IOError, OSError) as err:
            # If we already moved the .git dir, roll it back
            if os.path.exists(repo_dir):
                shutil.move(repo_dir, old_repo_dir)
            raise RuntimeError(f"Unable to update git dir location in {dot_git_file_path!r}: {err}")

    def is_remote_branch(self):
        cmd = ["ls-remote", self.remote, "--heads", "refs/heads/" + self.version]
        res = self.run_git(cmd, capture_output=True, text=True)
        for line in res.stdout.splitlines():
            shasum, ref = line.split(None, 1)
            if ref == self.version:
                return True
        return False

    def is_remote_tag(self):
        cmd = ["ls-remote", self.remote, "--tags", "refs/tags/" + self.version]
        res = self.run_git(cmd, capture_output=True, text=True)
        for line in res.stdout.splitlines():
            shasum, ref = line.split(None, 1)
            if ref == self.version:
                return True
        return False

    def do_clone(self):
        """
        Makes a new git repo if it does not already exist
        """
        dest_dirname = os.path.dirname(self.dest)
        os.makedirs(dest_dirname, exist_ok=True)

        cmd = ['clone']

        if self.bare:
            cmd.append('--bare')
        else:
            cmd.extend(['--origin', self.remote])

        is_branch_or_tag = self.is_remote_branch() or self.is_remote_tag()
        if self.depth:
            if self.version == 'HEAD' or self.refspec:
                cmd.extend(['--depth', str(self.depth)])
            elif is_branch_or_tag:
                cmd.extend(['--depth', str(self.depth)])
                cmd.extend(['--branch', self.version])
            else:
                # only use depth if the remote object is branch or tag (i.e. fetchable)
                self.log.warn("Ignoring depth argument: shallow clones are only available for"
                              " HEAD, branches, tags or in combination with refspec.")
        if self.reference:
            cmd.extend(['--reference', str(self.reference)])

        if self.single_branch:
            cmd.append("--single-branch")
            if is_branch_or_tag:
                cmd.extend(['--branch', self.version])

        if self.separate_git_dir:
            cmd.append("--separate-git-dir=" + self.separate_git_dir)

        self.log.info("Cloning %r to %r", self.repo, self.dest)
        cmd.extend([self.repo, self.dest])
        self.run_git(cmd, cwd=dest_dirname)
        self.set_changed()

        if self.bare and self.remote != 'origin':
            self.run_git(["remote", "add", self.remote, self.repo], cwd=self.dest)

        if self.refspec:
            cmd = ['fetch']
            if self.depth:
                cmd.extend(['--depth', str(self.depth)])
            cmd.extend([self.remote, self.refspec])
            self.run_git(cmd, cwd=self.dest)

        if self.verify_commit:
            self.verify_commit_sign()

    def run_git(self, args: List[str], cwd=None, check=True, **kw):
        env = dict(os.environ)
        # We parse git output so use C locale
        env["LANG"] = "C"
        env["LC_ALL"] = "C"
        env["LC_MESSAGES"] = "C"
        env["LC_CTYPE"] = "C"

        if self.ssh_opts:
            env["GIT_SSH_COMMAND"] = ' '.join(shlex.quote(c) for c in self.ssh_opts)

        cmd = [self.executable]
        cmd.extend(args)

        return subprocess.run(cmd, env=env, cwd=cwd, check=check, **kw)

    def get_annotated_tags(self):
        tags = []
        cmd = ['for-each-ref', 'refs/tags/', '--format', '%(objecttype):%(refname:short)']
        res = self.run_git(cmd, capture_output=True, text=True)
        for line in res.stdout.splitlines():
            if line.strip():
                tagtype, tagname = line.strip().split(':', 1)
                if tagtype == 'tag':
                    tags.append(tagname)
        return tags

    def get_gpg_fingerprint(self, output: str):
        """
        Return a fingerprint of the primary key.

        Ref: https://git.gnupg.org/cgi-bin/gitweb.cgi?p=gnupg.git;a=blob;f=doc/DETAILS;hb=HEAD#l482
        """
        for line in output.splitlines():
            data = line.split()
            if data[1] != 'VALIDSIG':
                continue

            # if signed with a subkey, this contains the primary key fingerprint
            data_id = 11 if len(data) == 11 else 2
            return data[data_id]

    def verify_commit_sign(self):
        if self.version in self.get_annotated_tags():
            cmd = ["verify-tag"]
        else:
            cmd = ["verify-commit"]
        cmd.append(self.version)
        if self.gpg_whitelist:
            cmd .append("--raw")
        res = self.run_git(cmd, capture_output=True, text=True)
        if self.gpg_whitelist:
            fingerprint = self.get_gpg_fingerprint(res.stderr)
            if fingerprint not in self.gpg_whitelist:
                raise RuntimeError(
                    f"The gpg_whitelist does not include the public key {fingerprint!r} for this commit")

    def has_local_mods(self):
        if self.bare:
            return False

        cmd = ["status", "--porcelain=v1"]
        res = self.run_git(cmd, capture_output=True, text=True, cwd=self.dest)
        for line in res.stdout.splitlines():
            if not line.startswith("?? "):
                return True
        return False

    def do_reset(self):
        """
        Resets the index and working tree to HEAD.

        Discards any changes to tracked files in working
        tree since that commit.
        """
        cmd = ["reset", "--hard", "HEAD"]
        self.run_git(cmd, cwd=self.dest)

    def get_remote_url(self):
        """
        Return URL of remote source for repo
        """
        cmd = ['ls-remote', '--get-url', self.remote]
        res = self.run_git(cmd, capture_output=True, text=True, cwd=self.dest)
        return res.stdout.strip()

    def set_remote_url(self):
        """
        Updates repo from remote sources
        """
        # Return if remote URL isn't changing
        remote_url = self.get_remote_url()
        if remote_url == self.repo or self._normalise_repo_path(remote_url) == self.repo:
            return False

        self.log.info("Setting remote url for %r to %r", self.remote, self.repo)
        cmd = ['remote', 'set-url', self.remote, self.repo]
        self.run_git(cmd, cwd=self.dest)
        self.set_changed()

        return True

    def _normalise_repo_path(self, path: str):
        _repo = os.path.expanduser(path)
        if _repo.startswith('/'):
            return 'file://' + _repo
        return _repo

    # def get_branches(self):
    #     branches = []
    #     cmd = '%s branch --no-color -a' % (git_path,)
    #     (rc, out, err) = module.run_command(cmd, cwd=dest)
    #     if rc != 0:
    #         module.fail_json(msg="Could not determine branch data - received %s" % out, stdout=out, stderr=err)
    #     for line in out.split('\n'):
    #         if line.strip():
    #             branches.append(line.strip())
    #     return branches

    def is_not_a_branch(self):
        cmd = ["branch", "--no-color", "--show-current"]
        res = self.run_git(cmd, capture_output=True, text=True, cwd=self.dest)
        return not res.stdout.strip()

    def branch_from_head(self, headfile: str) -> Optional[str]:
        """
        Extract the head reference
        """
        # https://github.com/ansible/ansible-modules-core/pull/907
        if not os.path.exists(headfile):
            return None

        with open(headfile, "rt") as fd:
            rawdata = fd.readline()

        if not rawdata:
            return None

        if not rawdata.startswith("ref: "):
            raise RuntimeError(f"{headfile!r} content does not begin with 'ref: '")

        res = rawdata[5:].strip()
        remote = f"refs/remotes/{self.remote}/"
        if res.startswith(remote):
            res = res[len(remote):]
        return res.split("/", 2)[-1]

    def get_head_branch(self):
        """
        Determine what branch HEAD is associated with

        It finds the correct path to .git/HEAD and reads from that file the
        branch that HEAD is associated with.  In the case of a detached HEAD,
        this will look up the branch in .git/refs/remotes/<remote>/HEAD.
        """
        repo_path = self.get_repo_path()

        # Read .git/HEAD for the name of the branch.
        # If we're in a detached HEAD state, look up the branch associated with
        # the remote HEAD in .git/refs/remotes/<remote>/HEAD
        headfile = os.path.join(repo_path, "HEAD")
        if self.is_not_a_branch():
            headfile = os.path.join(repo_path, 'refs', 'remotes', self.remote, 'HEAD')
        branch = self.branch_from_head(headfile)
        return branch

    def is_shasum(self, s: str):
        return re_shasum.match(s)

    def get_remote_head(self):
        """
        Get the shasum of self.version on the remote
        """
        cmd = ["rev-parse"]

        if self.version == 'HEAD':
            head_branch = self.get_head_branch()
            cmd.append(f"{self.remote}/{head_branch}")
        elif self.is_shasum(self.version):
            # appears to be a sha1.  return as-is since it appears
            # cannot check for a specific sha1 on remote
            return self.version
        else:
            cmd.append(f"{self.remote}/{self.version}")

        res = self.run_git(cmd, capture_output=True, text=True, cwd=self.dest)
        if not res.stdout:
            raise RuntimeError(f"Could not determine remote revision for {self.version}")

        return res.stdout.strip()

    def get_version(self, ref: str = "HEAD"):
        """
        Read the version of the git repo
        """
        cmd = ["rev-parse", ref]
        res = self.run_git(cmd, capture_output=True, text=True, cwd=self.dest)
        return res.stdout.strip()

    def set_remote_branch(self):
        """
        Set refs for the remote branch version

        This assumes the branch does not yet exist locally and is therefore also not checked out.
        """
        # From Ansible: can't use git remote set-branches, as it is not available in git 1.7.1 (centos6)
        # FIXME: switch to git remote set-branches?

        branchref = (
                f"+refs/heads/{self.version}:refs/heads/{self.version}"
                f" +refs/heads/{self.version}:refs/remotes/{self.remote}/{self.version}"
        )
        cmd = ["fetch", "--depth={self.depth}", self.remote, branchref]
        self.run_git(cmd, cwd=self.dest)

    def do_switch_version(self):
        if self.version == 'HEAD':
            branch = self.get_head_branch()
            self.run_git(["checkout", "--force", branch], cwd=self.dest)
            cmd = ["reset", "--hard", f"{self.remote}/{branch}"]
        else:
            # FIXME check for local_branch first, should have been fetched already
            if self.is_remote_branch():
                if self.depth and not self.is_local_branch():
                    # git clone --depth implies --single-branch, which makes
                    # the checkout fail if the version changes
                    # fetch the remote branch, to be able to check it out next
                    self.set_remote_branch()
                if not self.is_local_branch():
                    cmd = ["checkout", "--track", "-b", self.version, f"{self.remote}/{self.version}"]
                else:
                    self.run_git(["checkout", "--force", self.version], cwd=self.dest)
                    cmd = ["reset", "--hard", f"{self.remote}/{self.version}"]
            else:
                cmd = ["checkout", "--force", self.version]

        self.run_git(cmd, cwd=self.dest)

        if self.verify_commit:
            self.verify_commit_sign()

    def submodules_fetch(self):
        changed = False

        if not os.path.exists(os.path.join(self.dest, '.gitmodules')):
            # no submodules
            return changed

        gitmodules_file = open(os.path.join(self.dest, '.gitmodules'), 'r')
        for line in gitmodules_file:
            # Check for new submodules
            if not changed and line.strip().startswith('path'):
                path = line.split('=', 1)[1].strip()
                # Check that dest/path/.git exists
                if not os.path.exists(os.path.join(self.dest, path, '.git')):
                    changed = True

        # Check for updates to existing modules
        if not changed:
            raise NotImplementedError("git action not yet implemented")
        #     # Fetch updates
        #     begin = get_submodule_versions(git_path, module, dest)
        #     cmd = [git_path, 'submodule', 'foreach', git_path, 'fetch']
        #     (rc, out, err) = module.run_command(cmd, check_rc=True, cwd=dest)
        #     if rc != 0:
        #         module.fail_json(msg="Failed to fetch submodules: %s" % out + err)

        #     if track_submodules:
        #         # Compare against submodule HEAD
        #         # FIXME: determine this from .gitmodules
        #         version = 'master'
        #         after = get_submodule_versions(git_path, module, dest, '%s/%s' % (remote, version))
        #         if begin != after:
        #             changed = True
        #     else:
        #         # Compare against the superproject's expectation
        #         cmd = [git_path, 'submodule', 'status']
        #         (rc, out, err) = module.run_command(cmd, check_rc=True, cwd=dest)
        #         if rc != 0:
        #             module.fail_json(msg='Failed to retrieve submodule status: %s' % out + err)
        #         for line in out.splitlines():
        #             if line[0] != ' ':
        #                 changed = True
        #                 break
        return changed

    def __post_init__(self):
        super().__post_init__()
        if self.separate_git_dir and self.bare:
            raise ValueError(f"{self.__class__}: separate_git_dir and bare cannot both be set")
        if self.archive_prefix is not None and self.archive is None:
            raise ValueError(f"{self.__class__}: archive_prefix needs archive to be set")
        if self.dest is None and self.allow_clone:
            raise ValueError(f"{self.__class__}: dest must be specified if clone is True")
        if isinstance(self.ssh_opts, str):
            self.ssh_opts = shlex.split(self.ssh_opts)

    def action_run(self, system: transilience.system.system):
        super().action_run(system)

        if self.executable is None:
            self.executable = shutil.which("git")
        elif not os.access(self.executable, os.x_ok):
            raise RuntimeError(f"invalid path {self.executable!r} for git")
        if self.executable is None:
            raise RuntimeError("git not found on this system")

        # certain features such as depth require a file:/// protocol for path based urls
        # so force a protocol here ...
        self.repo = self._normalise_repo_path(self.repo)

        if self.separate_git_dir:
            self.separate_git_dir = os.path.abspath(self.separate_git_dir)

        if self.accept_hostkey:
            if "StrictHostKeyChecking=no" not in self.ssh_opts:
                self.ssh_opts += ["-o", "StrictHostKeyChecking=no"]

        # If we have 'bare', 'dest' is a .git directory, and we don't have separate_git_dir
        # If we do not have 'bare', 'dest' is the worktree, and the .git
        #    directory is either "{dest}/.git", or "{separate_git_dir}"

        if not self.repo:
            # If we do not have 'dest', it looks like ansible takes it as "just
            #    fetch information about the remote repo": the code path when
            #    'dest' is missing seems to boil down to just:
            #
            #    # if there is no git configuration, do a clone operation unless:
            #    # * the user requested no clone (they just want info)
            #    # * we're doing a check mode test
            #    # In those cases we do an ls-remote
            #    if module.check_mode or not allow_clone:
            #        remote_head = get_remote_head(git_path, module, dest, version, repo, bare)
            #        result.update(changed=True, after=remote_head)
            #        if module._diff:
            #            diff = get_diff(module, git_path, dest, repo, remote,
            #                            depth, bare, result['before'], result['after'])
            #            if diff:
            #                result['diff'] = diff
            #        module.exit_json(**result)
            return

        # evaluate and set the umask before doing anything else
        with self.set_umask():
            self.dest = os.path.abspath(self.dest)
            repo_path = self.get_repo_path()

            # It might be that the current .git directory is not where
            # separate_git_dir wants it: if that is the case, move it
            if self.separate_git_dir and os.path.exists(repo_path) and self.separate_git_dir != repo_path:
                # TODO: review
                self.log.info("relocating git repo from %r to %r, keeping working tree at %s",
                              repo_path, self.separate_git_dir, self.dest)
                if not self.check:
                    self.relocate_repo(self.separate_git_dir, repo_path, self.dest)
                    repo_path = self.separate_git_dir
                self.set_changed()

            gitconfig = os.path.join(repo_path, 'config')

            local_mods = False
            if not os.path.exists(gitconfig):
                # If there is no git configuration, do a clone operation unless:
                # * the user requested no clone (they just want info)
                # * we're doing a check mode test
                # In those cases we do an ls-remote
                if self.check or not self.clone:
                    # remote_head = get_remote_head(git_path, module, dest, version, repo, bare)
                    self.log.info("Would clone %r to %r", self.repo, self.dest)
                    self.set_changed()
                    return

                # FIXME: check signatures before producing a working directory!

                # There's no git config, so clone
                self.do_clone()
            elif self.update:
                # Else do a pull
                local_mods = self.has_local_mods()
                if local_mods:
                    # Failure should happen regardless of check mode
                    if not self.force:
                        raise RuntimeError("Local modifications exist in repository (force=no)")
                    # If force and in non-check mode, do a reset
                    if not self.check:
                        self.do_reset()
                        self.log.info("%s: resetting local modifications", self.dest)
                        self.set_changed()

                # Update remote information if requested
                self.set_remote_url()

                # Fetch from upstream
                fetch_cmd = ['fetch', '--tags']
                fetch_cmd.extend([self.remote])
                self.run_git(fetch_cmd, cwd=self.dest)

                # TODO: check signatures HERE!

                if self.get_version() != self.get_remote_head():
                    self.log.info("%s: remote HEAD changed", self.dest)
                    self.set_changed()
                    if not self.check:
                        # result['after'] = get_version(module, git_path, dest)

                        # switch to version specified regardless of whether
                        # we got new revisions from the repository
                        if not self.bare:
                            self.log.info("%s: checkout new version", self.dest)
                            self.do_switch_version()
                            self.set_changed()

            # TODO: refactor from here

            # Deal with submodules
            submodules_updated = False
            if self.recursive and not self.bare:
                submodules_updated = self.submodules_fetch()
                if submodules_updated:
                    self.log.info("%s: submodules have been updated", self.dest)
                    self.set_changed()
                    if self.check:
                        return

                    # Switch to version specified
                    raise NotImplementedError("git action not yet implemented")
                    # self.submodule_update(git_path, module, dest, track_submodules, force=force)

            # # determine if we changed anything
            # result['after'] = get_version(module, git_path, dest)

            # if result['before'] != result['after'] or local_mods or submodules_updated or remote_url_changed:
            #     result.update(changed=True)
            #     if module._diff:
            #         diff = get_diff(module, git_path, dest, repo, remote,
            #                         depth, bare, result['before'], result['after'])
            #         if diff:
            #             result['diff'] = diff

            if self.archive:
                raise NotImplementedError("git action not yet implemented")
            #     # Git archive is not supported by all git servers, so
            #     # we will first clone and perform git archive from local directory
            #     if module.check_mode:
            #         result.update(changed=True)
            #         module.exit_json(**result)

            #     create_archive(git_path, module, dest, archive, archive_prefix, version, repo, result)

# TODO ~ TODO ~ TODO ~ TODO ~ TODO ~ TODO ~ TODO ~ TODO ~ TODO ~ TODO:


# import filecmp
# import os
# import re
# import shlex
# import stat
# import sys
# import shutil
# import tempfile
# from distutils.version import LooseVersion
#
# from ansible.module_utils.basic import AnsibleModule
# from ansible.module_utils.six import b, string_types
# from ansible.module_utils._text import to_native, to_text
#
# def get_submodule_update_params(module, git_path, cwd):
#     # or: git submodule [--quiet] update [--init] [-N|--no-fetch]
#     # [-f|--force] [--rebase] [--reference <repository>] [--merge]
#     # [--recursive] [--] [<path>...]
#
#     params = []
#
#     # run a bad submodule command to get valid params
#     cmd = "%s submodule update --help" % (git_path)
#     rc, stdout, stderr = module.run_command(cmd, cwd=cwd)
#     lines = stderr.split('\n')
#     update_line = None
#     for line in lines:
#         if 'git submodule [--quiet] update ' in line:
#             update_line = line
#     if update_line:
#         update_line = update_line.replace('[', '')
#         update_line = update_line.replace(']', '')
#         update_line = update_line.replace('|', ' ')
#         parts = shlex.split(update_line)
#         for part in parts:
#             if part.startswith('--'):
#                 part = part.replace('--', '')
#                 params.append(part)
#
#     return params
#
#
# def write_ssh_wrapper(module_tmpdir):
#     try:
#         # make sure we have full permission to the module_dir, which
#         # may not be the case if we're sudo'ing to a non-root user
#         if os.access(module_tmpdir, os.W_OK | os.R_OK | os.X_OK):
#             fd, wrapper_path = tempfile.mkstemp(prefix=module_tmpdir + '/')
#         else:
#             raise OSError
#     except (IOError, OSError):
#         fd, wrapper_path = tempfile.mkstemp()
#     fh = os.fdopen(fd, 'w+b')
#     template = b("""#!/bin/sh
# if [ -z "$GIT_SSH_OPTS" ]; then
#     BASEOPTS=""
# else
#     BASEOPTS=$GIT_SSH_OPTS
# fi
#
# # Let ssh fail rather than prompt
# BASEOPTS="$BASEOPTS -o BatchMode=yes"
#
# if [ -z "$GIT_KEY" ]; then
#     ssh $BASEOPTS "$@"
# else
#     ssh -i "$GIT_KEY" -o IdentitiesOnly=yes $BASEOPTS "$@"
# fi
# """)
#     fh.write(template)
#     fh.close()
#     st = os.stat(wrapper_path)
#     os.chmod(wrapper_path, st.st_mode | stat.S_IEXEC)
#     return wrapper_path
#
#
# def set_git_ssh(ssh_wrapper, key_file, ssh_opts):
#
#     if os.environ.get("GIT_SSH"):
#         del os.environ["GIT_SSH"]
#     os.environ["GIT_SSH"] = ssh_wrapper
#
#     if os.environ.get("GIT_KEY"):
#         del os.environ["GIT_KEY"]
#
#     if key_file:
#         os.environ["GIT_KEY"] = key_file
#
#     if os.environ.get("GIT_SSH_OPTS"):
#         del os.environ["GIT_SSH_OPTS"]
#
#     if ssh_opts:
#         os.environ["GIT_SSH_OPTS"] = ssh_opts
#
#
# def get_submodule_versions(git_path, module, dest, version='HEAD'):
#     cmd = [git_path, 'submodule', 'foreach', git_path, 'rev-parse', version]
#     (rc, out, err) = module.run_command(cmd, cwd=dest)
#     if rc != 0:
#         module.fail_json(
#             msg='Unable to determine hashes of submodules',
#             stdout=out,
#             stderr=err,
#             rc=rc)
#     submodules = {}
#     subm_name = None
#     for line in out.splitlines():
#         if line.startswith("Entering '"):
#             subm_name = line[10:-1]
#         elif len(line.strip()) == 40:
#             if subm_name is None:
#                 module.fail_json()
#             submodules[subm_name] = line.strip()
#             subm_name = None
#         else:
#             module.fail_json(msg='Unable to parse submodule hash line: %s' % line.strip())
#     if subm_name is not None:
#         module.fail_json(msg='Unable to find hash for submodule: %s' % subm_name)
#
#     return submodules
#
#
# def get_diff(module, git_path, dest, repo, remote, depth, bare, before, after):
#     ''' Return the difference between 2 versions '''
#     if before is None:
#         return {'prepared': '>> Newly checked out %s' % after}
#     elif before != after:
#         # Ensure we have the object we are referring to during git diff !
#         git_version_used = git_version(git_path, module)
#         fetch(git_path, module, repo, dest, after, remote, depth, bare, '', git_version_used)
#         cmd = '%s diff %s %s' % (git_path, before, after)
#         (rc, out, err) = module.run_command(cmd, cwd=dest)
#         if rc == 0 and out:
#             return {'prepared': out}
#         elif rc == 0:
#             return {'prepared': '>> No visual differences between %s and %s' % (before, after)}
#         elif err:
#             return {'prepared': '>> Failed to get proper diff between %s and %s:\n>> %s' % (before, after, err)}
#         else:
#             return {'prepared': '>> Failed to get proper diff between %s and %s' % (before, after)}
#     return {}
#
# def is_local_branch(git_path, module, dest, branch):
#     branches = get_branches(git_path, module, dest)
#     lbranch = '%s' % branch
#     if lbranch in branches:
#         return True
#     elif '* %s' % branch in branches:
#         return True
#     else:
#         return False
#
#
# def submodule_update(git_path, module, dest, track_submodules, force=False):
#     ''' init and update any submodules '''
#
#     # get the valid submodule params
#     params = get_submodule_update_params(module, git_path, dest)
#
#     # skip submodule commands if .gitmodules is not present
#     if not os.path.exists(os.path.join(dest, '.gitmodules')):
#         return (0, '', '')
#     cmd = [git_path, 'submodule', 'sync']
#     (rc, out, err) = module.run_command(cmd, check_rc=True, cwd=dest)
#     if 'remote' in params and track_submodules:
#         cmd = [git_path, 'submodule', 'update', '--init', '--recursive', '--remote']
#     else:
#         cmd = [git_path, 'submodule', 'update', '--init', '--recursive']
#     if force:
#         cmd.append('--force')
#     (rc, out, err) = module.run_command(cmd, cwd=dest)
#     if rc != 0:
#         module.fail_json(msg="Failed to init/update submodules: %s" % out + err)
#     return (rc, out, err)
#
#
# def git_version(git_path, module):
#     """return the installed version of git"""
#     cmd = "%s --version" % git_path
#     (rc, out, err) = module.run_command(cmd)
#     if rc != 0:
#         # one could fail_json here, but the version info is not that important,
#         # so let's try to fail only on actual git commands
#         return None
#     rematch = re.search('git version (.*)$', to_native(out))
#     if not rematch:
#         return None
#     return LooseVersion(rematch.groups()[0])
#
#
# def git_archive(git_path, module, dest, archive, archive_fmt, archive_prefix, version):
#     """ Create git archive in given source directory """
#     cmd = [git_path, 'archive', '--format', archive_fmt, '--output', archive, version]
#     if archive_prefix is not None:
#         cmd.insert(-1, '--prefix')
#         cmd.insert(-1, archive_prefix)
#     (rc, out, err) = module.run_command(cmd, cwd=dest)
#     if rc != 0:
#         module.fail_json(msg="Failed to perform archive operation",
#                          details="Git archive command failed to create "
#                                  "archive %s using %s directory."
#                                  "Error: %s" % (archive, dest, err))
#     return rc, out, err
#
#
# def create_archive(git_path, module, dest, archive, archive_prefix, version, repo, result):
#     """ Helper function for creating archive using git_archive """
#     all_archive_fmt = {'.zip': 'zip', '.gz': 'tar.gz', '.tar': 'tar',
#                        '.tgz': 'tgz'}
#     _, archive_ext = os.path.splitext(archive)
#     archive_fmt = all_archive_fmt.get(archive_ext, None)
#     if archive_fmt is None:
#         module.fail_json(msg="Unable to get file extension from "
#                              "archive file name : %s" % archive,
#                          details="Please specify archive as filename with "
#                                  "extension. File extension can be one "
#                                  "of ['tar', 'tar.gz', 'zip', 'tgz']")
#
#     repo_name = repo.split("/")[-1].replace(".git", "")
#
#     if os.path.exists(archive):
#         # If git archive file exists, then compare it with new git archive file.
#         # if match, do nothing
#         # if does not match, then replace existing with temp archive file.
#         tempdir = tempfile.mkdtemp()
#         new_archive_dest = os.path.join(tempdir, repo_name)
#         new_archive = new_archive_dest + '.' + archive_fmt
#         git_archive(git_path, module, dest, new_archive, archive_fmt, archive_prefix, version)
#
#         # filecmp is supposed to be efficient than md5sum checksum
#         if filecmp.cmp(new_archive, archive):
#             result.update(changed=False)
#             # Cleanup before exiting
#             try:
#                 shutil.rmtree(tempdir)
#             except OSError:
#                 pass
#         else:
#             try:
#                 shutil.move(new_archive, archive)
#                 shutil.rmtree(tempdir)
#                 result.update(changed=True)
#             except OSError as e:
#                 module.fail_json(msg="Failed to move %s to %s" %
#                                      (new_archive, archive),
#                                  details=u"Error occurred while moving : %s"
#                                          % to_text(e))
#     else:
#         # Perform archive from local directory
#         git_archive(git_path, module, dest, archive, archive_fmt, archive_prefix, version)
#         result.update(changed=True)
#
#
# # ===========================================
#
#
# if __name__ == '__main__':
#     main()
