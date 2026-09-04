from __future__ import annotations

import argparse
import re
from pathlib import Path

EXECUTABLE_SECTION_FLAG = 0x20000000


def _replace_function(source: str, name: str, replacement: str, next_name: str) -> str:
    start = source.index(f"def {name}(")
    end = source.index(f"\ndef {next_name}(", start)
    return source[:start] + replacement.rstrip() + "\n" + source[end + 1 :]


def patch_codegen(repository: Path) -> None:
    path = repository / "tools" / "terrain_material_codegen.py"
    source = path.read_text(encoding="utf-8")
    if "CS_OP_IMM," not in source:
        anchor = "    CS_MODE_32,\n"
        if source.count(anchor) != 1:
            raise RuntimeError("could not locate capstone import insertion point")
        source = source.replace(anchor, anchor + "    CS_OP_IMM,\n")

    replacement = r'''def analyze_abi(pe: pefile.PE, raw: bytes, abi: FunctionAbi) -> tuple[int, int, bytes]:
    """Recover an ABI only from instructions reachable from the exact entry.

    Calls are fallthrough-only. Direct branches are followed inside executable PE
    sections. Indirect branches, escaping/non-executable targets, overlapping
    instructions, unsupported returns, and inconsistent cleanup values fail closed.
    """
    image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    executable_ranges: list[tuple[int, int]] = []
    for section in pe.sections:
        if int(section.Characteristics) & 0x20000000 == 0:
            continue
        start = image_base + int(section.VirtualAddress)
        size = max(int(section.Misc_VirtualSize), int(section.SizeOfRawData))
        if size > 0:
            executable_ranges.append((start, start + size))
    if not executable_ranges:
        raise RuntimeError("reviewed client has no executable PE section")

    def executable_end(address: int) -> int | None:
        for start, end in executable_ranges:
            if start <= address < end:
                return end
        return None

    disassembler = Cs(CS_ARCH_X86, CS_MODE_32)
    disassembler.detail = True
    decoded: dict[int, object] = {}
    byte_owner: dict[int, int] = {}

    def decode_one(address: int):
        if address in decoded:
            return decoded[address]
        section_end = executable_end(address)
        if section_end is None:
            raise RuntimeError(
                f"{abi.label} control flow reached non-executable address {address:#x}"
            )
        size = min(16, section_end - address)
        if size <= 0:
            raise RuntimeError(f"{abi.label} reached an empty executable range")
        payload = bytes_at(pe, raw, address, size)
        items = list(disassembler.disasm(payload, address, 1))
        if not items or items[0].address != address:
            raise RuntimeError(
                f"could not decode reachable {abi.label} instruction at {address:#x}"
            )
        instruction = items[0]
        if instruction.size <= 0:
            raise RuntimeError(f"invalid {abi.label} instruction size at {address:#x}")
        for byte_address in range(address, address + instruction.size):
            owner = byte_owner.get(byte_address)
            if owner is not None and owner != address:
                raise RuntimeError(
                    f"{abi.label} branch targets the middle of an instruction at "
                    f"{address:#x}"
                )
            byte_owner[byte_address] = address
        decoded[address] = instruction
        return instruction

    cleanup_values: set[int] = set()
    pending = [abi.entry_va]
    visited: set[int] = set()
    maximum_reachable = max(4096, abi.scan_size * 16)
    while pending:
        address = pending.pop()
        while address not in visited:
            if len(visited) >= maximum_reachable:
                raise RuntimeError(f"{abi.label} reachable instruction bound was exceeded")
            instruction = decode_one(address)
            visited.add(address)
            next_address = instruction.address + instruction.size

            if instruction.mnemonic in {"hlt", "ud2"}:
                raise RuntimeError(
                    f"unsupported terminal instruction in {abi.label} at "
                    f"{instruction.address:#x}"
                )
            if CS_GRP_INT in instruction.groups or CS_GRP_IRET in instruction.groups:
                raise RuntimeError(
                    f"unsupported interrupt control flow in {abi.label} at "
                    f"{instruction.address:#x}"
                )
            if CS_GRP_RET in instruction.groups:
                if instruction.mnemonic != "ret":
                    raise RuntimeError(
                        f"unsupported return form in {abi.label} at "
                        f"{instruction.address:#x}"
                    )
                if not instruction.operands:
                    cleanup = 0
                elif len(instruction.operands) == 1 and instruction.operands[0].type == CS_OP_IMM:
                    cleanup = int(instruction.operands[0].imm)
                else:
                    raise RuntimeError(
                        f"unsupported return operands in {abi.label} at "
                        f"{instruction.address:#x}"
                    )
                if cleanup < 0 or cleanup % 4 != 0:
                    raise RuntimeError(f"invalid {abi.label} return cleanup: {cleanup}")
                cleanup_values.add(cleanup)
                break
            if CS_GRP_JUMP in instruction.groups:
                if len(instruction.operands) != 1 or instruction.operands[0].type != CS_OP_IMM:
                    raise RuntimeError(
                        f"indirect {abi.label} jump is outside the reviewed ABI contract at "
                        f"{instruction.address:#x}"
                    )
                target = int(instruction.operands[0].imm) & 0xFFFFFFFF
                if executable_end(target) is None:
                    raise RuntimeError(
                        f"{abi.label} jump escapes executable client code: "
                        f"{instruction.address:#x} -> {target:#x}"
                    )
                pending.append(target)
                if instruction.mnemonic == "jmp":
                    break
                if not (
                    instruction.mnemonic.startswith("j")
                    or instruction.mnemonic.startswith("loop")
                ):
                    raise RuntimeError(
                        f"unsupported {abi.label} branch mnemonic "
                        f"{instruction.mnemonic!r}"
                    )
                address = next_address
                continue
            # Direct and indirect calls deliberately are not followed. The current
            # function's ABI is determined by its own reachable exits.
            address = next_address

    if not cleanup_values:
        raise RuntimeError(f"{abi.label} has no reachable return")
    if len(cleanup_values) != 1:
        raise RuntimeError(
            f"{abi.label} reachable returns disagree on stack cleanup: {cleanup_values}"
        )
    stack_bytes = cleanup_values.pop()
    if stack_bytes > abi.maximum_stack_bytes:
        raise RuntimeError(f"unsupported {abi.label} stack cleanup: {stack_bytes}")

    patch_length = 0
    address = abi.entry_va
    forbidden = {CS_GRP_CALL, CS_GRP_INT, CS_GRP_IRET, CS_GRP_JUMP, CS_GRP_RET}
    prologue = bytearray()
    while patch_length < 5:
        instruction = decode_one(address)
        if any(group in forbidden for group in instruction.groups):
            raise RuntimeError(
                f"relative/control-flow instruction occurs in {abi.label} prologue"
            )
        prologue.extend(instruction.bytes)
        patch_length += instruction.size
        address += instruction.size
    if patch_length > 16:
        raise RuntimeError(f"unsupported {abi.label} patch length: {patch_length}")
    return stack_bytes, patch_length, bytes(prologue)
'''
    source = _replace_function(source, "analyze_abi", replacement, "byte_list")
    source = source.replace(
        "pe = pefile.PE(data=raw, fast_load=False)",
        "pe = pefile.PE(data=raw, fast_load=True)",
    )
    if "pe = pefile.PE(data=raw, fast_load=True)" not in source:
        raise RuntimeError("unexpected PE parser construction")
    path.write_text(source, encoding="utf-8", newline="\n")


