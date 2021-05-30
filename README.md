# Transilience

Python provisioning library.

Ansible-like modules. Declarative actions. Generate actions with Python. No
templatized YAML. Mitogen-based connections.

Early stage proof of concept prototype.

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

Look into transilience.actions for available actions.

Feel free to add new ones!


## Adding actions

Actions are subclasses of `transilience.action.Action`.

The `__post_init__` constructor can do preprocessing client-side.

`run()` is the main function executed on the remote side.

dataclass attributes are transmitted as they are on the remote side. See
[Mitogen RPC serialization rules](https://mitogen.networkgenomics.com/getting_started.html#rpc-serialization-rules)
for what types can be used.


## Why the name

> **Transilience**: n. *A leap across or from one thing to another*
>  [1913 Webster]

Set in the Hainish Cycle world from Ursula Le Guin novels, Transilience appears
in the novels "A Fisherman of the Inland Sea", and "The Shobies' Story".
