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
import os
from .action import Action
from . import builtin

if TYPE_CHECKING:
    import transilience.system


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
        _repo = os.path.expanduser(self.repo)
        if _repo.startswith('/'):
            self.repo = 'file://' + _repo

        if self.separate_git_dir:
            self.separate_git_dir = os.path.realpath(self.separate_git_dir)

        # evaluate and set the umask before doing anything else
        with self.set_umask():
            if self.accept_hostkey:
                if "StrictHostKeyChecking=no" not in self.ssh_opts:
                    self.ssh_opts += ["-o", "StrictHostKeyChecking=no"]

            gitconfig = None
            if self.dest:
                self.dest = os.path.abspath(self.dest)
                repo_path = self.get_repo_path()

                # It might be that the current .git directory is not where
                # separate_git_dir wants it: if that is the case, move it
                if self.separate_git_dir and os.path.exists(repo_path) and self.separate_git_dir != repo_path:
                    self.log.info("relocating git repo from %r to %r, keeping working tree at %s",
                                  repo_path, self.separate_git_dir, self.dest)
                    if not self.check:
                        self.relocate_repo(self.separate_git_dir, repo_path, self.dest)
                        repo_path = self.separate_git_dir
                    self.set_changed()

                gitconfig = os.path.join(repo_path, 'config')

            # TODO: git_version_used = git_version(git_path, module)

            local_mods = False
            if gitconfig is None or not os.path.exists(gitconfig):
                # if there is no git configuration, do a clone operation unless:
                # * the user requested no clone (they just want info)
                # * we're doing a check mode test
                # In those cases we do an ls-remote
                if self.check or not self.clone:
                    # remote_head = get_remote_head(git_path, module, dest, version, repo, bare)
                    self.set_changed()
                    return
                # there's no git config, so clone
                self.do_clone()
            elif self.update:
                raise NotImplementedError("git action not yet implemented")
            #     # else do a pull
            #     local_mods = has_local_mods(module, git_path, dest, bare)
            #     result['before'] = get_version(module, git_path, dest)
            #     if local_mods:
            #         # failure should happen regardless of check mode
            #         if not force:
            #             module.fail_json(msg="Local modifications exist in repository (force=no).", **result)
            #         # if force and in non-check mode, do a reset
            #         if not module.check_mode:
            #             reset(git_path, module, dest)
            #             result.update(changed=True, msg='Local modifications exist.')

            #     # exit if already at desired sha version
            #     if module.check_mode:
            #         remote_url = get_remote_url(git_path, module, dest, remote)
            #         remote_url_changed = remote_url and remote_url != repo and unfrackgitpath(remote_url) != unfrackgitpath(repo)
            #     else:
            #         remote_url_changed = set_remote_url(git_path, module, repo, dest, remote)
            #     result.update(remote_url_changed=remote_url_changed)

            #     if module.check_mode:
            #         remote_head = get_remote_head(git_path, module, dest, version, remote, bare)
            #         result.update(changed=(result['before'] != remote_head or remote_url_changed), after=remote_head)
            #         # FIXME: This diff should fail since the new remote_head is not fetched yet?!
            #         if module._diff:
            #             diff = get_diff(module, git_path, dest, repo, remote, depth, bare, result['before'], result['after'])
            #             if diff:
            #                 result['diff'] = diff
            #         module.exit_json(**result)
            #     else:
            #         fetch(git_path, module, repo, dest, version, remote, depth, bare, refspec, git_version_used, force=force)

            #     result['after'] = get_version(module, git_path, dest)

            # # switch to version specified regardless of whether
            # # we got new revisions from the repository
            # if not bare:
            #     switch_version(git_path, module, dest, remote, version, verify_commit, depth, gpg_whitelist)

            # # Deal with submodules
            # submodules_updated = False
            # if recursive and not bare:
            #     submodules_updated = submodules_fetch(git_path, module, remote, track_submodules, dest)
            #     if submodules_updated:
            #         result.update(submodules_changed=submodules_updated)

            #         if module.check_mode:
            #             result.update(changed=True, after=remote_head)
            #             module.exit_json(**result)

            #         # Switch to version specified
            #         submodule_update(git_path, module, dest, track_submodules, force=force)

            # # determine if we changed anything
            # result['after'] = get_version(module, git_path, dest)

            # if result['before'] != result['after'] or local_mods or submodules_updated or remote_url_changed:
            #     result.update(changed=True)
            #     if module._diff:
            #         diff = get_diff(module, git_path, dest, repo, remote, depth, bare, result['before'], result['after'])
            #         if diff:
            #             result['diff'] = diff

            # if archive:
            #     # Git archive is not supported by all git servers, so
            #     # we will first clone and perform git archive from local directory
            #     if module.check_mode:
            #         result.update(changed=True)
            #         module.exit_json(**result)

            #     create_archive(git_path, module, dest, archive, archive_prefix, version, repo, result)

