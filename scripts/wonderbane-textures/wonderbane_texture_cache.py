#!/usr/bin/env python3
"""Plan, install, and exactly restore PNG replacements in a WonderBane texture cache."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _REPOSITORY_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from shadowbane_lab.client_extension.texture_cache import (  # noqa: E402
    TextureCacheError,
    apply_texture_cache_plan,
    build_texture_cache_plan,
    create_resource_backup,
    restore_resource_backup,
)


def replacement_argument(value: str) -> tuple[int, Path]:
    identifier, separator, filename = value.partition("=")
    if not separator or not identifier.strip() or not filename.strip():
        raise argparse.ArgumentTypeError("replacement must be RESOURCE_ID=PNG")
    try:
        resource_id = int(identifier, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid resource id {identifier!r}") from exc
    path = Path(filename).expanduser()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"replacement PNG does not exist: {path}")
    return resource_id, path


def public_plan(cache: Path, plan) -> dict[str, object]:
    return {
        "cache": str(cache.resolve()),
        "cache_size": plan.source_cache_size,
        "resource_count": plan.resource_count,
        "replacements": [
            {
                "group_id": write.group_id,
                "resource_id": write.resource_id,
                "index": write.entry_index,
                "dimensions": [write.width, write.height],
                "depth": write.channels,
                "png": write.artifact_path,
                "original_stored_size": write.original_stored_size,
                "replacement_stored_size": len(write.result_stored),
                "storage": "append" if write.append_required else "in-place",
                "original_payload_sha256": write.source_payload_sha256,
                "replacement_payload_sha256": write.result_payload_sha256,
            }
            for write in plan.writes
        ],
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("plan", "install"):
        command = commands.add_parser(name)
        command.add_argument("cache", type=Path)
        command.add_argument("replacements", nargs="+", type=replacement_argument)
        command.add_argument("--group-id", type=int, default=0)
        if name == "install":
            command.add_argument("--backup", type=Path, required=True)
            command.add_argument("--confirm-client-closed", action="store_true")
    restore_command = commands.add_parser("restore")
    restore_command.add_argument("backup", type=Path)
    restore_command.add_argument("--cache", type=Path)
    restore_command.add_argument("--confirm-client-closed", action="store_true")
    return result


def main(arguments: list[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    if args.command == "restore":
        if not args.confirm_client_closed:
            raise ValueError("restore requires --confirm-client-closed")
        cache = restore_resource_backup(args.backup, args.cache)
        print(
            json.dumps(
                {"restored": str(cache), "backup": str(args.backup.resolve())},
                indent=2,
            )
        )
        return 0

    cache = args.cache.resolve()
    if not cache.is_file():
        raise FileNotFoundError(cache)
    artifacts = {(args.group_id, resource_id): path for resource_id, path in args.replacements}
    if len(artifacts) != len(args.replacements):
        raise ValueError("each resource id may be replaced only once")
    plan = build_texture_cache_plan(cache, artifacts)
    output = public_plan(cache, plan)
    if args.command == "plan":
        print(json.dumps(output, indent=2))
        return 0
    if not args.confirm_client_closed:
        raise ValueError("install requires --confirm-client-closed")

    backup = args.backup.resolve()
    create_resource_backup(cache, backup, plan)
    try:
        apply_texture_cache_plan(cache, plan)
    except Exception:
        restore_resource_backup(backup, cache)
        raise
    output["installed"] = True
    output["backup"] = str(backup)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TextureCacheError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
