from __future__ import annotations


class LocalTestMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import mitogen
        from transilience.system import Mitogen
        cls.broker = mitogen.master.Broker()
        cls.router = mitogen.master.Router(cls.broker)
        cls.system = Mitogen("workdir", "local", router=cls.router)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.broker.shutdown()
