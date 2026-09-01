import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.manager.record_store import publish_atomic_record


class ManagerRecordStoreTests(unittest.TestCase):
    def test_record_is_durably_replaced_without_temporary_residue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "nested" / "worker.json"
            publish_atomic_record(target, b"first", temporary_label="worker")
            publish_atomic_record(target, b"second", temporary_label="worker")

            self.assertEqual(b"second", target.read_bytes())
            self.assertEqual([target], list(target.parent.iterdir()))

    def test_transient_reader_lock_is_retried_with_bounded_delays(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "dispatch.permit"
            original_replace = Path.replace
            attempts = 0

            def intermittently_locked(source: Path, destination: Path) -> Path:
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError(13, "record is transiently locked", str(destination))
                return original_replace(source, destination)

            with (
                patch.object(Path, "replace", intermittently_locked),
                patch("shadowbane_lab.manager.record_store.sleep") as retry_sleep,
            ):
                publish_atomic_record(target, b"permit", temporary_label="dispatch")

            self.assertEqual(3, attempts)
            self.assertEqual([0.01, 0.02], [call.args[0] for call in retry_sleep.call_args_list])
            self.assertEqual(b"permit", target.read_bytes())

    def test_non_retryable_failure_preserves_target_and_cleans_temporary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "receipt"
            target.write_bytes(b"previous")

            def fail_replace(_source: Path, _destination: Path) -> None:
                raise OSError(22, "not a transient reader lock")

            with (
                patch.object(Path, "replace", fail_replace),
                patch("shadowbane_lab.manager.record_store.sleep") as retry_sleep,
                self.assertRaisesRegex(OSError, "not a transient reader lock"),
            ):
                publish_atomic_record(target, b"next", temporary_label="receipt")

            retry_sleep.assert_not_called()
            self.assertEqual(b"previous", target.read_bytes())
            self.assertEqual([target], list(target.parent.iterdir()))

    def test_temporary_label_cannot_escape_the_target_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "record"

            with self.assertRaisesRegex(ValueError, "safe record label"):
                publish_atomic_record(target, b"payload", temporary_label="../escape")

            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
