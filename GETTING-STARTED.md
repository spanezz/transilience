# Getting started with Transilience

This is all still a prototype, and is subject to change as experiments
continue. However, to play with it, here's how to setup a simple playbook.

Playbooks are Python scripts. Here's the basic boilerplate:

```py
#!/usr/bin/python3

from dataclasses import dataclass
import sys
from transilience import Playbook, Host

@dataclass
class Server(Host):
    # Host vars go here
    ...


class Play(Playbook):
    """
    Name of this playbook
    """

    def hosts(self):
        # See https://mitogen.networkgenomics.com/api.html#connection-methods
        # "ssh" is the name of the Router method: in this case `Router.ssh()`
        # All arguments after "ssh" are forwarded to `Router.ssh()`
        yield Server(name="server", args={
            "type": "Mitogen",
            "method": "ssh",
            "hostname": "server.example.org",
            "username": "root",
        })
        # Alternatively, you can execute on the local system, without Mitogen
        # yield Server(name="local", type="Local")

    def start(self, runner):

        # Add roles and start sending actions to be executed. All arguments after
        # the role name are forwarded to the Role constructor
        runner.add_role("mail_aliases", aliases={
            "transilience": "enrico",
        })


if __name__ == "__main__":
    sys.exit(VPS().main())
```

The `Playbook` class adds a basic command line interface:

```
$ ./provision  --help
usage: provision [-h] [-v] [--debug]

Name of this playbook

optional arguments:
  -h, --help     show this help message and exit
  -v, --verbose  verbose output
  --debug        verbose output
```

Roles are loaded as normal Python `roles.<name>` modules, which are expected to
contain a class called `Role`:

```
$ mkdir roles
$ edit roles/mail_aliases.py
```

```py
from __future__ import annotations
from typing import Dict
from dataclasses import dataclass, field
from transilience import role
from transilience.actions import builtin


@dataclass
class Role(role.Role):
    # Role-level variables
    aliases: Dict[str, str] = field(default_factory=dict)

    def start(self):
        # Role-level variables are automatically exported to templates
        aliases = self.render_string("""{% for name, dest in aliases.items() %}
{{name}}: {{dest}}
{% endfor %}""")[

        self.task(builtin.blockinfile(
            path="/etc/aliases",
            block=aliases,
        ), name="configure /etc/aliases",
           notify=RereadAliases,
        )


@dataclass
class RereadAliases(role.Role):
    def start(self):
        self.task(builtin.command(argv=["newaliases"]))
```

Finally, run the playbook:

```
$ ./provision
2021-06-14 18:23:16 server: [changed 0.003s] mail_aliases configure /etc/aliases
2021-06-14 18:23:17 server: [changed 0.203s] RereadAliases Run newaliases
2021-06-18 15:57:53 server: 2 total actions: 0 unchanged, 2 changed, 0 skipped, 0 failed, 0 not executed.
```
