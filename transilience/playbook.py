from __future__ import annotations
from typing import TYPE_CHECKING, Sequence
import threading
import argparse
import inspect
import logging
import sys
try:
    import coloredlogs
except ModuleNotFoundError:
    coloredlogs = None
from transilience.runner import Runner


if TYPE_CHECKING:
    from transilience.hosts import Host


class Playbook:
    def __init__(self):
        self.progress = logging.getLogger("progress")

    def setup_logging(self):
        FORMAT = "%(asctime)-15s %(levelname)s %(name)s %(message)s"
        PROGRESS_FORMAT = "%(asctime)-15s %(message)s"
        if self.args.debug:
            log_level = logging.DEBUG
        elif self.args.verbose:
            log_level = logging.INFO
        else:
            log_level = logging.WARN

        progress_formatter = None
        if coloredlogs is not None:
            coloredlogs.install(level=log_level, fmt=FORMAT, stream=sys.stderr)
            if log_level > logging.INFO:
                progress_formatter = coloredlogs.ColoredFormatter(fmt=PROGRESS_FORMAT)
        else:
            logging.basicConfig(level=log_level, stream=sys.stderr, format=FORMAT)
            if log_level > logging.INFO:
                progress_formatter = logging.Formatter(fmt=PROGRESS_FORMAT)

        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(progress_formatter)
        self.progress.addHandler(handler)
        self.progress.setLevel(logging.INFO)
        self.progress.propagate = False

    def make_argparser(self):
        description = inspect.getdoc(self)
        if not description:
            description = "Provision systems"

        parser = argparse.ArgumentParser(description=description)
        parser.add_argument("-v", "--verbose", action="store_true",
                            help="verbose output")
        parser.add_argument("--debug", action="store_true",
                            help="verbose output")
        parser.add_argument("-C", "--check", action="store_true",
                            help="do not perform changes, but check if changes would be needed")

        return parser

    def hosts(self) -> Sequence[Host]:
        """
        Generate a sequence with all the systems on which the playbook needs to run
        """
        return ()

    def start(self, runner: Runner):
        """
        Start the playbook on the given runner.

        This method is called once for each system returned by systems()
        """
        raise NotImplementedError(f"{self.__class__.__name__}.start is not implemented")

    def main(self):
        parser = self.make_argparser()
        self.args = parser.parse_args()
        self.setup_logging()

        # Start all the runners in separate threads
        threads = []
        for host in self.hosts():
            runner = Runner(host, check_mode=self.args.check)
            self.start(runner)
            t = threading.Thread(target=runner.main)
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()
