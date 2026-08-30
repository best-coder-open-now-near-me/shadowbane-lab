from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from client_alignment_fixture import build_pe, write_profile
from shadowbane_lab.client_alignment.compare import compare_client_builds
from shadowbane_lab.client_alignment.profiles import (
    ProfileInventoryError,
    inventory_native_profiles,
)


class ClientAlignmentComparisonTests(unittest.TestCase):
    def test_unchanged_layout_with_unrelated_code_change_is_review_candidate(self) -> None:
        reference = bytearray(build_pe())
        candidate = bytearray(reference)
        candidate[0x200 + 0x10] ^= 0x7F

        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            reference_path = directory / "reference.exe"
            candidate_path = directory / "candidate.exe"
            profile_directory = directory / "profiles"
            profile_directory.mkdir()
            reference_path.write_bytes(reference)
            candidate_path.write_bytes(candidate)
            write_profile(
                profile_directory,
                hashlib.sha256(reference).hexdigest(),
                anchor_rva=0x2050,
            )
            before_reference = reference_path.read_bytes()
            before_candidate = candidate_path.read_bytes()

            report = compare_client_builds(
                reference_path,
                candidate_path,
                profile_directory=profile_directory,
            )

            self.assertEqual("candidate_for_reviewed_compatibility", report.recommendation)
            self.assertTrue(report.pe_header_layout_equal)
            self.assertTrue(report.section_layouts_equal)
            self.assertEqual(1, report.changed_byte_count)
            self.assertEqual(0, len(report.anchor_intersections))
            self.assertEqual((".data",), report.unchanged_sections)
            self.assertEqual((".text",), report.changed_sections)
            self.assertIsNotNone(report.proposed_compatibility_evidence)
            self.assertEqual(before_reference, reference_path.read_bytes())
            self.assertEqual(before_candidate, candidate_path.read_bytes())

    def test_change_inside_signature_is_reported_per_profile_anchor(self) -> None:
        reference = bytearray(build_pe())
        candidate = bytearray(reference)
        candidate[0x200 + 0x25] ^= 0x01

        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            reference_path = directory / "reference.exe"
            candidate_path = directory / "candidate.exe"
            profile_directory = directory / "profiles"
            profile_directory.mkdir()
            reference_path.write_bytes(reference)
            candidate_path.write_bytes(candidate)
            write_profile(
                profile_directory,
                hashlib.sha256(reference).hexdigest(),
                anchor_rva=0x2050,
            )

            report = compare_client_builds(
                reference_path,
                candidate_path,
                profile_directory=profile_directory,
            )

            self.assertEqual("calibrated_anchor_review_required", report.recommendation)
            self.assertEqual(1, len(report.anchor_intersections))
            self.assertEqual(
                "breakpoints[0].rva",
                report.anchor_intersections[0].anchor.field_path,
            )
            self.assertIsNone(report.proposed_compatibility_evidence)

    def test_changed_section_layout_cannot_reuse_rva_mapping(self) -> None:
        reference = build_pe()
        candidate = build_pe(data_virtual_address=0x3000)

        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            reference_path = directory / "reference.exe"
            candidate_path = directory / "candidate.exe"
            profile_directory = directory / "profiles"
            profile_directory.mkdir()
            reference_path.write_bytes(reference)
            candidate_path.write_bytes(candidate)
            write_profile(
                profile_directory,
                hashlib.sha256(reference).hexdigest(),
                anchor_rva=0x2050,
            )

            report = compare_client_builds(
                reference_path,
                candidate_path,
                profile_directory=profile_directory,
            )

            self.assertEqual("structural_review_required", report.recommendation)
            self.assertFalse(report.section_layouts_equal)
            self.assertTrue(
                all(changed_range.rva_start is None for changed_range in report.changed_ranges)
            )

    def test_unknown_reference_without_profiles_is_not_proposed_for_compatibility(self) -> None:
        reference = bytearray(build_pe())
        candidate = bytearray(reference)
        candidate[0x200 + 0x10] ^= 0x01

        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            reference_path = directory / "reference.exe"
            candidate_path = directory / "candidate.exe"
            profile_directory = directory / "profiles"
            profile_directory.mkdir()
            reference_path.write_bytes(reference)
            candidate_path.write_bytes(candidate)

            report = compare_client_builds(
                reference_path,
                candidate_path,
                profile_directory=profile_directory,
            )

            self.assertEqual("no_applicable_profiles", report.recommendation)
            self.assertIsNone(report.proposed_compatibility_evidence)

    def test_reviewed_layout_family_makes_canonical_profile_applicable(self) -> None:
        canonical = "ef43784ba6ffa0de6c0c16c76569f864393ad1530e7149395bb560e5cca30f13"
        compatible = "2b186aef864ea1ce16d8ec959c450f1f2e301d1ba25d9daa3b14ab6c65d68c3d"

        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            write_profile(directory, canonical, anchor_rva=0x2050)

            inventory = inventory_native_profiles(compatible, directory=directory)

            self.assertEqual(1, inventory.applicable_profile_count)
            self.assertEqual(2, len(inventory.anchors))

    def test_profile_inventory_collects_nested_and_named_rvas(self) -> None:
        reference = build_pe()
        digest = hashlib.sha256(reference).hexdigest()

        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            write_profile(directory, digest, anchor_rva=0x2050)

            inventory = inventory_native_profiles(digest, directory=directory)

            self.assertEqual(1, inventory.applicable_profile_count)
            self.assertEqual(
                ["breakpoints[0].rva", "root_pointer_rva"],
                [anchor.field_path for anchor in inventory.anchors],
            )
            self.assertEqual(8, inventory.anchors[0].length)
            self.assertEqual(4, inventory.anchors[1].length)

    def test_duplicate_profile_fields_fail_closed(self) -> None:
        digest = hashlib.sha256(build_pe()).hexdigest()
        profile = (
            '{"profile_id":"one","profile_id":"two",'
            f'"executable_sha256":"{digest}"}}'
        )

        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            (directory / "duplicate.json").write_text(profile, encoding="utf-8")

            with self.assertRaises(ProfileInventoryError):
                inventory_native_profiles(digest, directory=directory)


if __name__ == "__main__":
    unittest.main()
