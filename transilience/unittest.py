from __future__ import annotations
import contextlib


class LocalTestMixin:
    @contextlib.contextmanager
    def local_system(self):
        import mitogen
        from transilience.system import Mitogen
        broker = mitogen.master.Broker()
        router = mitogen.master.Router(broker)
        system = Mitogen("workdir", "local", router=router)
        try:
            yield system
        finally:
            broker.shutdown()
