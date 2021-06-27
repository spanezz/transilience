from __future__ import annotations
from unittest import TestCase
import tempfile
import os
import yaml
from transilience.unittest import LocalTestMixin
from transilience.hosts import Host
from transilience.runner import Runner


class TestParseYaml(LocalTestMixin, TestCase):
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

    def test_load_role(self):
        from transilience.ansible import ZipRoleLoader
        loader = ZipRoleLoader("test", self.zipfile.name)
        loader.load()
        role_cls = loader.get_role_class()
        with tempfile.TemporaryDirectory() as workdir:
            host = Host(name="local", type="Local")
            runner = Runner(host)
            runner.add_role(role_cls, workdir=workdir)
            with self.assertLogs():
                runner.main()

            testfile = os.path.join(workdir, "testfile")
            with open(testfile, "rt") as fd:
                self.assertEqual(fd.read(), "♥")
