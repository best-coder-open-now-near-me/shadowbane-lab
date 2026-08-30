"""Author the reviewed minimal loader manifest for the exact WonderBane client."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shadowbane_lab.client_alignment.model import PeImage, PeSection
from shadowbane_lab.client_alignment.pe import PeInspectionError, inspect_pe_bytes
from shadowbane_lab.client_extension.manifest import (
    ExtensionArtifact,
    MaskedSignature,
    PatchManifest,
    PatchSite,
    SourceExecutable,
)
from shadowbane_lab.client_extension.resolver import (
    PE_HEADERS_SECTION,
    apply_patch_plan,
    build_patch_plan,
)

_IMAGE_DIRECTORY_ENTRY_EXPORT = 0
_IMAGE_DIRECTORY_ENTRY_IMPORT = 1
_IMAGE_DIRECTORY_ENTRY_IAT = 12
_IMAGE_FILE_DLL = 0x2000
_MAX_IMPORT_DESCRIPTORS = 128
_MAX_IMPORT_THUNKS = 4096
_MAX_EXPORT_NAMES = 4096
_MAX_ASCII_BYTES = 256
_CONTEXT_BYTES = 16
_BOOTSTRAP_EXPORT = "WonderBaneExtensionInitialize"
_EXTENSION_FILE_NAME = "wonderbane-extension.dll"


class BootstrapAuthoringError(ValueError):
    """Raised when an input differs from the manually reviewed bootstrap profile."""


@dataclass(frozen=True, slots=True)
class ReviewedSection:
    """Exact section layout required by one manually reviewed client profile."""

    index: int
    name: str
    virtual_address: int
    virtual_size: int
    raw_offset: int
    raw_size: int
    characteristics: int


@dataclass(frozen=True, slots=True)
class ReviewedBootstrapProfile:
    """Hash and structural facts that authorize manifest authoring for one client."""

    profile_id: str
    source_sha256: str
    source_length: int
    image_base: int
    entry_point_rva: int
    entry_prefix: bytes
    text: ReviewedSection
    idata: ReviewedSection
    import_directory_rva: int
    import_directory_size: int
    iat_directory_rva: int
    iat_directory_size: int
    kernel32_original_first_thunk: int
    kernel32_first_thunk: int
    kernel32_import_count: int
    load_library_iat_rva: int


WONDERBANE_1_0_5_PROFILE = ReviewedBootstrapProfile(
    profile_id="wonderbane-1.0.5-e358237c",
    source_sha256="e358237c458ddfe2fc7a86e478f165a8fd067655ab1a8ada5731f790c6995d96",
    source_length=21_143_613,
    image_base=0x00400000,
    entry_point_rva=9_276_490,
    entry_prefix=bytes.fromhex("558bec6aff"),
    text=ReviewedSection(
        index=0,
        name=".text",
        virtual_address=4_096,
        virtual_size=18_087_536,
        raw_offset=4_096,
        raw_size=18_087_936,
        characteristics=0x60000020,
    ),
    idata=ReviewedSection(
        index=3,
        name=".idata",
        virtual_address=23_785_472,
        virtual_size=25_263,
        raw_offset=20_393_984,
        raw_size=28_672,
        characteristics=0xC0000040,
    ),
    import_directory_rva=23_785_472,
    import_directory_size=360,
    iat_directory_rva=23_789_448,
    iat_directory_size=3_616,
    kernel32_original_first_thunk=23_786_524,
    kernel32_first_thunk=23_790_140,
    kernel32_import_count=57,
    load_library_iat_rva=23_790_276,
)


@dataclass(frozen=True, slots=True)
class BootstrapAuthoringResult:
    """Reviewed manifest plus the small set of generated native locations."""

    profile_id: str
    manifest: PatchManifest
    bootstrap_rva: int
    bootstrap_length: int
    get_proc_address_name_rva: int
    get_proc_address_iat_rva: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "patch_id": self.manifest.patch_id,
            "source_sha256": self.manifest.source.sha256,
            "patched_executable_sha256": self.manifest.patched_executable_sha256,
            "extension_sha256": self.manifest.extension.sha256,
            "bootstrap_rva": self.bootstrap_rva,
            "bootstrap_length": self.bootstrap_length,
            "get_proc_address_name_rva": self.get_proc_address_name_rva,
            "get_proc_address_iat_rva": self.get_proc_address_iat_rva,
            "site_count": len(self.manifest.sites),
        }


@dataclass(frozen=True, slots=True)
class _PeHeaders:
    optional_offset: int
    section_table_offset: int
    import_directory_rva: int
    import_directory_size: int
    iat_directory_rva: int
    iat_directory_size: int


@dataclass(frozen=True, slots=True)
class _Kernel32Review:
    original_first_thunk: int
    first_thunk: int
    import_count: int
    load_library_iat_rva: int


def author_reviewed_bootstrap_manifest(
    source: bytes,
    extension: bytes,
    *,
    source_file_name: str = "sb.exe",
    extension_file_name: str = _EXTENSION_FILE_NAME,
    extension_version: str = "1.0.0",
    profile: ReviewedBootstrapProfile = WONDERBANE_1_0_5_PROFILE,
) -> BootstrapAuthoringResult:
    """Create a deterministic manifest only after every profile fact is reverified."""

    try:
        image = inspect_pe_bytes(source, path=source_file_name)
    except PeInspectionError as exc:
        raise BootstrapAuthoringError(f"source is not a supported PE image: {exc}") from exc
    _require_source_profile(source, image, profile)
    headers = _parse_headers(source, image)
    _require_header_profile(source, headers, profile)
    text = _require_section(image, profile.text)
    idata = _require_section(image, profile.idata)
    kernel32 = _review_kernel32_imports(source, image, headers)
    _require_kernel32_profile(kernel32, profile)
    extension_artifact = _review_extension(
        extension,
        file_name=extension_file_name,
        version=extension_version,
    )

    get_proc_name = b"\0\0GetProcAddress\0"
    get_proc_name_rva = _align_up(idata.virtual_address + idata.virtual_size, 2)
    new_idata_virtual_size = (
        get_proc_name_rva - idata.virtual_address + len(get_proc_name)
    )
    _require_zero_tail(
        source,
        idata,
        start_rva=idata.virtual_address + idata.virtual_size,
        end_rva=idata.virtual_address + new_idata_virtual_size,
        label=".idata GetProcAddress record",
    )

    get_proc_ilt_rva = kernel32.original_first_thunk + kernel32.import_count * 4
    get_proc_iat_rva = kernel32.first_thunk + kernel32.import_count * 4
    get_proc_thunk = struct.pack("<I", get_proc_name_rva)
    for label, rva in (
        ("KERNEL32 lookup-table terminator", get_proc_ilt_rva),
        ("KERNEL32 address-table terminator", get_proc_iat_rva),
    ):
        if _read_rva(source, image, rva, 8, label) != b"\0" * 8:
            raise BootstrapAuthoringError(f"{label} is not followed by a reserved zero slot")
    if not (
        headers.iat_directory_rva
        <= get_proc_iat_rva
        <= headers.iat_directory_rva + headers.iat_directory_size - 4
    ):
        raise BootstrapAuthoringError("new GetProcAddress IAT slot leaves the reviewed IAT range")

    bootstrap_rva = text.virtual_address + text.virtual_size
    stub = _build_x86_loader_stub(
        stub_rva=bootstrap_rva,
        entry_return_rva=image.entry_point_rva + len(profile.entry_prefix),
        load_library_iat_rva=kernel32.load_library_iat_rva,
        get_proc_address_iat_rva=get_proc_iat_rva,
        extension_file_name=extension_artifact.file_name,
        bootstrap_export=extension_artifact.bootstrap_export,
    )
    new_text_virtual_size = text.virtual_size + len(stub)
    _require_zero_tail(
        source,
        text,
        start_rva=bootstrap_rva,
        end_rva=text.virtual_address + new_text_virtual_size,
        label=".text bootstrap stub",
    )
    entry_jump = b"\xE9" + _pack_i32(bootstrap_rva - (image.entry_point_rva + 5))

    text_virtual_size_rva = headers.section_table_offset + text.index * 40 + 8
    idata_virtual_size_rva = headers.section_table_offset + idata.index * 40 + 8
    replacements = (
        ("entry-trampoline", text.name, image.entry_point_rva, entry_jump),
        (
            "headers-idata-virtual-size",
            PE_HEADERS_SECTION,
            idata_virtual_size_rva,
            struct.pack("<I", new_idata_virtual_size),
        ),
        (
            "headers-text-virtual-size",
            PE_HEADERS_SECTION,
            text_virtual_size_rva,
            struct.pack("<I", new_text_virtual_size),
        ),
        ("idata-getprocaddress-hint-name", idata.name, get_proc_name_rva, get_proc_name),
        ("idata-kernel32-iat-terminator", idata.name, get_proc_iat_rva, get_proc_thunk),
        ("idata-kernel32-ilt-terminator", idata.name, get_proc_ilt_rva, get_proc_thunk),
        ("text-bootstrap-stub", text.name, bootstrap_rva, stub),
    )
    sites = tuple(
        sorted(
            (
                _make_site(source, image, site_id, section, rva, replacement)
                for site_id, section, rva, replacement in replacements
            ),
            key=lambda site: site.site_id,
        )
    )
    patched = _apply_authored_sites(source, image, sites)
    manifest = PatchManifest(
        patch_id=f"{profile.profile_id}.bootstrap-v1",
        source=SourceExecutable(
            file_name=source_file_name,
            sha256=image.sha256,
            length=image.length,
            machine=image.machine,
            pointer_size=image.pointer_size,
        ),
        patched_executable_sha256=hashlib.sha256(patched).hexdigest(),
        extension=extension_artifact,
        sites=sites,
    )
    plan = build_patch_plan(source, manifest)
    if apply_patch_plan(source, plan.writes) != patched:
        raise BootstrapAuthoringError("independent patch planning changed the authored output")
    return BootstrapAuthoringResult(
        profile_id=profile.profile_id,
        manifest=manifest,
        bootstrap_rva=bootstrap_rva,
        bootstrap_length=len(stub),
        get_proc_address_name_rva=get_proc_name_rva,
        get_proc_address_iat_rva=get_proc_iat_rva,
    )


def author_reviewed_bootstrap_file(
    source_path: str | Path,
    extension_path: str | Path,
    output_path: str | Path,
    *,
    extension_version: str = "1.0.0",
    profile: ReviewedBootstrapProfile = WONDERBANE_1_0_5_PROFILE,
) -> BootstrapAuthoringResult:
    """Read reviewed inputs and atomically create a new manifest file."""

    source_file = Path(source_path)
    extension_file = Path(extension_path)
    output_file = Path(output_path)
    try:
        source = source_file.read_bytes()
        extension = extension_file.read_bytes()
    except OSError as exc:
        raise BootstrapAuthoringError("could not read bootstrap authoring input") from exc
    result = author_reviewed_bootstrap_manifest(
        source,
        extension,
        source_file_name=source_file.name,
        extension_file_name=extension_file.name,
        extension_version=extension_version,
        profile=profile,
    )
    _write_new_json(output_file, result.manifest.as_dict())
    return result


def _require_source_profile(
    source: bytes,
    image: PeImage,
    profile: ReviewedBootstrapProfile,
) -> None:
    if hashlib.sha256(source).hexdigest() != profile.source_sha256:
        raise BootstrapAuthoringError("source SHA-256 is not the reviewed WonderBane build")
    if len(source) != profile.source_length:
        raise BootstrapAuthoringError("source length is not the reviewed WonderBane build")
    if image.machine != 0x14C or image.pointer_size != 4:
        raise BootstrapAuthoringError("reviewed bootstrap requires a PE32 x86 executable")
    if image.image_base != profile.image_base:
        raise BootstrapAuthoringError("source image base differs from the reviewed profile")
    if image.entry_point_rva != profile.entry_point_rva:
        raise BootstrapAuthoringError("source entry point differs from the reviewed profile")
    entry = _read_rva(
        source,
        image,
        image.entry_point_rva,
        len(profile.entry_prefix),
        "entry prefix",
    )
    if entry != profile.entry_prefix:
        raise BootstrapAuthoringError("source entry prefix differs from the reviewed instructions")


def _parse_headers(source: bytes, image: PeImage) -> _PeHeaders:
    pe_offset = _u32(source, 0x3C, "PE header pointer")
    coff_offset = pe_offset + 4
    optional_size = _u16(source, coff_offset + 16, "optional-header size")
    optional_offset = coff_offset + 20
    if image.optional_header_magic != 0x10B or optional_size < 0xE0:
        raise BootstrapAuthoringError("reviewed bootstrap requires a complete PE32 header")
    directory_count = _u32(source, optional_offset + 92, "data-directory count")
    if directory_count <= _IMAGE_DIRECTORY_ENTRY_IAT:
        raise BootstrapAuthoringError("source does not declare the reviewed data directories")
    if _u32(source, optional_offset + 64, "PE checksum") != 0:
        raise BootstrapAuthoringError("reviewed source checksum field is no longer zero")
    if _u16(source, optional_offset + 70, "DLL characteristics") != 0:
        raise BootstrapAuthoringError("source DLL characteristics differ from the reviewed build")
    directory_offset = optional_offset + 96
    import_rva, import_size = _unpack(
        "<II",
        source,
        directory_offset + _IMAGE_DIRECTORY_ENTRY_IMPORT * 8,
        "import directory",
    )
    iat_rva, iat_size = _unpack(
        "<II",
        source,
        directory_offset + _IMAGE_DIRECTORY_ENTRY_IAT * 8,
        "IAT directory",
    )
    return _PeHeaders(
        optional_offset=optional_offset,
        section_table_offset=optional_offset + optional_size,
        import_directory_rva=import_rva,
        import_directory_size=import_size,
        iat_directory_rva=iat_rva,
        iat_directory_size=iat_size,
    )


def _require_header_profile(
    source: bytes,
    headers: _PeHeaders,
    profile: ReviewedBootstrapProfile,
) -> None:
    if (
        headers.import_directory_rva,
        headers.import_directory_size,
        headers.iat_directory_rva,
        headers.iat_directory_size,
    ) != (
        profile.import_directory_rva,
        profile.import_directory_size,
        profile.iat_directory_rva,
        profile.iat_directory_size,
    ):
        raise BootstrapAuthoringError("source import directories differ from the reviewed profile")
    if headers.section_table_offset >= len(source):
        raise BootstrapAuthoringError("source section table is outside the file")


def _require_section(image: PeImage, reviewed: ReviewedSection) -> PeSection:
    matches = tuple(section for section in image.sections if section.name == reviewed.name)
    if len(matches) != 1:
        raise BootstrapAuthoringError(
            f"source does not contain exactly one {reviewed.name} section"
        )
    section = matches[0]
    actual = (
        section.index,
        section.name,
        section.virtual_address,
        section.virtual_size,
        section.raw_offset,
        section.raw_size,
        section.characteristics,
    )
    expected = (
        reviewed.index,
        reviewed.name,
        reviewed.virtual_address,
        reviewed.virtual_size,
        reviewed.raw_offset,
        reviewed.raw_size,
        reviewed.characteristics,
    )
    if actual != expected:
        raise BootstrapAuthoringError(f"{reviewed.name} layout differs from the reviewed profile")
    return section


def _review_kernel32_imports(
    source: bytes,
    image: PeImage,
    headers: _PeHeaders,
) -> _Kernel32Review:
    directory_offset = _rva_to_offset(
        image,
        headers.import_directory_rva,
        headers.import_directory_size,
        "import descriptor table",
    )
    descriptor_limit = min(
        _MAX_IMPORT_DESCRIPTORS,
        headers.import_directory_size // 20,
    )
    descriptors: list[tuple[int, int, str]] = []
    terminated = False
    for index in range(descriptor_limit):
        values = _unpack(
            "<IIIII",
            source,
            directory_offset + index * 20,
            "import descriptor",
        )
        original_first_thunk, timestamp, forwarder, name_rva, first_thunk = values
        if not any(values):
            terminated = True
            break
        if timestamp or forwarder or not name_rva or not first_thunk:
            raise BootstrapAuthoringError("source import descriptor shape changed")
        library = _read_ascii_rva(source, image, name_rva, "import library")
        descriptors.append((original_first_thunk, first_thunk, library))
    if not terminated:
        raise BootstrapAuthoringError("source import descriptor table is not bounded")
    kernel32 = tuple(item for item in descriptors if item[2].casefold() == "kernel32.dll")
    if len(kernel32) != 1:
        raise BootstrapAuthoringError("source does not contain exactly one KERNEL32 descriptor")
    original_first_thunk, first_thunk, _ = kernel32[0]
    if not original_first_thunk:
        raise BootstrapAuthoringError("KERNEL32 descriptor has no independent lookup table")

    names: list[str] = []
    for index in range(_MAX_IMPORT_THUNKS):
        lookup = _read_u32_rva(
            source,
            image,
            original_first_thunk + index * 4,
            "KERNEL32 lookup thunk",
        )
        address = _read_u32_rva(
            source,
            image,
            first_thunk + index * 4,
            "KERNEL32 address thunk",
        )
        if lookup != address:
            raise BootstrapAuthoringError("KERNEL32 lookup and address tables differ on disk")
        if lookup == 0:
            break
        if lookup & 0x80000000:
            names.append(f"#{lookup & 0xFFFF}")
        else:
            names.append(_read_ascii_rva(source, image, lookup + 2, "KERNEL32 symbol"))
    else:
        raise BootstrapAuthoringError("KERNEL32 thunk table exceeds its safety bound")
    if "GetProcAddress" in names:
        raise BootstrapAuthoringError("source already imports GetProcAddress")
    load_indices = tuple(index for index, name in enumerate(names) if name == "LoadLibraryA")
    if len(load_indices) != 1:
        raise BootstrapAuthoringError("source does not import exactly one LoadLibraryA")
    return _Kernel32Review(
        original_first_thunk=original_first_thunk,
        first_thunk=first_thunk,
        import_count=len(names),
        load_library_iat_rva=first_thunk + load_indices[0] * 4,
    )


def _require_kernel32_profile(
    review: _Kernel32Review,
    profile: ReviewedBootstrapProfile,
) -> None:
    if review != _Kernel32Review(
        original_first_thunk=profile.kernel32_original_first_thunk,
        first_thunk=profile.kernel32_first_thunk,
        import_count=profile.kernel32_import_count,
        load_library_iat_rva=profile.load_library_iat_rva,
    ):
        raise BootstrapAuthoringError("KERNEL32 imports differ from the reviewed profile")


def _review_extension(data: bytes, *, file_name: str, version: str) -> ExtensionArtifact:
    try:
        image = inspect_pe_bytes(data, path=file_name)
    except PeInspectionError as exc:
        raise BootstrapAuthoringError(f"extension is not a supported PE image: {exc}") from exc
    if image.machine != 0x14C or image.pointer_size != 4:
        raise BootstrapAuthoringError("extension must be PE32 x86")
    if not image.characteristics & _IMAGE_FILE_DLL:
        raise BootstrapAuthoringError("extension is not marked as a PE DLL")
    exports = _export_names(data, image)
    if _BOOTSTRAP_EXPORT not in exports:
        raise BootstrapAuthoringError(f"extension does not export {_BOOTSTRAP_EXPORT}")
    return ExtensionArtifact(
        file_name=file_name,
        sha256=hashlib.sha256(data).hexdigest(),
        version=version,
        machine=image.machine,
        bootstrap_export=_BOOTSTRAP_EXPORT,
    )


def _export_names(data: bytes, image: PeImage) -> tuple[str, ...]:
    headers = _parse_data_directory_header(data, image)
    export_rva, export_size = _unpack(
        "<II",
        data,
        headers + _IMAGE_DIRECTORY_ENTRY_EXPORT * 8,
        "export directory entry",
    )
    if not export_rva or export_size < 40:
        return ()
    export_offset = _rva_to_offset(image, export_rva, 40, "export directory")
    number_of_names = _u32(data, export_offset + 24, "export name count")
    address_of_names = _u32(data, export_offset + 32, "export name table")
    if number_of_names > _MAX_EXPORT_NAMES:
        raise BootstrapAuthoringError("extension export-name count exceeds its safety bound")
    table_offset = _rva_to_offset(
        image,
        address_of_names,
        number_of_names * 4,
        "export name table",
    )
    names = tuple(
        _read_ascii_rva(
            data,
            image,
            _u32(data, table_offset + index * 4, "export name RVA"),
            "export name",
        )
        for index in range(number_of_names)
    )
    if len(set(names)) != len(names):
        raise BootstrapAuthoringError("extension contains duplicate export names")
    return names


def _parse_data_directory_header(data: bytes, image: PeImage) -> int:
    pe_offset = _u32(data, 0x3C, "PE header pointer")
    optional_offset = pe_offset + 24
    number_offset = optional_offset + (92 if image.pointer_size == 4 else 108)
    directory_offset = optional_offset + (96 if image.pointer_size == 4 else 112)
    if _u32(data, number_offset, "data-directory count") <= _IMAGE_DIRECTORY_ENTRY_EXPORT:
        raise BootstrapAuthoringError("extension has no export data directory")
    return directory_offset


def _build_x86_loader_stub(
    *,
    stub_rva: int,
    entry_return_rva: int,
    load_library_iat_rva: int,
    get_proc_address_iat_rva: int,
    extension_file_name: str,
    bootstrap_export: str,
) -> bytes:
    try:
        dll_name = extension_file_name.encode("ascii") + b"\0"
        export_name = bootstrap_export.encode("ascii") + b"\0"
    except UnicodeEncodeError as exc:
        raise BootstrapAuthoringError("loader names must be ASCII") from exc
    code = bytearray(b"\x9C\xFC\x60\xE8\0\0\0\0\x5B")
    anchor_rva = stub_rva + 8

    code.extend(b"\x8D\x83")
    dll_displacement_offset = len(code)
    code.extend(b"\0" * 4)
    code.extend(b"\x50\xFF\x93")
    code.extend(_pack_i32(load_library_iat_rva - anchor_rva))
    code.extend(b"\x85\xC0\x74\0")
    first_skip_offset = len(code) - 1
    code.extend(b"\x8D\x8B")
    export_displacement_offset = len(code)
    code.extend(b"\0" * 4)
    code.extend(b"\x51\x50\xFF\x93")
    code.extend(_pack_i32(get_proc_address_iat_rva - anchor_rva))
    code.extend(b"\x85\xC0\x74\0")
    second_skip_offset = len(code) - 1
    code.extend(b"\xFF\xD0")
    restore_offset = len(code)
    code.extend(b"\x61\x9D\x55\x8B\xEC\x6A\xFF\xE9")
    jump_displacement_offset = len(code)
    code.extend(b"\0" * 4)
    dll_offset = len(code)
    code.extend(dll_name)
    export_offset = len(code)
    code.extend(export_name)

    struct.pack_into("<i", code, dll_displacement_offset, stub_rva + dll_offset - anchor_rva)
    struct.pack_into(
        "<i",
        code,
        export_displacement_offset,
        stub_rva + export_offset - anchor_rva,
    )
    _pack_rel8(code, first_skip_offset, restore_offset)
    _pack_rel8(code, second_skip_offset, restore_offset)
    jump_next_rva = stub_rva + jump_displacement_offset + 4
    struct.pack_into("<i", code, jump_displacement_offset, entry_return_rva - jump_next_rva)
    return bytes(code)


def _pack_rel8(code: bytearray, displacement_offset: int, target_offset: int) -> None:
    displacement = target_offset - (displacement_offset + 1)
    if not -128 <= displacement <= 127:
        raise BootstrapAuthoringError("loader conditional branch exceeds rel8 range")
    struct.pack_into("<b", code, displacement_offset, displacement)


def _make_site(
    source: bytes,
    image: PeImage,
    site_id: str,
    section_name: str,
    rva: int,
    replacement: bytes,
) -> PatchSite:
    region_start, region_end = _region_bounds(image, section_name)
    site_offset = _region_rva_to_offset(image, section_name, rva, len(replacement))
    expected = source[site_offset : site_offset + len(replacement)]
    if not expected or expected == replacement:
        raise BootstrapAuthoringError(f"authored site has no effective change: {site_id}")
    signature_start = max(region_start, rva - _CONTEXT_BYTES)
    signature_end = min(region_end, rva + len(expected) + _CONTEXT_BYTES)
    signature_offset = _region_rva_to_offset(
        image,
        section_name,
        signature_start,
        signature_end - signature_start,
    )
    value = bytearray(source[signature_offset : signature_offset + signature_end - signature_start])
    mask = bytearray(b"\xFF" * len(value))
    patch_start = rva - signature_start
    patch_end = patch_start + len(expected)
    value[patch_start:patch_end] = b"\0" * len(expected)
    mask[patch_start:patch_end] = b"\0" * len(expected)
    return PatchSite(
        site_id=site_id,
        section=section_name,
        reviewed_rva=rva,
        expected_original=expected,
        replacement=replacement,
        signature=MaskedSignature(bytes(value), bytes(mask)),
        signature_site_offset=patch_start,
        search_radius=0,
    )


def _apply_authored_sites(source: bytes, image: PeImage, sites: tuple[PatchSite, ...]) -> bytes:
    output = bytearray(source)
    occupied: list[tuple[int, int, str]] = []
    for site in sites:
        offset = _region_rva_to_offset(image, site.section, site.reviewed_rva, site.length)
        end = offset + site.length
        if source[offset:end] != site.expected_original:
            raise BootstrapAuthoringError(f"authored original bytes changed: {site.site_id}")
        occupied.append((offset, end, site.site_id))
        output[offset:end] = site.replacement
    for previous, current in zip(sorted(occupied), sorted(occupied)[1:], strict=False):
        if previous[1] > current[0]:
            raise BootstrapAuthoringError(
                f"authored sites overlap: {previous[2]} and {current[2]}"
            )
    return bytes(output)


def _require_zero_tail(
    source: bytes,
    section: PeSection,
    *,
    start_rva: int,
    end_rva: int,
    label: str,
) -> None:
    if start_rva < section.virtual_address or end_rva <= start_rva:
        raise BootstrapAuthoringError(f"{label} has an invalid reviewed range")
    relative_end = end_rva - section.virtual_address
    if relative_end > section.raw_size:
        raise BootstrapAuthoringError(f"{label} exceeds raw section capacity")
    offset = section.raw_offset + start_rva - section.virtual_address
    if any(source[offset : offset + end_rva - start_rva]):
        raise BootstrapAuthoringError(f"{label} is not verified zero padding")


def _region_bounds(image: PeImage, section_name: str) -> tuple[int, int]:
    if section_name == PE_HEADERS_SECTION:
        return 0, image.size_of_headers
    section = _find_section(image, section_name)
    return section.virtual_address, section.virtual_address + section.raw_size


def _region_rva_to_offset(
    image: PeImage,
    section_name: str,
    rva: int,
    length: int,
) -> int:
    if section_name == PE_HEADERS_SECTION:
        if rva < 0 or rva + length > image.size_of_headers:
            raise BootstrapAuthoringError("header patch leaves SizeOfHeaders")
        return rva
    section = _find_section(image, section_name)
    relative = rva - section.virtual_address
    if relative < 0 or relative + length > section.raw_size:
        raise BootstrapAuthoringError(f"patch leaves reviewed section {section_name}")
    return section.raw_offset + relative


def _find_section(image: PeImage, name: str) -> PeSection:
    matches = tuple(section for section in image.sections if section.name == name)
    if len(matches) != 1:
        raise BootstrapAuthoringError(f"PE does not contain exactly one {name} section")
    return matches[0]


def _rva_to_offset(image: PeImage, rva: int, length: int, label: str) -> int:
    if 0 <= rva and rva + length <= image.size_of_headers:
        return rva
    matches = tuple(
        section
        for section in image.sections
        if 0 <= rva - section.virtual_address
        and rva - section.virtual_address + length <= section.raw_size
    )
    if len(matches) != 1:
        raise BootstrapAuthoringError(f"{label} is not backed by exactly one raw section")
    section = matches[0]
    return section.raw_offset + rva - section.virtual_address


def _read_rva(source: bytes, image: PeImage, rva: int, length: int, label: str) -> bytes:
    offset = _rva_to_offset(image, rva, length, label)
    return source[offset : offset + length]


def _read_u32_rva(source: bytes, image: PeImage, rva: int, label: str) -> int:
    offset = _rva_to_offset(image, rva, 4, label)
    return _u32(source, offset, label)


def _read_ascii_rva(source: bytes, image: PeImage, rva: int, label: str) -> str:
    offset = _rva_to_offset(image, rva, 1, label)
    limit = min(len(source), offset + _MAX_ASCII_BYTES)
    terminator = source.find(b"\0", offset, limit)
    if terminator < 0:
        raise BootstrapAuthoringError(f"{label} is not null terminated")
    raw = source[offset:terminator]
    try:
        result = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise BootstrapAuthoringError(f"{label} is not ASCII") from exc
    if not result or any(not 0x20 <= ord(character) <= 0x7E for character in result):
        raise BootstrapAuthoringError(f"{label} is empty or not printable")
    return result


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def _pack_i32(value: int) -> bytes:
    if not -(1 << 31) <= value < 1 << 31:
        raise BootstrapAuthoringError("loader displacement exceeds signed 32-bit range")
    return struct.pack("<i", value)


def _unpack(format_string: str, source: bytes, offset: int, label: str) -> tuple[int, ...]:
    size = struct.calcsize(format_string)
    if offset < 0 or offset + size > len(source):
        raise BootstrapAuthoringError(f"{label} extends beyond the file")
    return struct.unpack_from(format_string, source, offset)


def _u16(source: bytes, offset: int, label: str) -> int:
    return _unpack("<H", source, offset, label)[0]


def _u32(source: bytes, offset: int, label: str) -> int:
    return _unpack("<I", source, offset, label)[0]


def _write_new_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise BootstrapAuthoringError(f"manifest output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            raise BootstrapAuthoringError(f"manifest output raced into existence: {path}")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "WONDERBANE_1_0_5_PROFILE",
    "BootstrapAuthoringError",
    "BootstrapAuthoringResult",
    "ReviewedBootstrapProfile",
    "ReviewedSection",
    "author_reviewed_bootstrap_file",
    "author_reviewed_bootstrap_manifest",
]