def patch_integration(repository: Path) -> None:
    path = repository / "tools" / "integrate_terrain_material_repair.py"
    source = path.read_text(encoding="utf-8")
    start = source.index('    cmake_block = f"""')
    end = source.index("\n    updated_cmake =", start)
    replacement = '''    cmake_block = f"""
{START_MARKER}
add_library(wonderbane_terrain_material_core STATIC
{policy_lines}
)
target_compile_features(wonderbane_terrain_material_core PUBLIC cxx_std_20)
if(MSVC)
    target_compile_options(wonderbane_terrain_material_core PRIVATE
        /W4 /WX /permissive- /sdl /GS /guard:cf /Zc:__cplusplus /utf-8
    )
    set_property(TARGET wonderbane_terrain_material_core
        PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
endif()

if(BUILD_TESTING)
    add_executable(wonderbane_terrain_material_plan_test
        terrain_material_plan_test.cpp
    )
    target_link_libraries(wonderbane_terrain_material_plan_test PRIVATE
        wonderbane_terrain_material_core
    )
    add_test(NAME wonderbane_terrain_material_plan_test
        COMMAND wonderbane_terrain_material_plan_test
    )

    add_executable(wonderbane_terrain_material_transaction_test
        terrain_material_transaction_test.cpp
    )
    target_link_libraries(wonderbane_terrain_material_transaction_test PRIVATE
        wonderbane_terrain_material_core
    )
    add_test(NAME wonderbane_terrain_material_transaction_test
        COMMAND wonderbane_terrain_material_transaction_test
    )

    add_executable(wonderbane_terrain_vtable_hook_test
        terrain_vtable_hook.cpp
        terrain_vtable_hook_test.cpp
    )
    add_test(NAME wonderbane_terrain_vtable_hook_test
        COMMAND wonderbane_terrain_vtable_hook_test
    )

    add_executable(wonderbane_terrain_client_verification_test
        terrain_client_verification.cpp
        terrain_client_verification_test.cpp
    )
    add_test(NAME wonderbane_terrain_client_verification_test
        COMMAND wonderbane_terrain_client_verification_test
    )

    foreach(terrain_test_target
        wonderbane_terrain_material_plan_test
        wonderbane_terrain_material_transaction_test
        wonderbane_terrain_vtable_hook_test
        wonderbane_terrain_client_verification_test
    )
        target_compile_features(${{terrain_test_target}} PRIVATE cxx_std_20)
        if(MSVC)
            target_compile_options(${{terrain_test_target}} PRIVATE
                /W4 /WX /permissive- /sdl /GS /guard:cf /Zc:__cplusplus /utf-8
            )
            target_link_options(${{terrain_test_target}} PRIVATE
                /DYNAMICBASE /NXCOMPAT /guard:cf /INCREMENTAL:NO
            )
            set_property(TARGET ${{terrain_test_target}}
                PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
        endif()
    endforeach()
endif()

if(WONDERBANE_EXTENSION_PROFILE STREQUAL "full")
    target_sources({full_target} PRIVATE
{runtime_lines}
    )
    target_link_libraries({full_target} PRIVATE
        wonderbane_terrain_material_core
        bcrypt
    )
    target_compile_features({full_target} PRIVATE cxx_std_20)
    target_compile_definitions({full_target} PRIVATE
        WB_ENABLE_TERRAIN_MATERIAL_REPAIR=1
    )
elseif(NOT WONDERBANE_EXTENSION_PROFILE STREQUAL "diagnostics-only")
    message(FATAL_ERROR "Terrain repair requires an explicit reviewed extension profile")
endif()
{END_MARKER}"""'''
    source = source[:start] + replacement + source[end:]
    path.write_text(source, encoding="utf-8", newline="\n")


