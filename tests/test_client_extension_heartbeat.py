from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.client_extension.heartbeat import (
    ExtensionHeartbeat,
    ExtensionHeartbeatError,
    load_extension_heartbeat,
    parse_extension_heartbeat,
)


def _heartbeat() -> ExtensionHeartbeat:
    return ExtensionHeartbeat(
        extension_version="1.0.0",
        process_id=4900,
        process_creation_filetime_utc=134325668008358961,
        initialized_at_filetime_utc=134325668009023349,
    )


class ExtensionHeartbeatTests(unittest.TestCase):
    def test_native_shape_round_trips_and_binds_file_name_to_process_lifetime(self) -> None:
        heartbeat = _heartbeat()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / heartbeat.expected_file_name
            path.write_text(json.dumps(heartbeat.as_dict()), encoding="utf-8")

            loaded = load_extension_heartbeat(path)

        self.assertEqual(heartbeat, loaded)
        self.assertEqual((4900, 134325668008358961), loaded.process_identity)

    def test_unknown_duplicate_and_noncanonical_values_fail_closed(self) -> None:
        payload = _heartbeat().as_dict()
        payload["extra"] = True
        with self.assertRaisesRegex(ExtensionHeartbeatError, "unknown fields"):
            parse_extension_heartbeat(payload)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / _heartbeat().expected_file_name
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaisesRegex(ExtensionHeartbeatError, "duplicate"):
                load_extension_heartbeat(path)

        with self.assertRaisesRegex(ExtensionHeartbeatError, "predates"):
            ExtensionHeartbeat(
                extension_version="1.0.0",
                process_id=1,
                process_creation_filetime_utc=100,
                initialized_at_filetime_utc=99,
            )

    def test_file_name_identity_mismatch_is_rejected(self) -> None:
        heartbeat = _heartbeat()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "heartbeat-4901-134325668008358961.json"
            path.write_text(json.dumps(heartbeat.as_dict()), encoding="utf-8")

            with self.assertRaisesRegex(ExtensionHeartbeatError, "differs"):
                load_extension_heartbeat(path)


if __name__ == "__main__":
    unittest.main()