# TODO ~ TODO ~ TODO ~ TODO ~ TODO ~ TODO ~ TODO ~ TODO ~ TODO ~ TODO:

# TODO: Turn into tests
# EXAMPLES = '''
# - name: Git checkout
#   ansible.builtin.git:
#     repo: 'https://foosball.example.org/path/to/repo.git'
#     dest: /srv/checkout
#     version: release-0.22
#
# - name: Read-write git checkout from github
#   ansible.builtin.git:
#     repo: git@github.com:mylogin/hello.git
#     dest: /home/mylogin/hello
#
# - name: Just ensuring the repo checkout exists
#   ansible.builtin.git:
#     repo: 'https://foosball.example.org/path/to/repo.git'
#     dest: /srv/checkout
#     update: no
#
# - name: Just get information about the repository whether or not it has already been cloned locally
#   ansible.builtin.git:
#     repo: 'https://foosball.example.org/path/to/repo.git'
#     dest: /srv/checkout
#     clone: no
#     update: no
#
# - name: Checkout a github repo and use refspec to fetch all pull requests
#   ansible.builtin.git:
#     repo: https://github.com/ansible/ansible-examples.git
#     dest: /src/ansible-examples
#     refspec: '+refs/pull/*:refs/heads/*'
#
# - name: Create git archive from repo
#   ansible.builtin.git:
#     repo: https://github.com/ansible/ansible-examples.git
#     dest: /src/ansible-examples
#     archive: /tmp/ansible-examples.zip
#
# - name: Clone a repo with separate git directory
#   ansible.builtin.git:
#     repo: https://github.com/ansible/ansible-examples.git
#     dest: /src/ansible-examples
#     separate_git_dir: /src/ansible-examples.git
#
# - name: Example clone of a single branch
#   ansible.builtin.git:
#     repo: https://github.com/ansible/ansible-examples.git
#     dest: /src/ansible-examples
#     single_branch: yes
#     version: master
#
# - name: Avoid hanging when http(s) password is missing
#   ansible.builtin.git:
#     repo: https://github.com/ansible/could-be-a-private-repo
#     dest: /src/from-private-repo
#   environment:
#     GIT_TERMINAL_PROMPT: 0 # reports "terminal prompts disabled" on missing password
#     # or GIT_ASKPASS: /bin/true # for git before version 2.3.0, reports "Authentication failed" on missing password
# '''

