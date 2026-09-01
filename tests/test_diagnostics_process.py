from __future__ import annotations

import os

import pytest

from shadowbane_lab.diagnostics.process import WindowsProcessProbe


@pytest.mark.skipif(os.name != "nt", reason="Windows process handles are required")
def test_windows_process_probe_can_wait_on_its_open_handle() -> None:
    sample = WindowsProcessProbe().sample(os.getpid())

    assert sample.identity.process_id == os.getpid()
