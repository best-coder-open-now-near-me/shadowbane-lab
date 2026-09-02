from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from shadowbane_vanilla_diagnostics.discovery import WindowsProcessDiscovery


@unittest.skipUnless(os.name == "nt", "Windows process discovery test")
class WindowsProcessDiscoveryTests(unittest.TestCase):
    def test_current_process_is_discovered_by_exact_executable_name(self) -> None:
        identities = WindowsProcessDiscovery().find(Path(sys.executable).name)

        self.assertTrue(any(identity.process_id == os.getpid() for identity in identities))


if __name__ == "__main__":
    unittest.main()
