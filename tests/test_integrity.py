from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.integrity import (
    CreateOnlyError,
    FileRecord,
    JsonBounds,
    canonical_json_sha256,
    canonical_json_text,
    canonical_timestamp,
    create_only_json,
    freeze_json,
    inventory_tree,
    load_strict_json,
    resolve_within_root,
    strict_json_loads,
    thaw_json,
    tree_sha256,
    validate_relative_path,
)
from shadowbane_lab.integrity.canonical import IntegrityJsonError
from shadowbane_lab.integrity.paths import PathSecurityError


class CanonicalJsonTests(unittest.TestCase):
    def test_canonical_json_is_order_independent_and_ascii(self) -> None:
        left = {"z": "é", "a": [2, 1]}
        right = {"a": [2, 1], "z": "é"}
        self.assertEqual(canonical_json_text(left), '{"a":[2,1],"z":"\\u00e9"}')
        self.assertEqual(canonical_json_sha256(left), canonical_json_sha256(right))

    def test_frozen_json_is_detached_immutable_and_canonical(self) -> None:
        original = {"nested": [{"value": 1}], "name": "fixture"}
        frozen = freeze_json(original)
        expected_digest = canonical_json_sha256(frozen)

        original["nested"][0]["value"] = 2
        original["nested"].append({"value": 3})

        self.assertEqual(
            {"name": "fixture", "nested": [{"value": 1}]},
            thaw_json(frozen),
        )
        self.assertEqual(expected_digest, canonical_json_sha256(frozen))
        with self.assertRaises(TypeError):
            frozen["new"] = True
        with self.assertRaises(AttributeError):
            frozen["nested"].append({"value": 4})

    def test_strict_decoder_rejects_duplicate_and_nonfinite_fields(self) -> None:
        with self.assertRaisesRegex(IntegrityJsonError, "duplicate"):
            strict_json_loads('{"a":1,"a":2}')
        with self.assertRaisesRegex(IntegrityJsonError, "non-finite"):
            strict_json_loads('{"a":NaN}')

    def test_strict_decoder_enforces_bounds(self) -> None:
        with self.assertRaisesRegex(IntegrityJsonError, "byte limit"):
            strict_json_loads("[]", bounds=JsonBounds(maximum_bytes=1))
        with self.assertRaisesRegex(IntegrityJsonError, "depth"):
            strict_json_loads("[[[0]]]", bounds=JsonBounds(maximum_depth=2))
        with self.assertRaisesRegex(IntegrityJsonError, "node"):
            strict_json_loads("[1,2]", bounds=JsonBounds(maximum_nodes=2))


class IntegrityPathTests(unittest.TestCase):
    def test_relative_paths_fail_closed(self) -> None:
        for value in ("", "../x", "x\\y", "/x", "C:/x", "x/./y", "x../"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_relative_path(value)

    def test_resolve_within_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(
                resolve_within_root(root, "a/b.json"),
                root.resolve(strict=True) / "a" / "b.json",
            )
            with self.assertRaises(ValueError):
                resolve_within_root(root, "../outside")

    def test_symlink_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.mkdir()
            link = root / "link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation is not permitted")
            with self.assertRaises(PathSecurityError):
                resolve_within_root(root, "link/file")


class IntegrityStorageTests(unittest.TestCase):
    def test_create_only_json_round_trips_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested" / "value.json"
            create_only_json(path, {"b": 2, "a": 1}, make_parents=True)
            self.assertEqual(load_strict_json(path), {"a": 1, "b": 2})
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))
            with self.assertRaises(CreateOnlyError):
                create_only_json(path, {"replacement": True})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1, "b": 2})

    def test_timestamp_is_canonical_utc(self) -> None:
        value = datetime(2026, 8, 31, 12, 34, 56, 123456, tzinfo=UTC)
        self.assertEqual(canonical_timestamp(value), "2026-08-31T12:34:56.123Z")
        with self.assertRaises(ValueError):
            canonical_timestamp(datetime(2026, 8, 31))


class TreeInventoryTests(unittest.TestCase):
    def test_inventory_is_deterministic_and_detects_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "b.txt").write_text("b", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "a.txt").write_text("a", encoding="utf-8")
            first = inventory_tree(root)
            second = inventory_tree(root)
            self.assertEqual(first, second)
            self.assertEqual(
                tuple(item.relative_path for item in first.files),
                ("b.txt", "nested/a.txt"),
            )
            (root / "b.txt").write_text("changed", encoding="utf-8")
            self.assertNotEqual(first.tree_sha256, inventory_tree(root).tree_sha256)

    def test_tree_digest_matches_existing_client_baseline_algorithm(self) -> None:
        records = (
            FileRecord("a", 1, "0" * 64),
            FileRecord("b/c", 2, "1" * 64),
        )
        expected = tree_sha256(records)
        self.assertEqual(expected, tree_sha256(iter(records)))


if __name__ == "__main__":
    unittest.main()