# RETURN = '''
# after:
#     description: Last commit revision of the repository retrieved during the update.
#     returned: success
#     type: str
#     sample: 4c020102a9cd6fe908c9a4a326a38f972f63a903
# before:
#     description: Commit revision before the repository was updated, "null" for new repository.
#     returned: success
#     type: str
#     sample: 67c04ebe40a003bda0efb34eacfb93b0cafdf628
# remote_url_changed:
#     description: Contains True or False whether or not the remote URL was changed.
#     returned: success
#     type: bool
#     sample: True
# warnings:
#     description: List of warnings if requested features were not available due to a too old git version.
#     returned: error
#     type: str
#     sample: git version is too old to fully support the depth argument. Falling back to full checkouts.
# git_dir_now:
#     description: Contains the new path of .git directory if it is changed.
#     returned: success
#     type: str
#     sample: /path/to/new/git/dir
# git_dir_before:
#     description: Contains the original path of .git directory if it is changed.
#     returned: success
#     type: str
#     sample: /path/to/old/git/dir
# '''
#
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
#
# def head_splitter(headfile, remote, module=None, fail_on_error=False):
#     '''Extract the head reference'''
#     # https://github.com/ansible/ansible-modules-core/pull/907
#
#     res = None
#     if os.path.exists(headfile):
#         rawdata = None
#         try:
#             f = open(headfile, 'r')
#             rawdata = f.readline()
#             f.close()
#         except Exception:
#             if fail_on_error and module:
#                 module.fail_json(msg="Unable to read %s" % headfile)
#         if rawdata:
#             try:
#                 rawdata = rawdata.replace('refs/remotes/%s' % remote, '', 1)
#                 refparts = rawdata.split(' ')
#                 newref = refparts[-1]
#                 nrefparts = newref.split('/', 2)
#                 res = nrefparts[-1].rstrip('\n')
#             except Exception:
#                 if fail_on_error and module:
#                     module.fail_json(msg="Unable to split head from '%s'" % rawdata)
#     return res
#
#
# def unfrackgitpath(path):
#     if path is None:
#         return None
#
#     # copied from ansible.utils.path
#     return os.path.normpath(os.path.realpath(os.path.expanduser(os.path.expandvars(path))))
#
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
# def get_version(module, git_path, dest, ref="HEAD"):
#     ''' samples the version of the git repo '''
#
#     cmd = "%s rev-parse %s" % (git_path, ref)
#     rc, stdout, stderr = module.run_command(cmd, cwd=dest)
#     sha = to_native(stdout).rstrip('\n')
#     return sha
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
# def has_local_mods(module, git_path, dest, bare):
#     if bare:
#         return False
#
#     cmd = "%s status --porcelain" % (git_path)
#     rc, stdout, stderr = module.run_command(cmd, cwd=dest)
#     lines = stdout.splitlines()
#     lines = list(filter(lambda c: not re.search('^\\?\\?.*$', c), lines))
#
#     return len(lines) > 0
#
#
# def reset(git_path, module, dest):
#     '''
#     Resets the index and working tree to HEAD.
#     Discards any changes to tracked files in working
#     tree since that commit.
#     '''
#     cmd = "%s reset --hard HEAD" % (git_path,)
#     return module.run_command(cmd, check_rc=True, cwd=dest)
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
#
# def get_remote_head(git_path, module, dest, version, remote, bare):
#     cloning = False
#     cwd = None
#     tag = False
#     if remote == module.params['repo']:
#         cloning = True
#     elif remote == 'file://' + os.path.expanduser(module.params['repo']):
#         cloning = True
#     else:
#         cwd = dest
#     if version == 'HEAD':
#         if cloning:
#             # cloning the repo, just get the remote's HEAD version
#             cmd = '%s ls-remote %s -h HEAD' % (git_path, remote)
#         else:
#             head_branch = get_head_branch(git_path, module, dest, remote, bare)
#             cmd = '%s ls-remote %s -h refs/heads/%s' % (git_path, remote, head_branch)
#     elif is_remote_branch(git_path, module, dest, remote, version):
#         cmd = '%s ls-remote %s -h refs/heads/%s' % (git_path, remote, version)
#     elif is_remote_tag(git_path, module, dest, remote, version):
#         tag = True
#         cmd = '%s ls-remote %s -t refs/tags/%s*' % (git_path, remote, version)
#     else:
#         # appears to be a sha1.  return as-is since it appears
#         # cannot check for a specific sha1 on remote
#         return version
#     (rc, out, err) = module.run_command(cmd, check_rc=True, cwd=cwd)
#     if len(out) < 1:
#         module.fail_json(msg="Could not determine remote revision for %s" % version, stdout=out, stderr=err, rc=rc)
#
#     out = to_native(out)
#
#     if tag:
#         # Find the dereferenced tag if this is an annotated tag.
#         for tag in out.split('\n'):
#             if tag.endswith(version + '^{}'):
#                 out = tag
#                 break
#             elif tag.endswith(version):
#                 out = tag
#
#     rev = out.split()[0]
#     return rev
#
#
# def get_branches(git_path, module, dest):
#     branches = []
#     cmd = '%s branch --no-color -a' % (git_path,)
#     (rc, out, err) = module.run_command(cmd, cwd=dest)
#     if rc != 0:
#         module.fail_json(msg="Could not determine branch data - received %s" % out, stdout=out, stderr=err)
#     for line in out.split('\n'):
#         if line.strip():
#             branches.append(line.strip())
#     return branches
#
#
#
#
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
# def is_not_a_branch(git_path, module, dest):
#     branches = get_branches(git_path, module, dest)
#     for branch in branches:
#         if branch.startswith('* ') and ('no branch' in branch or 'detached from' in branch or 'detached at' in branch):
#             return True
#     return False
#
#
# def get_head_branch(git_path, module, dest, remote, bare=False):
#     '''
#     Determine what branch HEAD is associated with.  This is partly
#     taken from lib/ansible/utils/__init__.py.  It finds the correct
#     path to .git/HEAD and reads from that file the branch that HEAD is
#     associated with.  In the case of a detached HEAD, this will look
#     up the branch in .git/refs/remotes/<remote>/HEAD.
#     '''
#     try:
#         repo_path = get_repo_path(dest, bare)
#     except (IOError, ValueError) as err:
#         # No repo path found
#         """``.git`` file does not have a valid format for detached Git dir."""
#         module.fail_json(
#             msg='Current repo does not have a valid reference to a '
#             'separate Git dir or it refers to the invalid path',
#             details=to_text(err),
#         )
#     # Read .git/HEAD for the name of the branch.
#     # If we're in a detached HEAD state, look up the branch associated with
#     # the remote HEAD in .git/refs/remotes/<remote>/HEAD
#     headfile = os.path.join(repo_path, "HEAD")
#     if is_not_a_branch(git_path, module, dest):
#         headfile = os.path.join(repo_path, 'refs', 'remotes', remote, 'HEAD')
#     branch = head_splitter(headfile, remote, module=module, fail_on_error=True)
#     return branch
#
#
# def get_remote_url(git_path, module, dest, remote):
#     '''Return URL of remote source for repo.'''
#     command = [git_path, 'ls-remote', '--get-url', remote]
#     (rc, out, err) = module.run_command(command, cwd=dest)
#     if rc != 0:
#         # There was an issue getting remote URL, most likely
#         # command is not available in this version of Git.
#         return None
#     return to_native(out).rstrip('\n')
#
#
# def set_remote_url(git_path, module, repo, dest, remote):
#     ''' updates repo from remote sources '''
#     # Return if remote URL isn't changing.
#     remote_url = get_remote_url(git_path, module, dest, remote)
#     if remote_url == repo or unfrackgitpath(remote_url) == unfrackgitpath(repo):
#         return False
#
#     command = [git_path, 'remote', 'set-url', remote, repo]
#     (rc, out, err) = module.run_command(command, cwd=dest)
#     if rc != 0:
#         label = "set a new url %s for %s" % (repo, remote)
#         module.fail_json(msg="Failed to %s: %s %s" % (label, out, err))
#
#     # Return False if remote_url is None to maintain previous behavior
#     # for Git versions prior to 1.7.5 that lack required functionality.
#     return remote_url is not None
#
#
# def fetch(git_path, module, repo, dest, version, remote, depth, bare, refspec, git_version_used, force=False):
#     ''' updates repo from remote sources '''
#     set_remote_url(git_path, module, repo, dest, remote)
#     commands = []
#
#     fetch_str = 'download remote objects and refs'
#     fetch_cmd = [git_path, 'fetch']
#
#     refspecs = []
#     if depth:
#         # try to find the minimal set of refs we need to fetch to get a
#         # successful checkout
#         currenthead = get_head_branch(git_path, module, dest, remote)
#         if refspec:
#             refspecs.append(refspec)
#         elif version == 'HEAD':
#             refspecs.append(currenthead)
#         elif is_remote_branch(git_path, module, dest, repo, version):
#             if currenthead != version:
#                 # this workaround is only needed for older git versions
#                 # 1.8.3 is broken, 1.9.x works
#                 # ensure that remote branch is available as both local and remote ref
#                 refspecs.append('+refs/heads/%s:refs/heads/%s' % (version, version))
#             refspecs.append('+refs/heads/%s:refs/remotes/%s/%s' % (version, remote, version))
#         elif is_remote_tag(git_path, module, dest, repo, version):
#             refspecs.append('+refs/tags/' + version + ':refs/tags/' + version)
#         if refspecs:
#             # if refspecs is empty, i.e. version is neither heads nor tags
#             # assume it is a version hash
#             # fall back to a full clone, otherwise we might not be able to checkout
#             # version
#             fetch_cmd.extend(['--depth', str(depth)])
#
#     if not depth or not refspecs:
#         # don't try to be minimalistic but do a full clone
#         # also do this if depth is given, but version is something that can't be fetched directly
#         if bare:
#             refspecs = ['+refs/heads/*:refs/heads/*', '+refs/tags/*:refs/tags/*']
#         else:
#             # ensure all tags are fetched
#             if git_version_used >= LooseVersion('1.9'):
#                 fetch_cmd.append('--tags')
#             else:
#                 # old git versions have a bug in --tags that prevents updating existing tags
#                 commands.append((fetch_str, fetch_cmd + [remote]))
#                 refspecs = ['+refs/tags/*:refs/tags/*']
#         if refspec:
#             refspecs.append(refspec)
#
#     if force:
#         fetch_cmd.append('--force')
#
#     fetch_cmd.extend([remote])
#
#     commands.append((fetch_str, fetch_cmd + refspecs))
#
#     for (label, command) in commands:
#         (rc, out, err) = module.run_command(command, cwd=dest)
#         if rc != 0:
#             module.fail_json(msg="Failed to %s: %s %s" % (label, out, err), cmd=command)
#
#
# def submodules_fetch(git_path, module, remote, track_submodules, dest):
#     changed = False
#
#     if not os.path.exists(os.path.join(dest, '.gitmodules')):
#         # no submodules
#         return changed
#
#     gitmodules_file = open(os.path.join(dest, '.gitmodules'), 'r')
#     for line in gitmodules_file:
#         # Check for new submodules
#         if not changed and line.strip().startswith('path'):
#             path = line.split('=', 1)[1].strip()
#             # Check that dest/path/.git exists
#             if not os.path.exists(os.path.join(dest, path, '.git')):
#                 changed = True
#
#     # Check for updates to existing modules
#     if not changed:
#         # Fetch updates
#         begin = get_submodule_versions(git_path, module, dest)
#         cmd = [git_path, 'submodule', 'foreach', git_path, 'fetch']
#         (rc, out, err) = module.run_command(cmd, check_rc=True, cwd=dest)
#         if rc != 0:
#             module.fail_json(msg="Failed to fetch submodules: %s" % out + err)
#
#         if track_submodules:
#             # Compare against submodule HEAD
#             # FIXME: determine this from .gitmodules
#             version = 'master'
#             after = get_submodule_versions(git_path, module, dest, '%s/%s' % (remote, version))
#             if begin != after:
#                 changed = True
#         else:
#             # Compare against the superproject's expectation
#             cmd = [git_path, 'submodule', 'status']
#             (rc, out, err) = module.run_command(cmd, check_rc=True, cwd=dest)
#             if rc != 0:
#                 module.fail_json(msg='Failed to retrieve submodule status: %s' % out + err)
#             for line in out.splitlines():
#                 if line[0] != ' ':
#                     changed = True
#                     break
#     return changed
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
# def set_remote_branch(git_path, module, dest, remote, version, depth):
#     """set refs for the remote branch version
#
#     This assumes the branch does not yet exist locally and is therefore also not checked out.
#     Can't use git remote set-branches, as it is not available in git 1.7.1 (centos6)
#     """
#
#     branchref = "+refs/heads/%s:refs/heads/%s" % (version, version)
#     branchref += ' +refs/heads/%s:refs/remotes/%s/%s' % (version, remote, version)
#     cmd = "%s fetch --depth=%s %s %s" % (git_path, depth, remote, branchref)
#     (rc, out, err) = module.run_command(cmd, cwd=dest)
#     if rc != 0:
#         module.fail_json(msg="Failed to fetch branch from remote: %s" % version, stdout=out, stderr=err, rc=rc)
#
#
# def switch_version(git_path, module, dest, remote, version, verify_commit, depth, gpg_whitelist):
#     cmd = ''
#     if version == 'HEAD':
#         branch = get_head_branch(git_path, module, dest, remote)
#         (rc, out, err) = module.run_command("%s checkout --force %s" % (git_path, branch), cwd=dest)
#         if rc != 0:
#             module.fail_json(msg="Failed to checkout branch %s" % branch,
#                              stdout=out, stderr=err, rc=rc)
#         cmd = "%s reset --hard %s/%s --" % (git_path, remote, branch)
#     else:
#         # FIXME check for local_branch first, should have been fetched already
#         if is_remote_branch(git_path, module, dest, remote, version):
#             if depth and not is_local_branch(git_path, module, dest, version):
#                 # git clone --depth implies --single-branch, which makes
#                 # the checkout fail if the version changes
#                 # fetch the remote branch, to be able to check it out next
#                 set_remote_branch(git_path, module, dest, remote, version, depth)
#             if not is_local_branch(git_path, module, dest, version):
#                 cmd = "%s checkout --track -b %s %s/%s" % (git_path, version, remote, version)
#             else:
#                 (rc, out, err) = module.run_command("%s checkout --force %s" % (git_path, version), cwd=dest)
#                 if rc != 0:
#                     module.fail_json(msg="Failed to checkout branch %s" % version, stdout=out, stderr=err, rc=rc)
#                 cmd = "%s reset --hard %s/%s" % (git_path, remote, version)
#         else:
#             cmd = "%s checkout --force %s" % (git_path, version)
#     (rc, out1, err1) = module.run_command(cmd, cwd=dest)
#     if rc != 0:
#         if version != 'HEAD':
#             module.fail_json(msg="Failed to checkout %s" % (version),
#                              stdout=out1, stderr=err1, rc=rc, cmd=cmd)
#         else:
#             module.fail_json(msg="Failed to checkout branch %s" % (branch),
#                              stdout=out1, stderr=err1, rc=rc, cmd=cmd)
#
#     if verify_commit:
#         verify_commit_sign(git_path, module, dest, version, gpg_whitelist)
#
#     return (rc, out1, err1)
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
