"""No-game substitute for the live application; startup, HTTP and CLI remain real."""

import sys
import time
from pathlib import Path

# Explicitly import the same source/installed wheel as the invoking qualification.
sys.path.insert(0, sys.argv.pop(1))
from shadowbane_lab import cli
from shadowbane_lab.cli_commands import manager

root = Path(sys.argv[3]).parent  # original arguments: manager app <manifest>


class NoGameApplication:
    def __init__(self, *args, **kwargs):
        pass

    def status(self):
        deadline = time.monotonic() + 30
        while not (root / "allow-listener").exists():
            if (root / "stop-test").exists():
                raise RuntimeError("test shutdown before listener")
            if time.monotonic() >= deadline:
                raise RuntimeError("test listener release timed out")
            time.sleep(0.02)
        return {"ok": True}

    def supervise(self):
        if (root / "stop-test").exists():
            raise KeyboardInterrupt

    def execute(self, *args, **kwargs):
        raise AssertionError("This fixture permits no gameplay actions")

    def revoke_all_workers(self, **kwargs):
        pass


manager.LiveConfiguredManagerApplication = NoGameApplication
raise SystemExit(cli.main(sys.argv[1:]))
