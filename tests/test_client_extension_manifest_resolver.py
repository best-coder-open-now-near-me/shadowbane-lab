from __future__ import annotations

import hashlib
import json
import struct
import unittest

from shadowbane_lab.client_extension.manifest import (
    ExtensionArtifact,
    MaskedSignature,
    PatchManifest,
    PatchManifestError,
    PatchSite,
    SourceExecutable,
    load_patch_manifest_text,
)
from shadowbane_lab.client_extension.resolver import (
    PatchResolutionError,
    PatchSiteStatus,
    align_patch_sites,
    apply_patch_plan,
    build_patch_plan,
)
from tests.client_alignment_fixture import build_pe

_TEXT_RVA = 0x1000
_TEXT_OFFSET = 0x200
_REVIEWED_SITE_RVA = 0x1020
_ORIGINAL = b"\x11\x22"
_REPLACEMENT = b"\x33\x44"
_SIGNATURE = b"\xAA\xBB" + _ORIGINAL + b"\xCC"


def _file_offset(rva: int) -> int:
    return _TEXT_OFFSET + rva - _TEXT_RVA


def _put(target: bytes, rva: int, value: bytes) -> bytes:
    output = bytearray(target)
    offset = _file_offset(rva)
    output[offset : offset + len(value)] = value
    return bytes(output)


def _source() -> bytes:
    return _put(build_pe(), _REVIEWED_SITE_RVA - 2, _SIGNATURE)


def _manifest(
    source: bytes | None = None,
    *,
    patched_sha256: str | None = None,
    section: str = ".text",
) -> PatchManifest:
    source = _source() if source is None else source
    patched = bytearray(source)
    site_offset = _file_offset(_REVIEWED_SITE_RVA)
    patched[site_offset : site_offset + len(_ORIGINAL)] = _REPLACEMENT
    return PatchManifest(
        patch_id="fixture.bootstrap-v1",
        source=SourceExecutable(
            file_name="sb.exe",
            sha256=hashlib.sha256(source).hexdigest(),
            length=len(source),
            machine=0x14C,
            pointer_size=4,
        ),
        patched_executable_sha256=(
            hashlib.sha256(patched).hexdigest()
            if patched_sha256 is None
            else patched_sha256
        ),
        extension=ExtensionArtifact(
            file_name="wonderbane-extension.dll",
            sha256="e" * 64,
            version="1.0.0",
            machine=0x14C,
            bootstrap_export="WonderBaneExtensionInitialize",
        ),
        sites=(
            PatchSite(
                site_id="bootstrap-entry",
                section=section,
                reviewed_rva=_REVIEWED_SITE_RVA,
                expected_original=_ORIGINAL,
                replacement=_REPLACEMENT,
                signature=MaskedSignature(
                    value=b"\xAA\xBB\x00\x00\xCC",
                    mask=b"\xFF\xFF\x00\x00\xFF",
                ),
                signature_site_offset=2,
                search_radius=0x80,
            ),
        ),
    )


class PatchManifestTests(unittest.TestCase):
    def test_strict_manifest_round_trips_canonical_payload(self) -> None:
        manifest = _manifest()

        parsed = load_patch_manifest_text(json.dumps(manifest.as_dict()))

        self.assertEqual(parsed, manifest)
        self.assertEqual(parsed.sites[0].signature.as_text(), "AA BB ?? ?? CC")

    def test_duplicate_unknown_and_nonstandard_json_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(PatchManifestError, "duplicate JSON field"):
            load_patch_manifest_text('{"schema_version":1,"schema_version":1}')

        payload = _manifest().as_dict()
        payload["unexpected"] = True
        with self.assertRaisesRegex(PatchManifestError, "unknown fields"):
            load_patch_manifest_text(json.dumps(payload))

        with self.assertRaisesRegex(PatchManifestError, "non-standard JSON constant"):
            load_patch_manifest_text('{"schema_version":NaN}')

    def test_signature_must_wildcard_the_bytes_replaced_by_the_site(self) -> None:
        with self.assertRaisesRegex(PatchManifestError, "must wildcard"):
            PatchSite(
                site_id="bootstrap-entry",
                section=".text",
                reviewed_rva=_REVIEWED_SITE_RVA,
                expected_original=_ORIGINAL,
                replacement=_REPLACEMENT,
                signature=MaskedSignature(value=_SIGNATURE, mask=b"\xFF" * 5),
                signature_site_offset=2,
                search_radius=0x80,
            )


