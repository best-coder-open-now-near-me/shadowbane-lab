from __future__ import annotations

import argparse
from pathlib import Path

import terrain_delivery_finalize as base
import terrain_delivery_finalize_v2 as v2


_PATCH_DLLMAIN = r'''def patch_dllmain(native: Path) -> None:
    candidates = _dllmain_candidates(native)
    if len(candidates) != 1:
        raise RuntimeError(f"expected one DllMain source, found {candidates!r}")
    path = candidates[0]
    text = path.read_text(encoding="utf-8")
    if "QueueTerrainMaterialRepairStartup" in text:
        return

    signature = re.search(
        r"DllMain\s*\(\s*(?:const\s+)?(?:HINSTANCE|HMODULE)\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)",
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
'''


def patch_integration(repository: Path) -> None:
    v2.patch_integration(repository)
    path = repository / "tools" / "integrate_terrain_material_repair.py"
    source = path.read_text(encoding="utf-8")
    source = v2._replace_function(
        source,
        "patch_dllmain",
        _PATCH_DLLMAIN,
        "remove_one_shot_workflows",
    )
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