def write_product_gate(repository: Path) -> None:
    path = repository / ".github" / "workflows" / "terrain-repair-product-gate.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '''name: Terrain repair product gate

on:
  push:
    branches:
      - codex/client-convergence-v2
  pull_request:
    branches:
      - codex/client-convergence-v2
  workflow_dispatch:

permissions:
  contents: read

jobs:
  contracts-python-package:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install validation dependencies
        run: |
          python -m pip install --disable-pip-version-check --upgrade pip
          python -m pip install --disable-pip-version-check -e . pytest ruff build pefile==2024.8.26 capstone==5.0.9
      - name: Prove exact-client contracts are reproducible
        run: |
          set -euo pipefail
          find native/wonderbane_extension -maxdepth 1 -name 'terrain_*generated*' -type f -print0 | sort -z | xargs -0 sha256sum > /tmp/contracts.before
          python tools/terrain_material_codegen.py --repository .
          find native/wonderbane_extension -maxdepth 1 -name 'terrain_*generated*' -type f -print0 | sort -z | xargs -0 sha256sum > /tmp/contracts.after
          diff -u /tmp/contracts.before /tmp/contracts.after
          git diff --exit-code
      - name: Run Python, quality, and packaging gates
        run: |
          python -m pytest -q
          python -m ruff check .
          python -m build

  native-win32:
    runs-on: windows-latest
    strategy:
      fail-fast: false
      matrix:
        profile: [full, diagnostics-only]
    steps:
      - uses: actions/checkout@v4
      - name: Configure reviewed Win32 profile
        shell: pwsh
        run: |
          cmake -S native/wonderbane_extension -B "build/${{ matrix.profile }}" `
            -G "Visual Studio 17 2022" -A Win32 `
            -DWONDERBANE_EXTENSION_PROFILE=${{ matrix.profile }} -DBUILD_TESTING=ON
          if ($LASTEXITCODE -ne 0) { throw 'CMake configure failed' }
      - name: Prove product ownership boundary
        shell: pwsh
        run: |
          $project = Get-Content -LiteralPath "build/${{ matrix.profile }}/wonderbane_extension.vcxproj" -Raw
          $runtime = @(
            'terrain_client_verification.cpp',
            'terrain_inline_hook.cpp',
            'terrain_vtable_hook.cpp',
            'terrain_material_client_adapter.cpp',
            'terrain_material_runtime.cpp',
            'terrain_material_bootstrap.cpp',
            'terrain_append_bridge.generated.cpp',
            'terrain_registration_bridge.generated.cpp'
          )
          if ('${{ matrix.profile }}' -eq 'full') {
            foreach ($source in $runtime) {
              if ($project -notmatch [regex]::Escape($source)) { throw "Full project omits $source" }
            }
            if ($project -notmatch 'WB_ENABLE_TERRAIN_MATERIAL_REPAIR=1') { throw 'Full project omits repair enable definition' }
          }
          else {
            foreach ($source in $runtime) {
              if ($project -match [regex]::Escape($source)) { throw "Diagnostics project contains $source" }
            }
            if ($project -match 'WB_ENABLE_TERRAIN_MATERIAL_REPAIR') { throw 'Diagnostics project enables repair' }
          }
      - name: Build and run native tests
        shell: pwsh
        run: |
          cmake --build "build/${{ matrix.profile }}" --config Release --parallel
          if ($LASTEXITCODE -ne 0) { throw 'Native build failed' }
          ctest --test-dir "build/${{ matrix.profile }}" -C Release --output-on-failure
          if ($LASTEXITCODE -ne 0) { throw 'Native tests failed' }
      - name: Create receipt
        shell: pwsh
        run: |
          New-Item -ItemType Directory -Path receipt -Force | Out-Null
          $dll = Get-ChildItem -LiteralPath "build/${{ matrix.profile }}" -Recurse -File -Filter 'wonderbane-extension.dll' | Select-Object -First 1
          if ($null -eq $dll) { throw 'Built extension DLL was not found' }
          $destination = "receipt/wonderbane-extension-${{ matrix.profile }}.dll"
          Copy-Item -LiteralPath $dll.FullName -Destination $destination
          [ordered]@{
            schema = 'shadowbane-terrain-repair-build-receipt-v1'
            source_commit = '${{ github.sha }}'
            profile = '${{ matrix.profile }}'
            generator = 'Visual Studio 17 2022'
            platform = 'Win32'
            configuration = 'Release'
            dll_size = (Get-Item -LiteralPath $destination).Length
            dll_sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
          } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "receipt/${{ matrix.profile }}.json" -Encoding UTF8
      - uses: actions/upload-artifact@v4
        with:
          name: terrain-repair-${{ matrix.profile }}-${{ github.sha }}
          path: receipt/
          if-no-files-found: error
          retention-days: 30
