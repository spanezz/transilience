# transilience.actions.builtin

Documentation of the actions provided in module `transilience.actions.builtin`.


## apt

Same as Ansible's
[builtin.apt](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/apt_module.html).

`force_apt_get` is ignored: `apt-get` is always used.

Not yet implemented:

 * force
 * update_cache_retries
 * update_cache_retry_max_delay

Parameters:

* allow_unauthenticated [`bool`] = `False`
* autoclean [`bool`] = `False`
* autoremove [`bool`] = `False`
* cache_valid_time [`int`] = `0`
* deb [`List[str]`]
* default_release [`Optional[str]`] = `None`
* dpkg_options [`List[str]`]
* fail_on_autoremove [`bool`] = `False`
* force_apt_get [`bool`] = `False`
* install_recommends [`Optional[bool]`] = `None`
* name [`List[str]`]
* only_upgrade [`bool`] = `False`
* policy_rc_d [`Optional[int]`] = `None`
* purge [`bool`] = `False`
* state [`str`] = `'present'`
* update_cache [`bool`] = `False`
* upgrade [`str`] = `'no'`

## blockinfile

Same as Ansible's
[builtin.blockinfile](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/blockinfile_module.html).

Not yet implemented:

 * backup
 * unsafe_writes
 * validate

Parameters:

* block [`Union[str, bytes]`] = `''`
* create [`bool`] = `False`
* group [`Union[str, int, None]`] = `None`: set group, as gid or group name
* insertafter [`Optional[str]`] = `None`
* insertbefore [`Optional[str]`] = `None`
* marker [`str`] = `'# {mark} ANSIBLE MANAGED BLOCK'`
* marker_begin [`str`] = `'BEGIN'`
* marker_end [`str`] = `'END'`
* mode [`Union[str, int, None]`] = `None`: set mode, as octal or any expression `chmod` can use
* owner [`Union[str, int, None]`] = `None`: set owner, as uid or user name
* path [`str`] = `''`
* state [`Optional[str]`] = `None`

## command

Same as Ansible's
[builtin.command](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/command_module.html).

Not yet implemented:

 * strip_empty_ends

Parameters:

* argv [`List[str]`]
* chdir [`Optional[str]`] = `None`
* cmd [`Optional[str]`] = `None`
* creates [`Optional[str]`] = `None`
* removes [`Optional[str]`] = `None`
* stderr [`Optional[bytes]`] = `None`
* stdin [`Union[str, bytes, None]`] = `None`
* stdin_add_newline [`bool`] = `True`
* stdout [`Optional[bytes]`] = `None`

## copy

Same as Ansible's
[builtin.copy](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/copy_module.html).

Not yet implemented:

 * backup
 * decrypt
 * directory_mode
 * force
 * local_follow
 * remote_src
 * unsafe_writes
 * validate
 * src as directory

Parameters:

* checksum [`Optional[str]`] = `None`
* content [`Union[str, bytes, None]`] = `None`
* dest [`str`] = `''`
* follow [`bool`] = `True`
* group [`Union[str, int, None]`] = `None`: set group, as gid or group name
* mode [`Union[str, int, None]`] = `None`: set mode, as octal or any expression `chmod` can use
* owner [`Union[str, int, None]`] = `None`: set owner, as uid or user name
* src [`Optional[str]`] = `None`

## fail

Fail with a custom message

Same as Ansible's
[builtin.fail](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/fail_module.html).

Parameters:

* msg [`str`] = `'Failed as requested from task'`

## file

Same as Ansible's
[builtin.file](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/file_module.html).

Not yet implemented:

 * access_time
 * modification_time
 * modification_time_format
 * unsafe_writes

Parameters:

* follow [`bool`] = `True`: set attributes of symlink destinations instead of the symlinks themselves
* force [`bool`] = `False`
* group [`Union[str, int, None]`] = `None`: set group, as gid or group name
* mode [`Union[str, int, None]`] = `None`: set mode, as octal or any expression `chmod` can use
* owner [`Union[str, int, None]`] = `None`: set owner, as uid or user name
* path [`Optional[str]`] = `None`: Path to the file or directory being managed
* recurse [`bool`] = `False`: Recursively apply attributes (only used with state=directory)
* src [`Optional[str]`] = `None`: target of the link or hard link
* state [`str`] = `'file'`: Valid: file, directory, link, hard, touch, absent

## noop

Do nothing, successfully.

Parameters:

* changed [`bool`] = `False`: Set to True to pretend the action performed changes

## systemd

Same as Ansible's
[builtin.systemd](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/systemd_module.html)

Parameters:

* daemon_reexec [`bool`] = `False`
* daemon_reload [`bool`] = `False`
* enabled [`Optional[bool]`] = `None`
* force [`bool`] = `False`
* masked [`Optional[bool]`] = `None`
* no_block [`bool`] = `False`
* scope [`str`] = `'system'`
* state [`Optional[str]`] = `None`
* unit [`Optional[str]`] = `None`

