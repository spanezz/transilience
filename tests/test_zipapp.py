from __future__ import annotations
import unittest
import tempfile
import os
import yaml
from transilience.unittest import LocalTestMixin, LocalMitogenTestMixin
from transilience.role import Role


class ZipappTests:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.zipfile = tempfile.NamedTemporaryFile(mode="w+b", suffix=".zip")
        import zipfile
        zf = zipfile.PyZipFile(cls.zipfile, mode='w', optimize=2)
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
            "",
            "@role.with_facts([actions.facts.Platform])",
            "class Role(role.Role):",
            "    workdir: str = None",
            "    def all_facts_available(self):",
            "        self.add(builtin.copy(",
            "            src=self.lookup_file('files/testfile'),",
            "            dest=self.workdir,",
            "        ))",
        ]
        zf.writestr("roles/__init__.py", "")
        zf.writestr("roles/test1.py", "\n".join(role))
        zf.writestr("roles/test1/files/testfile", "♥")
        zf.close()

    @classmethod
    def tearDownClass(cls):
        cls.zipfile.close()
        super().tearDownClass()

    def test_load_yaml(self):
        role_cls = Role.load_zip_ansible("test", self.zipfile.name)
        with tempfile.TemporaryDirectory() as workdir:
            self.run_role(role_cls, workdir=workdir)

            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "rt") as fd:
                self.assertEqual(fd.read(), "♥")

    def test_load_module(self):
        role_cls = Role.load_zip_module("test1", self.zipfile.name)
        with tempfile.TemporaryDirectory() as workdir:
            self.run_role(role_cls, workdir=workdir)

            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "rt") as fd:
                self.assertEqual(fd.read(), "♥")


class TestLocal(ZipappTests, LocalTestMixin, unittest.TestCase):
    pass


class TestMitogen(ZipappTests, LocalMitogenTestMixin, unittest.TestCase):
    pass
