from __future__ import annotations

import argparse
from pathlib import Path

import terrain_delivery_finalize as base


def _replace_function(source: str, name: str, replacement: str, next_name: str) -> str:
    start = source.index(f"def {name}(")
    end = source.index(f"\ndef {next_name}(", start)
    return source[:start] + replacement.rstrip() + "\n" + source[end + 1 :]


_PATCH_CMAKE = r'''def patch_cmake(native: Path) -> None:
    path = native / "CMakeLists.txt"
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return

    full_target = select_full_renderer_target(text)
    runtime_lines = "\n".join(f"        {source}" for source in RUNTIME_SOURCES)
    block = f"""

{MARKER}
# Exact-client terrain coverage repair. Policy tests are available in both build
# profiles, while client mutation/runtime sources belong exclusively to full.
add_library(wonderbane_terrain_material_core STATIC
    terrain_material_plan.cpp
    terrain_material_transaction.cpp
)
target_include_directories(wonderbane_terrain_material_core PUBLIC
    ${{CMAKE_CURRENT_SOURCE_DIR}}
)
target_compile_features(wonderbane_terrain_material_core PUBLIC cxx_std_20)
if(MSVC)
    target_compile_definitions(wonderbane_terrain_material_core PRIVATE
        UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT
    )
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
    if(WIN32)
        target_link_libraries(wonderbane_terrain_client_verification_test PRIVATE bcrypt)
    endif()
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
            target_compile_definitions(${{terrain_test_target}} PRIVATE
                UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX STRICT
            )
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
{END_MARKER}
"""
    path.write_text(text.rstrip() + block + "\n", encoding="utf-8", newline="\n")
'''


def patch_integration(repository: Path) -> None:
    path = repository / "tools" / "integrate_terrain_material_repair.py"
    source = path.read_text(encoding="utf-8")
    source = _replace_function(source, "patch_cmake", _PATCH_CMAKE, "_dllmain_candidates")
    path.write_text(source, encoding="utf-8", newline="\n")


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
    base.patch_codegen(repository)
    patch_integration(repository)
    base.write_product_gate(repository)
    base.remove_one_shot_workflows(repository)
    base.write_resolution(
        repository,
        args.convergence_parent,
        args.repair_parent,
        args.run_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
