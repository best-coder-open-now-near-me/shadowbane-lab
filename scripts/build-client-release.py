"""Build a complete pinned client release from verified official files."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

REPOSITORY = "https://github.com/best-coder-open-now-near-me/shadowbane-lab"
BASELINE_HASH = "22e083d1ef09aa94ced7380cc7e2bf994e69b3a3d8450f319c8f19c4dabbb95c"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def personal(path: str) -> bool:
    lower = path.lower()
    return lower.startswith("config/") and lower.endswith(".cfg") or lower.startswith("doublefusion/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--client-root", type=Path, required=True)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--patcher", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    if sha256(args.baseline) != BASELINE_HASH:
        raise SystemExit("Official baseline manifest differs from the reviewed release")
    if args.output.exists():
        raise SystemExit("Choose a fresh output directory; existing releases are never overwritten")
    baseline = json.loads(args.baseline.read_bytes())
    root = args.client_root.resolve()
    files = []
    sources = {}
    for record in baseline["files"]:
        relative = record["path"]
        source = (root / relative).resolve()
        if not source.is_relative_to(root) or source.is_symlink():
            raise SystemExit("Unsafe client path")
        if source.stat().st_size != record["size"] or sha256(source) != record["sha256"]:
            raise SystemExit("Pinned client file differs: " + relative)
        sources[relative] = source
        files.append({**record, "policy": "seed" if personal(relative) else "replace"})
    for relative, source, policy in [
        ("ShadowbaneLauncher.exe", args.launcher, "replace"),
    ]:
        sources[relative] = source
        files.append({"path": relative, "size": source.stat().st_size, "sha256": sha256(source), "policy": policy})
    # A new client has no generated preferences yet. Existing preferences are never replaced.
    preferences = b"RESOLUTION= 800 600\r\nFULLSCREEN= FALSE\r\nREFRESH= 60\r\nVIDEOSETTINGSVALIDATION= 800x600@60Hz\r\n"
    relative = "Config/ArcanePref.cfg"
    files.append({"path": relative, "size": len(preferences), "sha256": hashlib.sha256(preferences).hexdigest(), "policy": "seed"})
    args.output.mkdir(parents=True)
    groups = []
    group = []
    size = 0
    for record in files:
        if group and size + record["size"] > 128 * 1024 * 1024:
            groups.append(group)
            group, size = [], 0
        group.append(record)
        size += record["size"]
    if group:
        groups.append(group)
    bundles = []
    prefix = REPOSITORY + "/releases/download/" + args.tag + "/"
    for index, group in enumerate(groups, 1):
        name = "client-{0:03}.zip".format(index)
        target = args.output / name
        print("Packing " + name + " (" + str(len(group)) + " files)", flush=True)
        with zipfile.ZipFile(target, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for record in group:
                relative = record["path"]
                if relative == "Config/ArcanePref.cfg":
                    archive.writestr(relative, preferences)
                else:
                    archive.write(sources[relative], relative)
                record["bundle"] = name
        if target.stat().st_size >= 2 * 1024**3:
            raise SystemExit("Bundle exceeds GitHub asset limit")
        bundles.append({"name": name, "url": prefix + name, "size": target.stat().st_size, "sha256": sha256(target)})
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    manifest = {
        "schema_version": 1, "minimum_patcher": 1, "version": args.version,
        "server": "100.87.213.55", "port": 6000, "source_commit": source_commit,
        "official_baseline_sha256": BASELINE_HASH, "official_file_count": len(baseline["files"]),
        "bundles": bundles, "files": files,
    }
    manifest_path = args.output / "client-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    channel = {
        "schema_version": 1, "version": args.version,
        "manifest_url": prefix + "client-manifest.json",
        "manifest_sha256": sha256(manifest_path),
    }
    (args.output / "channel.json").write_text(json.dumps(channel, indent=2) + "\n", encoding="utf-8", newline="\n")
    shutil.copyfile(args.patcher, args.output / "ShadowbanePatcher.exe")
    hashes = {p.name: sha256(p) for p in args.output.iterdir() if p.is_file()}
    (args.output / "SHA256SUMS.txt").write_text("".join(digest + "  " + name + "\n" for name, digest in sorted(hashes.items())), encoding="ascii")
    print(json.dumps({"version": args.version, "official_files": len(baseline["files"]),
        "managed_files": len(files), "bundles": len(bundles),
        "download_bytes": sum(b["size"] for b in bundles), "channel": channel}, indent=2))


if __name__ == "__main__":
    main()
