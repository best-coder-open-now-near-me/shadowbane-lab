from __future__ import annotations

import argparse
import re
from pathlib import Path

MARKER = "# BEGIN SHADOWBANE TERRAIN MATERIAL REPAIR"
END_MARKER = "# END SHADOWBANE TERRAIN MATERIAL REPAIR"

RUNTIME_SOURCES = [
    "terrain_client_verification.cpp",
    "terrain_inline_hook.cpp",
    "terrain_vtable_hook.cpp",
    "terrain_material_client_adapter.cpp",
    "terrain_material_runtime.cpp",
    "terrain_material_bootstrap.cpp",
    "terrain_append_bridge.generated.cpp",
    "terrain_registration_bridge.generated.cpp",
]

REQUIRED_GENERATED = [
    "terrain_client_profile.generated.h",
    "terrain_append_abi.generated.h",
    "terrain_append_bridge.generated.cpp",
    "terrain_registration_abi.generated.h",
    "terrain_registration_bridge.generated.cpp",
]

ONE_SHOT_WORKFLOWS = [
    "wire-terrain-material-core.yml",
    "generate-terrain-client-profile.yml",
    "generate-terrain-append-abi.yml",
    "generate-terrain-registration-abi.yml",
]


def _native_root(repository: Path) -> Path:
    native = repository / "native" / "wonderbane_extension"
    if not native.is_dir():
        raise RuntimeError(f"native extension directory not found: {native}")
    return native


def finalize_runtime_source(native: Path) -> None:
    integrated = native / "terrain_material_runtime_integrated.cpp"
    runtime = native / "terrain_material_runtime.cpp"
    if integrated.exists():
        runtime.write_text(
            integrated.read_text(encoding="utf-8"),
            encoding="utf-8",
            newline="\n",
        )
        integrated.unlink()
    if not runtime.exists():
        raise RuntimeError("terrain material runtime implementation is missing")


def _library_targets(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r"add_library\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s+"
        r"(?:(STATIC|SHARED|MODULE|OBJECT|INTERFACE)\b)?",
        re.IGNORECASE,
    )
    return [(match.group(1), (match.group(2) or "").upper()) for match in pattern.finditer(text)]


def select_full_renderer_target(text: str) -> str:
    targets = _library_targets(text)
    names = [name for name, _ in targets]
    if "wonderbane_extension" in names:
        return "wonderbane_extension"

    candidates = [
        name
        for name, kind in targets
        if kind in {"SHARED", "MODULE"}
        and "wonderbane" in name.lower()
        and "diagnostic" not in name.lower()
        and "test" not in name.lower()
    ]
    if len(candidates) == 1:
        return candidates[0]

    extension_candidates = [
        name
        for name, kind in targets
        if kind in {"SHARED", "MODULE"}
        and "diagnostic" not in name.lower()
        and "test" not in name.lower()
    ]
    if len(extension_candidates) == 1:
        return extension_candidates[0]
    raise RuntimeError(
        "could not identify one full-renderer CMake target; candidates="
        f"{targets!r}"
    )


def patch_cmake(native: Path) -> None:
    path = native / "CMakeLists.txt"
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return

    full_target = select_full_renderer_target(text)
    diagnostics_targets = [
        name for name, _ in _library_targets(text) if "diagnostic" in name.lower()
    ]
    if full_target in diagnostics_targets:
        raise RuntimeError("selected full target is a diagnostics target")

    runtime_lines = "\n".join(f"        {source}" for source in RUNTIME_SOURCES)
    diagnostics_comment = (
        ", ".join(diagnostics_targets) if diagnostics_targets else "none declared here"
    )
    block = f"""

{MARKER}
# Exact-client terrain coverage repair. Only the full renderer target receives
# these sources and the enabling definition. Diagnostics targets observed while
# generating this block: {diagnostics_comment}.
add_library(wonderbane_terrain_material_core STATIC
    terrain_material_plan.cpp
    terrain_material_transaction.cpp
)
target_include_directories(wonderbane_terrain_material_core PUBLIC
    ${{CMAKE_CURRENT_SOURCE_DIR}}
)
target_compile_features(wonderbane_terrain_material_core PUBLIC cxx_std_20)

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
    if(WIN32)
        target_link_libraries(wonderbane_terrain_client_verification_test PRIVATE bcrypt)
    endif()
    add_test(NAME wonderbane_terrain_client_verification_test
        COMMAND wonderbane_terrain_client_verification_test
    )
endif()
{END_MARKER}
"""
    path.write_text(text.rstrip() + block + "\n", encoding="utf-8", newline="\n")


def _dllmain_candidates(native: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in native.glob("*.cpp"):
        if "DllMain" in path.read_text(encoding="utf-8", errors="replace"):
            candidates.append(path)
    return candidates


def patch_dllmain(native: Path) -> None:
    candidates = _dllmain_candidates(native)
    if len(candidates) != 1:
        raise RuntimeError(f"expected one DllMain source, found {candidates!r}")
    path = candidates[0]
    text = path.read_text(encoding="utf-8")
    if "QueueTerrainMaterialRepairStartup" in text:
        return

    signature = re.search(
        r"DllMain\s*\(\s*(?:HINSTANCE|HMODULE)\s+([A-Za-z_][A-Za-z0-9_]*)",
        text,
    )
    if signature is None:
        raise RuntimeError(f"could not parse DllMain module parameter in {path}")
    module_name = signature.group(1)

    include = '#include "terrain_material_bootstrap.h"\n'
    include_matches = list(re.finditer(r"^#include[^\n]*\n", text, re.MULTILINE))
    if not include_matches:
        raise RuntimeError(f"no include insertion point in {path}")
    insertion = include_matches[-1].end()
    text = text[:insertion] + include + text[insertion:]

    guarded_call = (
        "\n#if defined(WB_ENABLE_TERRAIN_MATERIAL_REPAIR)\n"
        "        (void)wonderbane::extension::terrain_material::"
        f"QueueTerrainMaterialRepairStartup({module_name});\n"
        "#endif\n"
    )

    case_match = re.search(r"case\s+DLL_PROCESS_ATTACH\s*:\s*", text)
    if case_match is not None:
        insertion = case_match.end()
        text = text[:insertion] + guarded_call + text[insertion:]
    else:
        if_match = re.search(
            r"if\s*\([^\)]*DLL_PROCESS_ATTACH[^\)]*\)\s*\{",
            text,
        )
        if if_match is None:
            raise RuntimeError(f"could not locate DLL_PROCESS_ATTACH block in {path}")
        insertion = if_match.end()
        text = text[:insertion] + guarded_call + text[insertion:]

    path.write_text(text, encoding="utf-8", newline="\n")


def remove_one_shot_workflows(repository: Path) -> None:
    workflows = repository / ".github" / "workflows"
    for name in ONE_SHOT_WORKFLOWS:
        path = workflows / name
        if path.exists():
            path.unlink()


def verify_generated(native: Path) -> None:
    missing = [name for name in REQUIRED_GENERATED if not (native / name).is_file()]
    if missing:
        raise RuntimeError(f"generated terrain ABI files are missing: {missing!r}")


def integrate(repository: Path) -> None:
    native = _native_root(repository)
    verify_generated(native)
    finalize_runtime_source(native)
    patch_cmake(native)
    patch_dllmain(native)
    remove_one_shot_workflows(repository)


def main() -> int:
    parser = argparse.ArgumentParser(description="Wire the exact-client terrain repair")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    args = parser.parse_args()
    integrate(args.repository.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
