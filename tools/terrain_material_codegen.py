from __future__ import annotations

import argparse
import hashlib
import json
import struct
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pefile
from capstone import (
    CS_ARCH_X86,
    CS_GRP_CALL,
    CS_GRP_INT,
    CS_GRP_IRET,
    CS_GRP_JUMP,
    CS_GRP_RET,
    CS_MODE_32,
    Cs,
)

EXPECTED_SHA256 = "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc"
PATCH_ROOT = "http://87.99.132.84/"
MAXIMUM_DOWNLOAD = 128 * 1024 * 1024
IMAGE_BASE = 0x00400000


@dataclass(frozen=True)
class FunctionAbi:
    label: str
    entry_va: int
    scan_size: int
    maximum_stack_bytes: int


APPEND_ABI = FunctionAbi("append", 0x0069EE60, 0x900, 48)
REGISTRATION_ABI = FunctionAbi("registration", 0x006527B0, 0x1800, 64)

SIGNATURES: dict[str, tuple[int, int]] = {
    "ImageFactory": (0x0058D340, 32),
    "ImageSetter": (0x0058DB10, 32),
    "TextureAssignment": (0x005DDB60, 32),
    "TextureClone": (0x005DF2D0, 32),
    "MaterialRegistration": (0x006527B0, 32),
    "TerrainFinalizer": (0x0069ABD0, 32),
    "TerrainBuilder": (0x0069E2D0, 32),
    "MaterialAppend": (0x0069EE60, 32),
    "LookupInserting": (0x0069F5A0, 32),
    "LookupLowerBound": (0x0069F7A0, 32),
    "BuilderThunk": (0x004136D3, 16),
    "FinalizerThunk": (0x00415294, 16),
}


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": "shadowbane-lab-review"})


