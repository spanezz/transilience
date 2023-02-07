# Transilience

Python provisioning library.

Ansible-like modules. Declarative actions. Generate actions with Python. No
templatized YAML. Mitogen-based connections.

Early stage proof of concept prototype.

If you want to try playing with Transilience, see [GETTING-STARTED.md](GETTING-STARTED.md) for a
guide on setting up a simple playbook.

## Usage

```py
import mitogen
from transilience.system import Mitogen
from transilience import actions

# Mitogen setup
broker = mitogen.master.Broker()
router = mitogen.master.Router(cls.broker)

# Access the system 'workdir' as a 'local' connection.
# You can use any connection method from
# https://mitogen.networkgenomics.com/api.html#connection-methods
# and arguments to the Mitogen constructor will be forwarded to it
system = Mitogen("workdir", "local", router=cls.router)

# Run a playbook
system.system.run_actions([
    actions.File(
	name="Create test dir",
	path="/tmp/test",
	state="directory",
    ),
    actions.File(
	name="Create test file",
	path="/tmp/test/testfile",
	state="touch",
    ),
])
```

## Requirements

On the local system:

* Required: Python version 3.7 or later.
* Optional: [Mitogen](https://mitogen.networkgenomics.com/) to connect to
  remote systems; [Jinja2](https://jinja.palletsprojects.com/en/3.0.x/) for
  ansible-like templates.

On remote systems:

* Python 3 (tested on 3.7)

## Existing actions

See [actions_builtin.md](actions_builtin.md).


## Design

The basic ideas of Transilience:

 * Provisioning building blocks that you can reuse freely and follow a
   well-known API
 * A way to run them anywhere Mythogen can reach
 * Logic coded in straightforward Python instead of templated YAML

In other words:

 * `transilience.actions` is a collection of idempotent, reusable provisioning
   macros in the style of Ansible tasks. They can be used without transilience.
 * `transilience.system` contains executors that can run actions anywhere
   [Mitogen](https://mitogen.networkgenomics.com/api.html#connection-methods)
   can reach
 * For provisioning, one can write a simple Python script that feeds Actions to
   local or remote systems. If an action depends on the results of previous
   actions, the logic can be coded in simple Python.


## Adding actions

Actions are subclasses of `transilience.action.Action`, which is a
[dataclass](https://docs.python.org/3/library/dataclasses.html) with an extra
`run()` method.

The `__post_init__` constructor can do preprocessing client-side.

`run()` is the main function executed on the remote side.

dataclass attributes are transmitted as they are on the remote side, filled
further as the action is performed, and then sent back. See [Mitogen RPC serialization rules](https://mitogen.networkgenomics.com/getting_started.html#rpc-serialization-rules)
for what types can be used.


## Why the name

> **Transilience**: n. *A leap across or from one thing to another*
>  [1913 Webster]

Set in the Hainish Cycle world from Ursula Le Guin novels, Transilience appears
in the novels "A Fisherman of the Inland Sea", and "The Shobies' Story".


## Copyright

Transilience is licensed under the GNU General Public License v3.0 or later.

See [LICENSE](LICENSE) for the full text.

Backends for the `user` action are adapted from
[Ansible](https://github.com/ansible/ansible)'s sources.
