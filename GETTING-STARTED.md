# Getting started with Transilience

This is all still a prototype, and is subject to change as experiments
continue. However, to play with it, here's how to setup a simple playbook.

Playbooks are Python scripts. Here's the basic boilerplate:

```py
#!/usr/bin/python3

import sys
from transilience.system import Mitogen, Local
from transilience.runner import Runner


@Runner.cli
def main():
    # See https://mitogen.networkgenomics.com/api.html#connection-methods
    # "ssh" is the name of the Router method: in this case `Router.ssh()`
    # All arguments after "ssh" are forwarded to `Router.ssh()`
    system = Mitogen("server", "ssh", hostname="server.example.org", username="root")

    # Alternatively, you can execute on the local system, without Mitogen
    # system = Local()

    # Instantiate a pipelined runner sending actions to this system
    runner = Runner(system)

    # Add roles and start sending actions to be executed. All arguments after
    the role name are forwarded to the Role constructor
    runner.add_role("mail_aliases", aliases={
        "transilience": "enrico",
    })

    # Run until all roles are done
    runner.main()


if __name__ == "__main__":
    sys.exit(main())
```

`@Runner.cli` adds a basic command line interface:

```
$ ./provision  --help
usage: provision [-h] [-v] [--debug]

Provision a system

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
from transilience import role
from transilience.actions import builtin
from .handlers import RereadAliases


class Role(role.Role):
    def __init__(self, aliases=Dict[str, str]):
        super().__init__()
        self.aliases = aliases

    def main(self):
        aliases = [
            f"{name}: {dest}"
            for name, dest in self.aliases.items()
        ]

        self.add(builtin.blockinfile(
            path="/etc/aliases",
            block="\n".join(aliases)
        ), name="configure /etc/aliases",
           notify=RereadAliases,
        )


class RereadAliases(role.Role):
    def main(self):
        self.add(builtin.command(argv=["newaliases"]))
```

Finally, run the playbook:

```
$ ./provision
2021-06-14 18:23:16 [changed 0.003s] mail_aliases configure /etc/aliases
2021-06-14 18:23:17 [changed 0.203s] RereadAliases Run newaliases
```