''',
        encoding="utf-8",
        newline="\n",
    )


def remove_one_shot_workflows(repository: Path) -> None:
    names = {
        "generate-terrain-append-abi.yml",
        "generate-terrain-client-profile.yml",
        "generate-terrain-registration-abi.yml",
        "terrain-material-finalize.yml",
        "terrain-material-repair.yml",
        "terrain-material-transaction.yml",
        "wire-terrain-material-core.yml",
    }
    workflow_root = repository / ".github" / "workflows"
    for name in names:
        path = workflow_root / name
        if path.exists():
            path.unlink()


def write_resolution(
    repository: Path,
    convergence_parent: str,
    repair_parent: str,
    run_id: str,
) -> None:
    path = repository / "docs" / "handoffs" / "terrain-delivery-resolution-20260904.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'''# Terrain material repair delivery resolution

This product commit is assembled as a clean merge of:

- convergence parent: `{convergence_parent}`
- reviewed repair parent: `{repair_parent}`
- delivery workflow run: `{run_id}`

The convergence ref is advanced only after the following gates pass in the same
workflow:

- exact `55fbad5f...f5c61bc` client contracts regenerate byte-for-byte;
- the repair runtime and generated bridges are members of the full renderer only;
- the diagnostics-only extension project contains no repair runtime sources or
  repair enable definition;
- both Visual Studio 2022 Win32 profiles build and pass CTest;
- the repository Python suite, Ruff, wheel build, and source-distribution build pass;
- full and diagnostics DLLs receive SHA-256 build receipts and are uploaded before
  convergence is pushed.

The repair does not change zone ownership, terrain heights, collision, geometry,
or shared archive bytes. Ambiguous coverage and unsupported ownership/rotation
states remain fail-closed. Snapshot 6 remains rejected evidence.

No VM visual acceptance is claimed by this file. One bounded Sea Dog's Rest visual
pass remains after the accepted full-renderer package is installed.
''',
        encoding="utf-8",
        newline="\n",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--convergence-parent", required=True)
    parser.add_argument("--repair-parent", required=True)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repository = args.repository.resolve()
    patch_codegen(repository)
    patch_integration(repository)
    write_product_gate(repository)
    remove_one_shot_workflows(repository)
    write_resolution(
        repository,
        args.convergence_parent,
        args.repair_parent,
        args.run_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
