from __future__ import annotations

import os
import unittest

from shadowbane_lab.diagnostics.process import WindowsProcessProbe


class WindowsProcessProbeTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows process handles are required")
    def test_windows_process_probe_can_wait_on_its_open_handle(self) -> None:
        sample = WindowsProcessProbe().sample(os.getpid())

        self.assertEqual(os.getpid(), sample.identity.process_id)
