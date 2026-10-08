"""Generate the patcher's embedded baseline from the canonical client pins."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shadowbane_lab.client_extension.distribution import WONDERBANE_BASELINE  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
base = WONDERBANE_BASELINE
content = json.dumps({
    "profile": base.profile_id,
    "markers": [{"path": f.relative_path, "size": f.size, "sha256": f.sha256}
                for f in base.files_for("official")],
}, indent=2) + "\n"
args.output.parent.mkdir(parents=True, exist_ok=True)
if not args.output.exists() or args.output.read_text(encoding="utf-8") != content:
    args.output.write_text(content, encoding="utf-8", newline="\n")
