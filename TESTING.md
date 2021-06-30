# Running unit tests

Some of Transilience actions, like apt or systemd, need a containerized system
to be tested.

To run the tests, I built a simple and very fast system of ephemeral containers based on
[systemd-nspawn](https://www.enricozini.org/blog/2021/debian/exploring-nspawn-for-cis/)
and [btrfs snapshots](https://www.enricozini.org/blog/2021/debian/nspawn-runner-btrfs/),
based on my work on [nspawn-runner](https://github.com/Truelite/nspawn-runner).

## Prerequisites

```
apt install systemd-container btrfs-progs eatmydata debootstrap
```

The `test_chroots/` directory needs to be on a `btrfs` filesystem. If you are
using another filesystem, you can create one of about 1.5Gb, and mount it on
`test_chroots`.

You can even create one on a file:

```
$ fallocate -l 1.5G testfile 
$ /usr/sbin/mkfs.btrfs testfile
$ sudo mount -o loop testfile test_chroots/
```

Once you have `test_chroots/` on btrfs, you can use `make-test-chroot` to
create the master chroot for the container:

```
sudo ./make-test-chroot buster
```

Note: this uses `eatmydata` to speed up debootstrap: you'll need the packages
`btrfs-progs` and `eatmydata` installed, or you can remove the 'eatmydata' call
from `make-test-chroot`.

## Running tests

To start and stop the nspawn containers, the unit tests need to be run as root
with `sudo`. The test suite drops root as soon as possible (see
`unittest.ProcessPrivs`) and changes to `$SUDO_UID` and `$SUDO_GID`.

They will temporarily regain root for as short as possible to start the
container, stop it, and open a Mitogen connection to it. Look for `privs.root`
in the code to see where this happens.

To run the test, once `test_chroots` is set up, use `sudo`
[`nose2`](https://docs.nose2.io/):

```
sudo nose2-3
```
