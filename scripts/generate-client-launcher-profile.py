"""Generate native build pins from the canonical reviewed distribution profile."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shadowbane_lab.client_extension.distribution import WONDERBANE_BASELINE  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = WONDERBANE_BASELINE
    lines = ["#pragma once", "namespace shadowbane::desktop {",
             f"inline constexpr auto kProfile = {json.dumps(baseline.profile_id)};"]
    markers = (("Exe", baseline.official_executable), ("Objects", baseline.objects_cache))
    for prefix, record in markers:
        lines += [f"inline constexpr auto k{prefix}Path = L{json.dumps(record.relative_path)};",
                  f"inline constexpr unsigned long long k{prefix}Size = {record.size}ULL;",
                  f"inline constexpr auto k{prefix}Hash = {json.dumps(record.sha256)};"]
    lines += ["}", ""]
    content = "\n".join(lines)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.output.exists() or args.output.read_text(encoding="utf-8") != content:
        args.output.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