def download_reviewed_executable() -> bytes:
    with urllib.request.urlopen(_request(PATCH_ROOT + "manifest.json"), timeout=60) as response:
        manifest = json.loads(response.read().decode("utf-8-sig"))
    files = manifest.get("files")
    if not isinstance(files, list):
        raise RuntimeError("patch manifest files is not a list")
    base_url = manifest.get("baseUrl", "")
    if not isinstance(base_url, str):
        raise RuntimeError("patch manifest baseUrl is not a string")

    matches = [
        item
        for item in files
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and str(item.get("sha256", "")).lower() == EXPECTED_SHA256
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one reviewed executable in manifest, found {len(matches)}")

    download_base = urllib.parse.urljoin(PATCH_ROOT, base_url.rstrip("/") + "/")
    relative = matches[0]["path"].replace("\\", "/")
    url = urllib.parse.urljoin(download_base, urllib.parse.quote(relative))
    with urllib.request.urlopen(_request(url), timeout=180) as response:
        raw = response.read(MAXIMUM_DOWNLOAD + 1)
    if len(raw) > MAXIMUM_DOWNLOAD:
        raise RuntimeError("reviewed executable exceeds bounded download limit")
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
        raise RuntimeError("downloaded executable SHA-256 mismatch")
    expected_size = matches[0].get("size")
    if isinstance(expected_size, int) and expected_size != len(raw):
        raise RuntimeError("downloaded executable size mismatch")
    return raw


def bytes_at(pe: pefile.PE, raw: bytes, va: int, size: int) -> bytes:
    image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    offset = pe.get_offset_from_rva(va - image_base)
    payload = raw[offset : offset + size]
    if len(payload) != size:
        raise RuntimeError(f"short read at preferred VA {va:#x}")
    return payload


def analyze_abi(pe: pefile.PE, raw: bytes, abi: FunctionAbi) -> tuple[int, int, bytes]:
    payload = bytes_at(pe, raw, abi.entry_va, abi.scan_size)
    disassembler = Cs(CS_ARCH_X86, CS_MODE_32)
    disassembler.detail = True
    instructions = list(disassembler.disasm(payload, abi.entry_va))
    if not instructions or instructions[0].address != abi.entry_va:
        raise RuntimeError(f"could not decode {abi.label} entry")

    cleanup_values: set[int] = set()
    for instruction in instructions:
        if instruction.mnemonic == "ret":
            cleanup_values.add(int(instruction.op_str, 0) if instruction.op_str else 0)
    if len(cleanup_values) != 1:
        raise RuntimeError(f"{abi.label} has ambiguous stack cleanup: {cleanup_values}")
    stack_bytes = cleanup_values.pop()
    if stack_bytes % 4 != 0 or stack_bytes > abi.maximum_stack_bytes:
        raise RuntimeError(f"unsupported {abi.label} stack cleanup: {stack_bytes}")

    patch_length = 0
    forbidden = {CS_GRP_CALL, CS_GRP_INT, CS_GRP_IRET, CS_GRP_JUMP, CS_GRP_RET}
    for instruction in instructions:
        if any(group in forbidden for group in instruction.groups):
            raise RuntimeError(f"control-flow instruction occurs in {abi.label} prologue")
        patch_length += instruction.size
        if patch_length >= 5:
            break
    if not 5 <= patch_length <= 16:
        raise RuntimeError(f"unsupported {abi.label} patch length: {patch_length}")
    return stack_bytes, patch_length, payload[:patch_length]


def byte_list(payload: Iterable[int]) -> str:
    return ", ".join(f"0x{value:02X}U" for value in payload)


def generate_profile(pe: pefile.PE, raw: bytes, output: Path) -> None:
    image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    if image_base != IMAGE_BASE:
        raise RuntimeError(f"unexpected preferred image base: {image_base:#x}")

    builder_slot = struct.unpack("<I", bytes_at(pe, raw, 0x015634B4, 4))[0]
    finalizer_slot = struct.unpack("<I", bytes_at(pe, raw, 0x0154C120, 4))[0]
    if builder_slot != 0x004136D3:
        raise RuntimeError(f"builder vtable slot mismatch: {builder_slot:#x}")
    if finalizer_slot != 0x00415294:
        raise RuntimeError(f"finalizer vtable slot mismatch: {finalizer_slot:#x}")

    lines = [
        "#pragma once",
        "",
        "// Generated from the exact patch-manifest executable. Do not edit.",
        "// The executable itself is not retained in the repository.",
        "",
        "#include <array>",
        "#include <cstddef>",
        "#include <cstdint>",
        "",
        "namespace wonderbane::extension::terrain_material::client_profile {",
        "",
        f"inline constexpr std::uintptr_t kPreferredImageBase = 0x{image_base:08X}U;",
        f"inline constexpr std::size_t kExpectedFileSize = {len(raw)}U;",
        "inline constexpr std::size_t kExpectedImageSize = "
        f"{int(pe.OPTIONAL_HEADER.SizeOfImage)}U;",
        "inline constexpr std::array<std::uint8_t, 32> kExpectedSha256{",
        "    " + byte_list(bytes.fromhex(EXPECTED_SHA256)),
        "};",
        "",
        "inline constexpr std::uintptr_t kBuilderVtableSlot = 0x015634B4U;",
        "inline constexpr std::uintptr_t kBuilderThunk = 0x004136D3U;",
        "inline constexpr std::uintptr_t kBuilderMethod = 0x0069E2D0U;",
        "inline constexpr std::uintptr_t kFinalizerVtableSlot = 0x0154C120U;",
        "inline constexpr std::uintptr_t kFinalizerThunk = 0x00415294U;",
        "inline constexpr std::uintptr_t kFinalizerMethod = 0x0069ABD0U;",
        "inline constexpr std::uintptr_t kMaterialRegistration = 0x006527B0U;",
        "inline constexpr std::uintptr_t kMaterialAppend = 0x0069EE60U;",
        "inline constexpr std::uintptr_t kLookupInserting = 0x0069F5A0U;",
        "inline constexpr std::uintptr_t kLookupLowerBound = 0x0069F7A0U;",
        "inline constexpr std::uintptr_t kImageFactory = 0x0058D340U;",
        "inline constexpr std::uintptr_t kImageSetter = 0x0058DB10U;",
        "inline constexpr std::uintptr_t kTextureAssignment = 0x005DDB60U;",
        "inline constexpr std::uintptr_t kTextureClone = 0x005DF2D0U;",
        "",
    ]
    for name, (va, size) in SIGNATURES.items():
        payload = bytes_at(pe, raw, va, size)
        lines.extend(
            [
                f"inline constexpr std::uintptr_t k{name}SignatureAddress = 0x{va:08X}U;",
                f"inline constexpr std::array<std::uint8_t, {size}> k{name}Signature{{",
                "    " + byte_list(payload),
                "};",
                "",
            ]
        )
    lines.extend(
        [
            "}  // namespace wonderbane::extension::terrain_material::client_profile",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def generate_abi_header(
    namespace: str,
    stack_bytes: int,
    patch_length: int,
    prologue: bytes,
    output: Path,
) -> None:
    argument_count = stack_bytes // 4
    output.write_text(
        "\n".join(
            [
                "#pragma once",
                "",
                "// Generated from the exact reviewed x86 client. Do not edit.",
                "#include <array>",
                "#include <cstddef>",
                "#include <cstdint>",
                "",
                f"namespace wonderbane::extension::terrain_material::{namespace} {{",
                f"inline constexpr std::size_t kStackBytes = {stack_bytes}U;",
                f"inline constexpr std::size_t kArgumentCount = {argument_count}U;",
                f"inline constexpr std::size_t kPatchLength = {patch_length}U;",
                f"inline constexpr std::array<std::uint8_t, {patch_length}> kPrologue{{",
                "    " + byte_list(prologue),
                "};",
                f"}}  // namespace wonderbane::extension::terrain_material::{namespace}",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )


def generate_append_bridge(argument_count: int, output: Path) -> None:
    typed_args = "".join(", std::uint32_t" for _ in range(argument_count))
    declarations = ",\n    ".join(
        f"std::uint32_t argument{index}" for index in range(argument_count)
    )
    hook_separator = ",\n    " if argument_count else ""
    initializers = ", ".join(f"argument{index}" for index in range(argument_count))
    replay_args = "".join(
        f", arguments[{index}]" for index in range(argument_count)
    )
    source = f'''#include "terrain_append_bridge.h"

#include "terrain_append_abi.generated.h"
#include "terrain_material_capture.h"

#include <array>
#include <cstdint>

namespace wonderbane::extension::terrain_material {{
namespace {{

#if defined(_MSC_VER) && defined(_M_IX86)
using AppendFunction = std::uintptr_t (__thiscall*)(void*{typed_args});
AppendFunction g_append_trampoline = nullptr;

extern "C" std::uintptr_t __fastcall TerrainMaterialAppendHook(
    void* this_pointer,
    void*{hook_separator}{declarations}) noexcept {{
    std::array<std::uint32_t, append_abi::kArgumentCount> arguments{{{initializers}}};
    void* effective_this = this_pointer;
    RewriteMaterialAppendInvocation(effective_this, arguments);
    RecordMaterialAppendEnter(effective_this, arguments);
    const auto original = g_append_trampoline;
    const auto result = original == nullptr
        ? 0U
        : original(effective_this{replay_args});
    RecordMaterialAppendExit(result);
    return result;
}}
#endif

}}  // namespace

void SetMaterialAppendTrampoline(void* trampoline) noexcept {{
#if defined(_MSC_VER) && defined(_M_IX86)
    g_append_trampoline = reinterpret_cast<AppendFunction>(trampoline);
#else
    (void)trampoline;
#endif
}}

void* MaterialAppendHookAddress() noexcept {{
#if defined(_MSC_VER) && defined(_M_IX86)
    return reinterpret_cast<void*>(&TerrainMaterialAppendHook);
#else
    return nullptr;
#endif
}}

std::uintptr_t InvokeMaterialAppend(
    void* this_pointer,
    const std::span<const std::uint32_t> arguments) noexcept {{
#if defined(_MSC_VER) && defined(_M_IX86)
    const auto original = g_append_trampoline;
    if (original == nullptr || arguments.size() != append_abi::kArgumentCount) {{
        return 0U;
    }}
    return original(this_pointer{replay_args});
#else
    (void)this_pointer;
    (void)arguments;
    return 0U;
#endif
}}

}}  // namespace wonderbane::extension::terrain_material
'''
    output.write_text(source, encoding="utf-8", newline="\n")


def generate_registration_bridge(argument_count: int, output: Path) -> None:
    typed_args = "".join(", std::uint32_t" for _ in range(argument_count))
    declarations = ",\n    ".join(
        f"std::uint32_t argument{index}" for index in range(argument_count)
    )
    hook_separator = ",\n    " if argument_count else ""
    initializers = ", ".join(f"argument{index}" for index in range(argument_count))
    replay_args = "".join(f", argument{index}" for index in range(argument_count))
    source = f'''#include "terrain_registration_bridge.h"

#include "terrain_registration_abi.generated.h"

#include <array>
#include <cstdint>

namespace wonderbane::extension::terrain_material {{
namespace {{

#if defined(_MSC_VER) && defined(_M_IX86)
using RegistrationFunction = std::uintptr_t (__thiscall*)(void*{typed_args});
RegistrationFunction g_registration_trampoline = nullptr;

extern "C" std::uintptr_t __fastcall TerrainMaterialRegistrationHook(
    void* this_pointer,
    void*{hook_separator}{declarations}) noexcept {{
    const auto original = g_registration_trampoline;
    const auto result = original == nullptr
        ? 0U
        : original(this_pointer{replay_args});
    const std::array<std::uint32_t, registration_abi::kArgumentCount> arguments{{{initializers}}};
    RecordMaterialRegistration(this_pointer, arguments, result);
    return result;
}}
#endif

}}  // namespace

void SetMaterialRegistrationTrampoline(void* trampoline) noexcept {{
#if defined(_MSC_VER) && defined(_M_IX86)
    g_registration_trampoline = reinterpret_cast<RegistrationFunction>(trampoline);
#else
    (void)trampoline;
#endif
}}

void* MaterialRegistrationHookAddress() noexcept {{
#if defined(_MSC_VER) && defined(_M_IX86)
    return reinterpret_cast<void*>(&TerrainMaterialRegistrationHook);
#else
    return nullptr;
#endif
}}

}}  // namespace wonderbane::extension::terrain_material
'''
    output.write_text(source, encoding="utf-8", newline="\n")


def generate(repository: Path) -> None:
    raw = download_reviewed_executable()
    pe = pefile.PE(data=raw, fast_load=False)
    if int(pe.OPTIONAL_HEADER.ImageBase) != IMAGE_BASE:
        raise RuntimeError("reviewed executable preferred base changed")

    native = repository / "native" / "wonderbane_extension"
    native.mkdir(parents=True, exist_ok=True)
    generate_profile(pe, raw, native / "terrain_client_profile.generated.h")

    append_stack, append_patch, append_prologue = analyze_abi(pe, raw, APPEND_ABI)
    generate_abi_header(
        "append_abi",
        append_stack,
        append_patch,
        append_prologue,
        native / "terrain_append_abi.generated.h",
    )
    generate_append_bridge(
        append_stack // 4,
        native / "terrain_append_bridge.generated.cpp",
    )

    registration_stack, registration_patch, registration_prologue = analyze_abi(
        pe, raw, REGISTRATION_ABI
    )
    generate_abi_header(
        "registration_abi",
        registration_stack,
        registration_patch,
        registration_prologue,
        native / "terrain_registration_abi.generated.h",
    )
    generate_registration_bridge(
        registration_stack // 4,
        native / "terrain_registration_bridge.generated.cpp",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate exact WonderBane terrain-repair ABI sources"
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path.cwd(),
        help="repository root (default: current directory)",
    )
    args = parser.parse_args()
    generate(args.repository.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
