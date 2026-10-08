"""Package the tested native launcher without proprietary client assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True,
    ).strip()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing update package")
    payload = {"ShadowbaneLauncher.exe": args.launcher.read_bytes()}
    if payload["ShadowbaneLauncher.exe"][:2] != b"MZ":
        raise SystemExit("Launcher is not a Windows executable")
    for name in (
        "Play-ShadowbaneLocal.cmd", "Install-ShadowbaneLocal.cmd",
        "Install-ShadowbaneLocal.ps1", "README.txt",
    ):
        payload[name] = (repository / "scripts/client-friend-update" / name).read_bytes()
    manifest = {
        "schema_version": 1,
        "source_commit": source,
        "server": "100.87.213.55",
        "port": 6000,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()},
    }
    payload["package.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, data in payload.items():
            archive.writestr(name, data)
    print(json.dumps({
        "package": str(args.output),
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "source_commit": source,
        "launcher_sha256": manifest["files"]["ShadowbaneLauncher.exe"],
    }, indent=2))


if __name__ == "__main__":
    main()
