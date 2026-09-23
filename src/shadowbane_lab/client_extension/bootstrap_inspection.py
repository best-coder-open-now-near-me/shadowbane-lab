"""Read-only evidence for choosing an exact x86 client bootstrap site."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import tempfile
from pathlib import Path
from typing import Any

from shadowbane_lab.client_alignment.model import PeImage, PeSection
from shadowbane_lab.client_alignment.pe import PeInspectionError, inspect_pe_bytes

BOOTSTRAP_INSPECTION_SCHEMA_VERSION = 1
PE_IMPORT_INSPECTION_SCHEMA_VERSION = 1
_IMAGE_DIRECTORY_ENTRY_IMPORT = 1
_IMAGE_SCN_MEM_EXECUTE = 0x20000000
_MAX_IMPORT_DESCRIPTORS = 4096
_MAX_IMPORT_THUNKS = 65_536
_MAX_IMPORT_NAME_BYTES = 512
_ENTRY_BYTES = 128
_MINIMUM_TRAILING_PADDING = 64
_PREFERRED_BOOTSTRAP_CAPACITY = 256


class BootstrapInspectionError(ValueError):
    """Raised when bootstrap evidence cannot be collected safely."""


def inspect_bootstrap_candidate(executable: bytes) -> dict[str, Any]:
    """Inspect one PE without asserting that any observed site is safe to patch."""

    image, layout, imports = _inspect_pe_imports(executable)
    return _inspect_bootstrap_with_imports(executable, image, layout, imports)


def inspect_pe_imports(executable: bytes) -> dict[str, Any]:
    """Inspect one PE import table without assigning runtime call-path authority."""

    image, layout, imports = _inspect_pe_imports(executable)
    return {
        "schema_version": PE_IMPORT_INSPECTION_SCHEMA_VERSION,
        "authorization": "evidence_only_no_runtime_route_authority",
        "executable": image.as_dict(),
        "pe_layout": layout,
        "imports": list(imports),
    }


def _inspect_pe_imports(
    executable: bytes,
) -> tuple[PeImage, dict[str, Any], tuple[dict[str, Any], ...]]:
    try:
        image = inspect_pe_bytes(executable, path="sb.exe")
    except PeInspectionError as exc:
        raise BootstrapInspectionError(f"candidate is not a supported PE image: {exc}") from exc
    layout = _pe_layout(executable, image)
    return image, layout, _parse_imports(executable, image, layout)


def _inspect_bootstrap_with_imports(
    executable: bytes,
    image: PeImage,
    layout: dict[str, Any],
    imports: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    entry_section = _section_for_rva(image, image.entry_point_rva, 1)
    if entry_section is None:
        raise BootstrapInspectionError("entry point is not backed by a raw PE section")
    entry_offset = _rva_to_offset(image, image.entry_point_rva, 1)
    if entry_offset is None:
        raise BootstrapInspectionError("entry point cannot be mapped to a file offset")
    entry_available = min(
        _ENTRY_BYTES,
        entry_section.raw_offset + entry_section.raw_size - entry_offset,
    )
    entry_bytes = executable[entry_offset : entry_offset + entry_available]
    disassembly = _disassemble_entry(image, entry_bytes)
    bootstrap_imports = tuple(
        item
        for item in imports
        if item["symbol"] in {"LoadLibraryA", "LoadLibraryW", "GetProcAddress"}
    )
    trailing_padding = _trailing_executable_padding(executable, image)
    can_call_loader = any(
        item["symbol"] in {"LoadLibraryA", "LoadLibraryW"} for item in bootstrap_imports
    )
    can_call_initializer = any(
        item["symbol"] == "GetProcAddress" for item in bootstrap_imports
    )
    has_preferred_capacity = any(
        item["length"] >= _PREFERRED_BOOTSTRAP_CAPACITY for item in trailing_padding
    )
    entry_prefix = disassembly.get("five_byte_prefix")
    entry_prefix_reviewable = bool(
        isinstance(entry_prefix, dict)
        and entry_prefix.get("length", 0) >= 5
        and not entry_prefix.get("contains_control_flow", True)
    )
    architecture_supported = image.machine == 0x14C and image.pointer_size == 4
    candidate_ready = (
        architecture_supported
        and can_call_loader
        and can_call_initializer
        and has_preferred_capacity
        and entry_prefix_reviewable
    )
    return {
        "schema_version": BOOTSTRAP_INSPECTION_SCHEMA_VERSION,
        "authorization": "evidence_only_no_patch_authority",
        "executable": image.as_dict(),
        "pe_layout": layout,
        "entry_point": {
            "rva": image.entry_point_rva,
            "file_offset": entry_offset,
            "section": entry_section.name,
            "bytes_hex": entry_bytes.hex(),
            "disassembly": disassembly,
        },
        "imports": list(imports),
        "bootstrap_imports": list(bootstrap_imports),
        "trailing_executable_padding": list(trailing_padding),
        "assessment": {
            "architecture_supported": architecture_supported,
            "imported_loader_available": can_call_loader,
            "imported_get_proc_address_available": can_call_initializer,
            "preferred_trailing_capacity_available": has_preferred_capacity,
            "entry_prefix_reviewable": entry_prefix_reviewable,
            "candidate_ready_for_manual_stub_review": candidate_ready,
            "detail": (
                "all mechanical prerequisites were observed; displaced instructions and stub "
                "bytes still require manual review"
                if candidate_ready
                else "one or more mechanical prerequisites for the preferred trampoline are absent"
            ),
        },
    }


def inspect_bootstrap_file(
    executable_path: str | Path,
    *,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(executable_path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise BootstrapInspectionError(f"could not read executable: {path}") from exc
    report = inspect_bootstrap_candidate(data)
    if output_path is not None:
        _atomic_write_json(Path(output_path), report)
    return report


def _pe_layout(executable: bytes, image: PeImage) -> dict[str, Any]:
    pe_offset = _u32(executable, 0x3C, "PE header pointer")
    coff_offset = pe_offset + 4
    optional_size = _u16(executable, coff_offset + 16, "optional-header size")
    optional_offset = coff_offset + 20
    section_table_offset = optional_offset + optional_size
    section_table_end = section_table_offset + len(image.sections) * 40
    first_raw_offset = min(
        (section.raw_offset for section in image.sections if section.raw_size),
        default=len(executable),
    )
    if section_table_end > first_raw_offset:
        raise BootstrapInspectionError("section table overlaps the first raw section")
    directory_relative = 96 if image.pointer_size == 4 else 112
    number_relative = 92 if image.pointer_size == 4 else 108
    if optional_size < directory_relative:
        raise BootstrapInspectionError("optional header does not contain data directories")
    directory_offset = optional_offset + directory_relative
    number_offset = optional_offset + number_relative
    directory_count = _u32(executable, number_offset, "data-directory count")
    available_directory_bytes = optional_size - (directory_offset - optional_offset)
    available_directories = min(directory_count, available_directory_bytes // 8)
    import_rva = 0
    import_size = 0
    if available_directories > _IMAGE_DIRECTORY_ENTRY_IMPORT:
        import_rva = _u32(
            executable,
            directory_offset + _IMAGE_DIRECTORY_ENTRY_IMPORT * 8,
            "import-directory RVA",
        )
        import_size = _u32(
            executable,
            directory_offset + _IMAGE_DIRECTORY_ENTRY_IMPORT * 8 + 4,
            "import-directory size",
        )
    return {
        "pe_header_offset": pe_offset,
        "optional_header_offset": optional_offset,
        "optional_header_size": optional_size,
        "section_table_offset": section_table_offset,
        "section_table_end_offset": section_table_end,
        "first_section_raw_offset": first_raw_offset,
        "section_header_slack_bytes": first_raw_offset - section_table_end,
        "data_directory_count": available_directories,
        "import_directory_rva": import_rva,
        "import_directory_size": import_size,
        "file_sha256_recheck": hashlib.sha256(executable).hexdigest(),
    }


def _parse_imports(
    executable: bytes,
    image: PeImage,
    layout: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    import_rva = layout["import_directory_rva"]
    import_size = layout["import_directory_size"]
    if not import_rva or not import_size:
        return ()
    import_offset = _rva_to_offset(image, import_rva, 20)
    if import_offset is None:
        raise BootstrapInspectionError("import directory is not backed by raw file data")
    import_section = _section_for_rva(image, import_rva, 1)
    if import_section is None:
        directory_end = min(image.size_of_headers, import_offset + import_size)
    else:
        directory_end = min(
            import_section.raw_offset + import_section.raw_size,
            import_offset + import_size,
        )
    imports: list[dict[str, Any]] = []
    terminated = False
    for descriptor_index in range(_MAX_IMPORT_DESCRIPTORS):
        descriptor_offset = import_offset + descriptor_index * 20
        if descriptor_offset + 20 > directory_end:
            break
        original_thunk, timestamp, forwarder, name_rva, first_thunk = _unpack(
            "<IIIII",
            executable,
            descriptor_offset,
            "import descriptor",
        )
        if not any((original_thunk, timestamp, forwarder, name_rva, first_thunk)):
            terminated = True
            break
        if not name_rva or not first_thunk:
            raise BootstrapInspectionError("import descriptor has missing required RVAs")
        library = _read_ascii_rva(executable, image, name_rva, "import library")
        lookup_rva = original_thunk or first_thunk
        thunk_size = image.pointer_size
        ordinal_mask = 1 << (thunk_size * 8 - 1)
        thunk_format = "<I" if thunk_size == 4 else "<Q"
        thunk_terminated = False
        for thunk_index in range(_MAX_IMPORT_THUNKS):
            thunk_rva = lookup_rva + thunk_index * thunk_size
            thunk_offset = _rva_to_offset(image, thunk_rva, thunk_size)
            if thunk_offset is None:
                raise BootstrapInspectionError("import lookup table leaves raw file data")
            (thunk_value,) = _unpack(
                thunk_format,
                executable,
                thunk_offset,
                "import thunk",
            )
            if thunk_value == 0:
                thunk_terminated = True
                break
            iat_rva = first_thunk + thunk_index * thunk_size
            if thunk_value & ordinal_mask:
                imports.append(
                    {
                        "library": library,
                        "symbol": None,
                        "ordinal": thunk_value & 0xFFFF,
                        "iat_rva": iat_rva,
                    }
                )
                continue
            name_offset = _rva_to_offset(image, thunk_value, 3)
            if name_offset is None:
                raise BootstrapInspectionError("import hint/name record is outside raw file data")
            symbol = _read_ascii_offset(
                executable,
                name_offset + 2,
                "import symbol",
            )
            imports.append(
                {
                    "library": library,
                    "symbol": symbol,
                    "ordinal": None,
                    "iat_rva": iat_rva,
                }
            )
        if not thunk_terminated:
            raise BootstrapInspectionError("import lookup table exceeds its safety bound")
    if not terminated:
        raise BootstrapInspectionError("import descriptor table is not terminated")
    return tuple(imports)


def _disassemble_entry(image: PeImage, entry_bytes: bytes) -> dict[str, Any]:
    try:
        from capstone import CS_ARCH_X86, CS_GRP_CALL, CS_GRP_JUMP, CS_MODE_32, Cs
    except ImportError:
        return {
            "available": False,
            "detail": "capstone is not installed; raw entry bytes were still recorded",
            "instructions": [],
            "five_byte_prefix": None,
        }
    if image.pointer_size != 4:
        return {
            "available": False,
            "detail": "only x86 entry-point review is supported",
            "instructions": [],
            "five_byte_prefix": None,
        }
    engine = Cs(CS_ARCH_X86, CS_MODE_32)
    engine.detail = True
    instructions: list[dict[str, Any]] = []
    prefix_length = 0
    prefix_control_flow = False
    expected_address = image.image_base + image.entry_point_rva
    for instruction in engine.disasm(entry_bytes, expected_address):
        if instruction.address != expected_address:
            break
        control_flow = instruction.group(CS_GRP_CALL) or instruction.group(CS_GRP_JUMP)
        instructions.append(
            {
                "rva": instruction.address - image.image_base,
                "size": instruction.size,
                "bytes_hex": bytes(instruction.bytes).hex(),
                "mnemonic": instruction.mnemonic,
                "operands": instruction.op_str,
                "control_flow": bool(control_flow),
            }
        )
        expected_address += instruction.size
        if prefix_length < 5:
            prefix_length += instruction.size
            prefix_control_flow = prefix_control_flow or bool(control_flow)
        if len(instructions) >= 32:
            break
    prefix = None
    if prefix_length >= 5:
        prefix = {
            "length": prefix_length,
            "bytes_hex": entry_bytes[:prefix_length].hex(),
            "contains_control_flow": prefix_control_flow,
        }
    return {
        "available": True,
        "detail": "Capstone x86 disassembly is evidence only and requires manual review",
        "instructions": instructions,
        "five_byte_prefix": prefix,
    }


def _trailing_executable_padding(
    executable: bytes,
    image: PeImage,
) -> tuple[dict[str, Any], ...]:
    results: list[dict[str, Any]] = []
    for section in image.sections:
        if not section.raw_size or not section.characteristics & _IMAGE_SCN_MEM_EXECUTE:
            continue
        slack_start = max(0, min(section.virtual_size, section.raw_size))
        if slack_start >= section.raw_size:
            continue
        region = executable[
            section.raw_offset + slack_start : section.raw_offset + section.raw_size
        ]
        run_start = 0
        while run_start < len(region):
            fill = region[run_start]
            if fill not in {0x00, 0xCC}:
                run_start += 1
                continue
            run_end = run_start + 1
            while run_end < len(region) and region[run_end] == fill:
                run_end += 1
            length = run_end - run_start
            if length >= _MINIMUM_TRAILING_PADDING:
                relative = slack_start + run_start
                results.append(
                    {
                        "section": section.name,
                        "rva": section.virtual_address + relative,
                        "file_offset": section.raw_offset + relative,
                        "length": length,
                        "fill_byte": fill,
                        "within_declared_virtual_size": False,
                    }
                )
            run_start = run_end
    results.sort(key=lambda item: (item["section"], item["rva"]))
    return tuple(results)


def _section_for_rva(image: PeImage, rva: int, length: int) -> PeSection | None:
    matches = tuple(
        section
        for section in image.sections
        if 0 <= rva - section.virtual_address
        and rva - section.virtual_address + length <= section.raw_size
    )
    if len(matches) > 1:
        raise BootstrapInspectionError("RVA maps to overlapping raw sections")
    return matches[0] if matches else None


def _rva_to_offset(image: PeImage, rva: int, length: int) -> int | None:
    if 0 <= rva and rva + length <= image.size_of_headers:
        return rva
    section = _section_for_rva(image, rva, length)
    if section is None:
        return None
    return section.raw_offset + (rva - section.virtual_address)


def _read_ascii_rva(executable: bytes, image: PeImage, rva: int, label: str) -> str:
    offset = _rva_to_offset(image, rva, 1)
    if offset is None:
        raise BootstrapInspectionError(f"{label} is outside raw file data")
    return _read_ascii_offset(executable, offset, label)


def _read_ascii_offset(executable: bytes, offset: int, label: str) -> str:
    end_limit = min(len(executable), offset + _MAX_IMPORT_NAME_BYTES)
    terminator = executable.find(b"\0", offset, end_limit)
    if terminator < 0:
        raise BootstrapInspectionError(f"{label} is not bounded by a null terminator")
    raw = executable[offset:terminator]
    if not raw:
        raise BootstrapInspectionError(f"{label} is empty")
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise BootstrapInspectionError(f"{label} is not ASCII") from exc
    if any(ord(character) < 0x20 or ord(character) > 0x7E for character in value):
        raise BootstrapInspectionError(f"{label} contains non-printable characters")
    return value


def _unpack(
    format_string: str,
    data: bytes,
    offset: int,
    label: str,
) -> tuple[int, ...]:
    size = struct.calcsize(format_string)
    if offset < 0 or offset + size > len(data):
        raise BootstrapInspectionError(f"{label} extends beyond the file")
    return struct.unpack_from(format_string, data, offset)


def _u16(data: bytes, offset: int, label: str) -> int:
    return _unpack("<H", data, offset, label)[0]


def _u32(data: bytes, offset: int, label: str) -> int:
    return _unpack("<I", data, offset, label)[0]


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise BootstrapInspectionError(f"inspection output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                payload,
                stream,
                sort_keys=True,
                indent=2,
                ensure_ascii=True,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            raise BootstrapInspectionError(f"inspection output raced into existence: {path}")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "BOOTSTRAP_INSPECTION_SCHEMA_VERSION",
    "PE_IMPORT_INSPECTION_SCHEMA_VERSION",
    "BootstrapInspectionError",
    "inspect_bootstrap_candidate",
    "inspect_bootstrap_file",
    "inspect_pe_imports",
]
