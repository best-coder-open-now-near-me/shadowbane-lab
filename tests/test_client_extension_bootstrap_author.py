from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from shadowbane_lab.client_extension.bootstrap_author import (
    WONDERBANE_1_0_5_55FB_PROFILE,
    WONDERBANE_1_0_5_PROFILE,
    BootstrapAuthoringError,
    ReviewedBootstrapProfile,
    ReviewedSection,
    author_reviewed_bootstrap_file,
    author_reviewed_bootstrap_manifest,
    resolve_reviewed_bootstrap_profile,
)
from shadowbane_lab.client_extension.resolver import apply_patch_plan, build_patch_plan
from tests.client_alignment_fixture import build_pe


def _reviewed_source() -> bytes:
    result = bytearray(build_pe())
    optional = 0x80 + 24
    section_table = optional + 0xE0
    result[section_table + 40 : section_table + 48] = b".idata\0\0"
    struct.pack_into("<I", result, section_table + 40 + 8, 0x180)
    struct.pack_into("<I", result, optional + 92, 16)
    struct.pack_into("<II", result, optional + 96 + 8, 0x2000, 40)
    struct.pack_into("<II", result, optional + 96 + 12 * 8, 0x2050, 8)
    result[0x200:0x205] = bytes.fromhex("558bec6aff")
    result[0x300:0x400] = b"\0" * 0x100
    struct.pack_into("<IIIII", result, 0x400, 0x2040, 0, 0, 0x2030, 0x2050)
    result[0x430:0x43D] = b"KERNEL32.dll\0"
    struct.pack_into("<I", result, 0x440, 0x2080)
    struct.pack_into("<I", result, 0x450, 0x2080)
    struct.pack_into("<H", result, 0x480, 0)
    result[0x482:0x48F] = b"LoadLibraryA\0"
    return bytes(result)


def _extension(*, include_initializer: bool = True) -> bytes:
    result = bytearray(build_pe())
    optional = 0x80 + 24
    struct.pack_into("<H", result, 0x80 + 4 + 18, 0x2102)
    struct.pack_into("<I", result, optional + 92, 16)
    struct.pack_into("<II", result, optional + 96, 0x2000, 0x100)
    struct.pack_into(
        "<IIHHIIIIIII",
        result,
        0x400,
        0,
        0,
        0,
        0,
        0x2050,
        1,
        1,
        1 if include_initializer else 0,
        0x2040,
        0x2044,
        0x2048,
    )
    struct.pack_into("<I", result, 0x440, 0x1000)
    if include_initializer:
        struct.pack_into("<I", result, 0x444, 0x2070)
    struct.pack_into("<H", result, 0x448, 0)
    result[0x450:0x469] = b"wonderbane-extension.dll\0"
    export_name = b"WonderBaneExtensionInitialize\0"
    result[0x470 : 0x470 + len(export_name)] = export_name
    return bytes(result)


def _profile(source: bytes) -> ReviewedBootstrapProfile:
    return ReviewedBootstrapProfile(
        profile_id="fixture-reviewed-client",
        source_sha256=hashlib.sha256(source).hexdigest(),
        source_length=len(source),
        image_base=0x400000,
        entry_point_rva=0x1000,
        entry_prefix=bytes.fromhex("558bec6aff"),
        text=ReviewedSection(
            index=0,
            name=".text",
            virtual_address=0x1000,
            virtual_size=0x100,
            raw_offset=0x200,
            raw_size=0x200,
            characteristics=0x60000020,
        ),
        idata=ReviewedSection(
            index=1,
            name=".idata",
            virtual_address=0x2000,
            virtual_size=0x180,
            raw_offset=0x400,
            raw_size=0x200,
            characteristics=0xC0000040,
        ),
        import_directory_rva=0x2000,
        import_directory_size=40,
        iat_directory_rva=0x2050,
        iat_directory_size=8,
        kernel32_original_first_thunk=0x2040,
        kernel32_first_thunk=0x2050,
        kernel32_import_count=1,
        load_library_iat_rva=0x2050,
    )


