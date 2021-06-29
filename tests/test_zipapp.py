from __future__ import annotations
import unittest
import tempfile
import os
import yaml
from transilience.unittest import LocalTestMixin, LocalMitogenTestMixin
from transilience.role import Loader


class ZipappTests:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.zipfile = tempfile.NamedTemporaryFile(mode="w+b", suffix=".zip")
        import zipfile
        with zipfile.PyZipFile(cls.zipfile, mode='w', optimize=2) as zf:
            # Create a directory entry. There seems to be nothing to do this in
            # zipfile's standard API, so I looked into zipfile sources to see
            # what it does in ZipInfo.from_file and ZipFile.write()
            role_info = zipfile.ZipInfo("roles/")
            role_info.external_attr = 0o700 << 16  # Unix attributes
            role_info.file_size = 0
            role_info.external_attr |= 0x10  # MS-DOS directory flag
            role_info.compress_size = 0
            role_info.CRC = 0
            zf.writestr(role_info, b"")

            role = [
                {
                    "name": "test task",
                    "copy": {
                        "src": "testfile",
                        "dest": "{{workdir}}/testfile",
                    },
                }
            ]
            zf.writestr("roles/test/tasks/main.yaml", yaml.dump(role))
            zf.writestr("roles/test/files/testfile", "♥")

            role = [
                "from __future__ import annotations",
                "from transilience import actions, role",
                "from transilience.actions import builtin",
                "import os",
                "",
                "@role.with_facts([actions.facts.Platform])",
                "class Role(role.Role):",
                "    workdir: str = None",
                "    def all_facts_available(self):",
                "        self.add(builtin.copy(",
                "            src=self.lookup_file('files/testfile'),",
                "            dest=os.path.join(self.workdir, 'testfile'),",
                "        ))",
            ]
            zf.writestr("roles/test1.py", "\n".join(role))
            zf.writestr("roles/test1/files/testfile", "♥")

    @classmethod
    def tearDownClass(cls):
        cls.zipfile.close()
        super().tearDownClass()

    def test_load_yaml(self):
        loader = Loader.create_from_path(self.zipfile.name)
        self.assertIsNotNone(loader)
        role_cls = loader.load("test")
        with tempfile.TemporaryDirectory() as workdir:
            self.run_role(role_cls, workdir=workdir)

            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "rt") as fd:
                self.assertEqual(fd.read(), "♥")

    def test_load_module(self):
        loader = Loader.create_from_path(self.zipfile.name)
        self.assertIsNotNone(loader)
        role_cls = loader.load("test1")
        with tempfile.TemporaryDirectory() as workdir:
            self.run_role(role_cls, workdir=workdir)

            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "rt") as fd:
                self.assertEqual(fd.read(), "♥")


class TestLocal(ZipappTests, LocalTestMixin, unittest.TestCase):
    pass


class TestMitogen(ZipappTests, LocalMitogenTestMixin, unittest.TestCase):
    pass
