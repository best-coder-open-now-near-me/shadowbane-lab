"""Portable console entry point for name-based Shadowbane location lookup."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from shadowbane_lab.location_lookup import main as location_lookup_main
from shadowbane_vanilla_diagnostics.discovery import WindowsProcessDiscovery
from shadowbane_vanilla_diagnostics.model import ProcessIdentity
from shadowbane_vanilla_diagnostics.package import verify_package


def _package_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve(strict=True).parent
    return Path(__file__).resolve(strict=True).parents[1]


def resolve_world_definition(
    explicit: Path | None,
    identities: Sequence[ProcessIdentity],
) -> Path:
    """Resolve WorldDef.cfg from an explicit path or exactly one running client."""

    if explicit is not None:
        candidate = explicit.resolve(strict=True)
        if not candidate.is_file():
            raise ValueError(f"WorldDef.cfg is not a file: {candidate}")
        return candidate
    if not identities:
        raise ValueError(
            "No running sb.exe was found. Start Shadowbane, or pass --world-def explicitly."
        )
    if len(identities) != 1:
        process_ids = ", ".join(str(identity.process_id) for identity in identities)
        raise ValueError(
            f"Multiple sb.exe processes were found ({process_ids}). "
            "Close extras, or pass --world-def explicitly."
        )
    candidate = Path(identities[0].executable_path).parent / "Config" / "WorldDef.cfg"
    if not candidate.is_file():
        raise ValueError(f"WorldDef.cfg was not found beside the running client: {candidate}")
    return candidate.resolve(strict=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Look up Shadowbane map locations by name from the running client's WorldDef."
    )
    parser.add_argument("--world-def", type=Path)
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--no-overrides", action="store_true")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--query")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-test-result", type=Path, help=argparse.SUPPRESS)
    return parser


def _run_self_test(package_root: Path, result_path: Path | None) -> int:
    if result_path is None:
        raise ValueError("--self-test requires --self-test-result")
    payload: dict[str, object]
    try:
        package = verify_package(package_root)
        override_path = package_root / "Location Data" / "wonderbane-named-destinations.json"
        override_payload = json.loads(override_path.read_text(encoding="utf-8"))
        payload = {
            "ok": (
                override_payload.get("schema_version") == 1
                and isinstance(override_payload.get("destinations"), list)
            ),
            "package_id": package["package_id"],
            "package_version": package["package_version"],
            "source_revision": package["source_revision"],
            "override_path": str(override_path),
        }
    except Exception as exc:
        payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if payload["ok"] else 2


def main(arguments: Sequence[str] | None = None) -> int:
    source_arguments = list(sys.argv[1:] if arguments is None else arguments)
    launched_interactively = not source_arguments
    options = _parser().parse_args(source_arguments)
    package_root = _package_root()
    try:
        if options.self_test:
            return _run_self_test(package_root, options.self_test_result)
        identities = WindowsProcessDiscovery().find("sb.exe")
        world_def = resolve_world_definition(options.world_def, identities)
        forwarded = ["--world-def", str(world_def), "--limit", str(options.limit)]
        if options.query:
            forwarded.extend(("--query", options.query))
        if options.json:
            forwarded.append("--json")
        if not options.no_overrides:
            overrides = options.overrides or (
                package_root / "Location Data" / "wonderbane-named-destinations.json"
            )
            if overrides.is_file():
                forwarded.extend(("--overrides", str(overrides)))
            elif options.overrides is not None:
                raise ValueError(f"Location overrides were not found: {overrides}")
        return location_lookup_main(forwarded)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        if launched_interactively:
            input("Press Enter to close.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