class BootstrapAuthorTests(unittest.TestCase):
    def test_resolves_each_reviewed_wonderbane_source_by_exact_digest(self) -> None:
        self.assertIs(
            WONDERBANE_1_0_5_PROFILE,
            resolve_reviewed_bootstrap_profile(WONDERBANE_1_0_5_PROFILE.source_sha256.upper()),
        )
        self.assertIs(
            WONDERBANE_1_0_5_55FB_PROFILE,
            resolve_reviewed_bootstrap_profile(WONDERBANE_1_0_5_55FB_PROFILE.source_sha256),
        )
        self.assertEqual(WONDERBANE_1_0_5_PROFILE.text, WONDERBANE_1_0_5_55FB_PROFILE.text)
        self.assertEqual(WONDERBANE_1_0_5_PROFILE.idata, WONDERBANE_1_0_5_55FB_PROFILE.idata)

    def test_rejects_unknown_or_malformed_default_profile_digest(self) -> None:
        with self.assertRaisesRegex(BootstrapAuthoringError, "not a reviewed bootstrap build"):
            resolve_reviewed_bootstrap_profile("ab" * 32)
        with self.assertRaisesRegex(BootstrapAuthoringError, "64-character"):
            resolve_reviewed_bootstrap_profile("not-a-digest")

    def test_authors_seven_exact_sites_and_independent_plan(self) -> None:
        source = _reviewed_source()
        result = author_reviewed_bootstrap_manifest(
            source,
            _extension(),
            profile=_profile(source),
        )
        plan = build_patch_plan(source, result.manifest)
        patched = apply_patch_plan(source, plan.writes)

        self.assertEqual(7, len(result.manifest.sites))
        self.assertEqual(0x1100, result.bootstrap_rva)
        self.assertEqual(0x2180, result.get_proc_address_name_rva)
        self.assertEqual(0x2054, result.get_proc_address_iat_rva)
        self.assertEqual(b"\xE9", patched[0x200:0x201])
        self.assertEqual(b"\x9C\xFC\x60\xE8\0\0\0\0\x5B", patched[0x300:0x309])
        self.assertEqual(struct.pack("<I", 0x2180), patched[0x444:0x448])
        self.assertEqual(struct.pack("<I", 0x2180), patched[0x454:0x458])
        self.assertEqual(b"\0\0GetProcAddress\0", patched[0x580:0x591])
        self.assertTrue(build_patch_plan(patched, result.manifest).already_patched)

    def test_rejects_unreviewed_source_and_missing_initializer_export(self) -> None:
        source = _reviewed_source()
        changed = bytearray(source)
        changed[0x250] ^= 1
        with self.assertRaisesRegex(BootstrapAuthoringError, "SHA-256"):
            author_reviewed_bootstrap_manifest(
                bytes(changed),
                _extension(),
                profile=_profile(source),
            )
        with self.assertRaisesRegex(BootstrapAuthoringError, "does not export"):
            author_reviewed_bootstrap_manifest(
                source,
                _extension(include_initializer=False),
                profile=_profile(source),
            )

    def test_file_authoring_is_atomic_create_new(self) -> None:
        source = _reviewed_source()
        profile = _profile(source)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "sb.exe"
            extension_path = root / "wonderbane-extension.dll"
            output_path = root / "evidence" / "manifest.json"
            source_path.write_bytes(source)
            extension_path.write_bytes(_extension())

            result = author_reviewed_bootstrap_file(
                source_path,
                extension_path,
                output_path,
                profile=profile,
            )
            self.assertEqual(
                result.manifest.as_dict(),
                json.loads(output_path.read_text(encoding="utf-8")),
            )
            with self.assertRaisesRegex(BootstrapAuthoringError, "already exists"):
                author_reviewed_bootstrap_file(
                    source_path,
                    extension_path,
                    output_path,
                    profile=profile,
                )


if __name__ == "__main__":
    unittest.main()


def test_current_version_update_uses_reviewed_bootstrap_layout():
    profile = resolve_reviewed_bootstrap_profile(
        "feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff"
    )
    assert profile.profile_id == "wonderbane-1.3.38.6-feb351f0"
    assert profile.text == WONDERBANE_1_0_5_55FB_PROFILE.text
    assert profile.entry_point_rva == WONDERBANE_1_0_5_55FB_PROFILE.entry_point_rva