class PatchResolverTests(unittest.TestCase):
    def test_unrelated_candidate_change_aligns_without_authorizing_candidate(self) -> None:
        source = _source()
        manifest = _manifest(source)
        exact = align_patch_sites(source, manifest)
        candidate = bytearray(source)
        candidate[_file_offset(0x1080)] ^= 0x01
        changed = align_patch_sites(bytes(candidate), manifest)

        self.assertTrue(exact.exact_source_match)
        self.assertEqual(exact.sites[0].status, PatchSiteStatus.EXACT)
        self.assertFalse(changed.exact_source_match)
        self.assertTrue(changed.all_sites_resolved)
        self.assertEqual(changed.sites[0].status, PatchSiteStatus.EXACT)
        with self.assertRaisesRegex(PatchResolutionError, "source SHA-256"):
            build_patch_plan(bytes(candidate), manifest)

    def test_moved_site_resolves_only_when_signature_is_unique(self) -> None:
        source = _source()
        manifest = _manifest(source)
        moved = _put(source, _REVIEWED_SITE_RVA - 2, b"\x90" * len(_SIGNATURE))
        moved = _put(moved, 0x1040 - 2, _SIGNATURE)

        report = align_patch_sites(moved, manifest)

        self.assertEqual(report.sites[0].status, PatchSiteStatus.RELOCATED)
        self.assertEqual(report.sites[0].resolved_rva, 0x1040)

    def test_ambiguous_and_semantically_changed_sites_fail_closed(self) -> None:
        source = _source()
        manifest = _manifest(source)
        blank = _put(source, _REVIEWED_SITE_RVA - 2, b"\x90" * len(_SIGNATURE))
        ambiguous = _put(blank, 0x1040 - 2, _SIGNATURE)
        ambiguous = _put(ambiguous, 0x1060 - 2, _SIGNATURE)

        ambiguous_report = align_patch_sites(ambiguous, manifest)
        missing_report = align_patch_sites(blank, manifest)

        self.assertEqual(ambiguous_report.sites[0].status, PatchSiteStatus.AMBIGUOUS)
        self.assertEqual(ambiguous_report.sites[0].candidate_rvas, (0x1040, 0x1060))
        self.assertEqual(missing_report.sites[0].status, PatchSiteStatus.MISSING)

    def test_section_and_architecture_changes_are_explicit(self) -> None:
        source = _source()
        missing_section = align_patch_sites(source, _manifest(source, section=".rdata"))
        wrong_machine = bytearray(source)
        struct.pack_into("<H", wrong_machine, 0x84, 0x8664)
        architecture = align_patch_sites(bytes(wrong_machine), _manifest(source))

        self.assertEqual(
            missing_section.sites[0].status,
            PatchSiteStatus.SECTION_MISSING,
        )
        self.assertFalse(architecture.architecture_matches)
        self.assertEqual(
            architecture.sites[0].status,
            PatchSiteStatus.ARCHITECTURE_MISMATCH,
        )

    def test_exact_plan_applies_and_recognizes_verified_patched_output(self) -> None:
        source = _source()
        manifest = _manifest(source)

        plan = build_patch_plan(source, manifest)
        patched = apply_patch_plan(source, plan.writes)
        second_plan = build_patch_plan(patched, manifest)

        self.assertFalse(plan.already_patched)
        self.assertEqual(plan.writes[0].rva, _REVIEWED_SITE_RVA)
        self.assertEqual(hashlib.sha256(patched).hexdigest(), manifest.patched_executable_sha256)
        self.assertTrue(second_plan.already_patched)
        self.assertEqual(second_plan.writes, ())

    def test_incorrect_predicted_output_hash_rejects_plan(self) -> None:
        source = _source()
        manifest = _manifest(source, patched_sha256="f" * 64)

        with self.assertRaisesRegex(PatchResolutionError, "predicted patched"):
            build_patch_plan(source, manifest)


if __name__ == "__main__":
    unittest.main()
