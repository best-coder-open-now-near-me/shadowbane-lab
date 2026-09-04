from __future__ import annotations

import argparse
from pathlib import Path

import terrain_delivery_finalize as base
import terrain_delivery_finalize_v2 as v2


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"unexpected {label} source shape")
    return source.replace(old, new)


def patch_native_compile_issues(repository: Path) -> None:
    native = repository / "native" / "wonderbane_extension"

    inline_path = native / "terrain_inline_hook.cpp"
    inline_source = inline_path.read_text(encoding="utf-8")
    inline_source = _replace_once(
        inline_source,
        "std::fill_n(patch.begin(), expected_prologue.size(), 0x90U);",
        "std::fill_n(\n"
        "        patch.begin(),\n"
        "        expected_prologue.size(),\n"
        "        static_cast<std::uint8_t>(0x90U));",
        "inline-hook patch fill",
    )
    inline_path.write_text(inline_source, encoding="utf-8", newline="\n")

    runtime_path = native / "terrain_material_runtime_integrated.cpp"
    runtime_source = runtime_path.read_text(encoding="utf-8")
    runtime_source = _replace_once(
        runtime_source,
        "void* __fastcall BuilderHook(\n",
        "ClientRepairResult RepairBuiltTerrainGuarded(\n"
        "    void* terrain,\n"
        "    const Token& key) noexcept {\n"
        "    ClientRepairResult result = ClientRepairResult::failed;\n"
        "    __try {\n"
        "        result = RepairBuiltTerrain(terrain, key);\n"
        "    } __except (EXCEPTION_EXECUTE_HANDLER) {\n"
        "        AbortTerrainBuild();\n"
        "    }\n"
        "    return result;\n"
        "}\n\n"
        "void* __fastcall BuilderHook(\n",
        "builder SEH helper insertion",
    )
    runtime_source = _replace_once(
        runtime_source,
        "    } else {\n"
        "        __try {\n"
        "            repair_result = RepairBuiltTerrain(*output_terrain, key);\n"
        "        } __except (EXCEPTION_EXECUTE_HANDLER) {\n"
        "            AbortTerrainBuild();\n"
        "            repair_result = ClientRepairResult::failed;\n"
        "        }\n"
        "    }\n",
        "    } else {\n"
        "        repair_result = RepairBuiltTerrainGuarded(*output_terrain, key);\n"
        "    }\n",
        "builder SEH call site",
    )
    runtime_source = _replace_once(
        runtime_source,
        "void RemoveInstalledHooksForFailedStart() noexcept {\n"
        "    if (g_builder_hook.installed) {\n"
        "        RemoveVtableHook(g_builder_hook);\n"
        "    }\n"
        "    g_original_builder = nullptr;\n\n"
        "    if (g_append_hook.installed) {\n"
        "        if (RemoveInlineHook(g_append_hook) == InlineHookResult::ok) {\n"
        "            SetMaterialAppendTrampoline(nullptr);\n"
        "        }\n"
        "    }\n"
        "    if (g_registration_hook.installed) {\n"
        "        if (RemoveInlineHook(g_registration_hook) == InlineHookResult::ok) {\n"
        "            SetMaterialRegistrationTrampoline(nullptr);\n"
        "        }\n"
        "    }\n"
        "}\n",
        "[[nodiscard]] bool RemoveInstalledHooksForFailedStart() noexcept {\n"
        "    bool clean = true;\n"
        "    if (g_builder_hook.installed) {\n"
        "        const auto result = RemoveVtableHook(g_builder_hook);\n"
        "        g_hook_result.store(result, std::memory_order_release);\n"
        "        clean = result == VtableHookResult::ok;\n"
        "    }\n\n"
        "    if (clean && g_append_hook.installed) {\n"
        "        if (RemoveInlineHook(g_append_hook) == InlineHookResult::ok) {\n"
        "            SetMaterialAppendTrampoline(nullptr);\n"
        "        } else {\n"
        "            clean = false;\n"
        "        }\n"
        "    }\n"
        "    if (clean && g_registration_hook.installed) {\n"
        "        if (RemoveInlineHook(g_registration_hook) == InlineHookResult::ok) {\n"
        "            SetMaterialRegistrationTrampoline(nullptr);\n"
        "        } else {\n"
        "            clean = false;\n"
        "        }\n"
        "    }\n"
        "    if (clean) {\n"
        "        g_original_builder = nullptr;\n"
        "    }\n"
        "    return clean;\n"
        "}\n",
        "failed-start hook cleanup",
    )
    runtime_source = _replace_once(
        runtime_source,
        "    if (inline_result != InlineHookResult::ok) {\n"
        "        RemoveInstalledHooksForFailedStart();\n"
        "        g_state.store(RuntimeState::hook_install_failed, std::memory_order_release);\n"
        "        return false;\n"
        "    }\n",
        "    if (inline_result != InlineHookResult::ok) {\n"
        "        const bool cleaned = RemoveInstalledHooksForFailedStart();\n"
        "        g_state.store(\n"
        "            cleaned ? RuntimeState::hook_install_failed\n"
        "                    : RuntimeState::shutdown_conflict,\n"
        "            std::memory_order_release);\n"
        "        return false;\n"
        "    }\n",
        "append-install cleanup call",
    )
    runtime_source = _replace_once(
        runtime_source,
        "    if (builder_result != VtableHookResult::ok) {\n"
        "        RemoveInstalledHooksForFailedStart();\n"
        "        g_state.store(RuntimeState::hook_install_failed, std::memory_order_release);\n"
        "        return false;\n"
        "    }\n",
        "    if (builder_result != VtableHookResult::ok) {\n"
        "        const bool cleaned = RemoveInstalledHooksForFailedStart();\n"
        "        g_state.store(\n"
        "            cleaned ? RuntimeState::hook_install_failed\n"
        "                    : RuntimeState::shutdown_conflict,\n"
        "            std::memory_order_release);\n"
        "        return false;\n"
        "    }\n",
        "builder-install cleanup call",
    )
    runtime_path.write_text(runtime_source, encoding="utf-8", newline="\n")


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
    v2.normalize_codegen_quality(repository)
    patch_native_compile_issues(repository)
    v2.patch_integration(repository)
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
