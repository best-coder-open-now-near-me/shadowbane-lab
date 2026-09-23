from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.client_extension.heartbeat import ExtensionHeartbeat
from shadowbane_lab.client_extension.runtime_status import (
    ExtensionHeartbeatStatusProvider,
    ExtensionRuntimeState,
)


class ExtensionRuntimeStatusTests(unittest.TestCase):
    def test_exact_process_heartbeat_is_initialized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            heartbeat = ExtensionHeartbeat(
                extension_version="1.0.0",
                process_id=42,
                process_creation_filetime_utc=1000,
                initialized_at_filetime_utc=1010,
            )
            (root / heartbeat.expected_file_name).write_text(
                json.dumps(heartbeat.as_dict()),
                encoding="utf-8",
            )

            status = ExtensionHeartbeatStatusProvider(root).inspect(42, 1000)

            self.assertEqual(ExtensionRuntimeState.INITIALIZED, status.state)
            self.assertTrue(status.ready)
            self.assertEqual("1.0.0", status.extension_version)
            self.assertEqual(1, status.abi_version)
            self.assertEqual(heartbeat.expected_file_name, status.heartbeat_file_name)

    def test_unbound_missing_and_other_lifetimes_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = ExtensionHeartbeat(
                extension_version="1.0.0",
                process_id=41,
                process_creation_filetime_utc=900,
                initialized_at_filetime_utc=910,
            )
            (root / old.expected_file_name).write_text(
                json.dumps(old.as_dict()),
                encoding="utf-8",
            )
            provider = ExtensionHeartbeatStatusProvider(root)

            self.assertEqual(ExtensionRuntimeState.UNBOUND, provider.inspect(None, None).state)
            self.assertEqual(ExtensionRuntimeState.MISSING, provider.inspect(42, 1000).state)

    def test_malformed_exact_heartbeat_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "heartbeat-42-1000.json").write_text("{}", encoding="utf-8")

            status = ExtensionHeartbeatStatusProvider(root).inspect(42, 1000)

            self.assertEqual(ExtensionRuntimeState.INVALID, status.state)
            self.assertFalse(status.ready)
            self.assertIn("invalid", status.detail or "")


if __name__ == "__main__":
    unittest.main()
