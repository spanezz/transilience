from __future__ import annotations
import unittest
import tempfile
import os
import yaml
from transilience.unittest import LocalTestMixin, LocalMitogenTestMixin


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
        zf.close()

    @classmethod
    def tearDownClass(cls):
        cls.zipfile.close()
        super().tearDownClass()

    def test_load_yaml(self):
        from transilience.ansible import ZipRoleLoader
        loader = ZipRoleLoader("test", self.zipfile.name)
        loader.load()
        role_cls = loader.get_role_class()
        with tempfile.TemporaryDirectory() as workdir:
            self.run_role(role_cls, workdir=workdir)

            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "rt") as fd:
                self.assertEqual(fd.read(), "♥")


class TestLocal(ZipappTests, LocalTestMixin, unittest.TestCase):
    pass


class TestMitogen(ZipappTests, LocalMitogenTestMixin, unittest.TestCase):
    pass
