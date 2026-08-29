"""Command-line diagnostics used by the WonderBane VM bootstrap."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from shadowbane_lab.character_capture import (
    CharacterCaptureError,
    CharacterLayoutError,
    MemoryAccessError,
    ProcessSelectionError,
    WindowsProcessMemory,
    capture_character,
    load_character_layout,
)
from shadowbane_lab.client_input import (
    CalibrationLoadError,
    WindowsForegroundWindowInspector,
    WindowSnapshot,
    load_calibration,
)


def _integer_argument(value: str) -> int:
    try:
        parsed = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer or 0x-prefixed value") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must not be negative")
    return parsed


def _add_process_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pid", type=int, help="target one client when multiple are open")
    parser.add_argument(
        "--process",
        action="append",
        dest="process_names",
        help="allowed executable name; may be repeated (default: Shadowbane.exe)",
    )


def _add_scan_arguments(parser: argparse.ArgumentParser) -> None:
    _add_process_arguments(parser)
    parser.add_argument("--max-matches", type=int, default=50)
    parser.add_argument("--max-scan-mib", type=int, default=256)
    parser.add_argument("--context-bytes", type=int, default=32)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shadowbane-lab")
    commands = parser.add_subparsers(dest="command", required=True)
    client = commands.add_parser("client", help="inspect and validate client integration")
    client_commands = client.add_subparsers(dest="client_command", required=True)

    inspect = client_commands.add_parser(
        "inspect",
        help="read the current foreground Win32 client without sending input",
    )
    inspect.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    validate = client_commands.add_parser(
        "validate-profile",
        help="strictly load a client calibration profile",
    )
    validate.add_argument("profile", type=Path)
    validate.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    character = commands.add_parser(
        "character",
        help="discover and capture read-only WonderBane character state",
    )
    character_commands = character.add_subparsers(dest="character_command", required=True)

    validate_layout = character_commands.add_parser(
        "validate-layout",
        help="strictly validate a process-memory character layout",
    )
    validate_layout.add_argument("layout", type=Path)
    validate_layout.add_argument("--json", action="store_true")

    inspect_process = character_commands.add_parser(
        "inspect-process",
        help="pin the running client PID, executable hash, pointer size, and modules",
    )
    _add_process_arguments(inspect_process)
    inspect_process.add_argument("--json", action="store_true")

    scan_text = character_commands.add_parser(
        "scan-text",
        help="scan readable pages for a character or item name without dumping memory",
    )
    scan_text.add_argument("text")
    scan_text.add_argument(
        "--encoding",
        action="append",
        dest="encodings",
        help="text encoding; may be repeated (defaults: cp1252, utf-8, utf-16le)",
    )
    _add_scan_arguments(scan_text)

    scan_pointer = character_commands.add_parser(
        "scan-pointer",
        help="find read-only pointer references to a candidate address",
    )
    scan_pointer.add_argument("address", type=_integer_argument)
    _add_scan_arguments(scan_pointer)

    snapshot = character_commands.add_parser(
        "snapshot",
        help="capture declared character fields from a hash-pinned layout",
    )
    snapshot.add_argument("layout", type=Path)
    snapshot.add_argument("--output", type=Path)
    snapshot.add_argument("--pid", type=int)
    snapshot.add_argument("--json", action="store_true")
    return parser


def _snapshot_payload(snapshot: WindowSnapshot) -> dict[str, object]:
    bounds = snapshot.client_bounds
    return {
        "ok": True,
        "executable_name": snapshot.executable_name,
        "title": snapshot.title,
        "client_bounds": {
            "left": bounds.left,
            "top": bounds.top,
            "width": bounds.width,
            "height": bounds.height,
        },
        "dpi_scale": snapshot.dpi_scale,
        "is_foreground": snapshot.is_foreground,
        "is_visible": snapshot.is_visible,
    }


def _inspect_client(*, as_json: bool) -> int:
    try:
        snapshot = WindowsForegroundWindowInspector().inspect()
    except (OSError, RuntimeError) as exc:
        return _error(f"client inspection failed: {exc}", as_json=as_json)
    if snapshot is None:
        return _error(
            "no foreground window could be inspected; focus WonderBane and try again",
            as_json=as_json,
        )
    payload = _snapshot_payload(snapshot)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Executable: {payload['executable_name']}")
        print(f"Title: {payload['title']}")
        bounds = payload["client_bounds"]
        assert isinstance(bounds, dict)
        print(
            "Client bounds: "
            f"left={bounds['left']} top={bounds['top']} "
            f"width={bounds['width']} height={bounds['height']}"
        )
        print(f"DPI scale: {payload['dpi_scale']}")
    return 0


def _validate_profile(path: Path, *, as_json: bool) -> int:
    try:
        profile = load_calibration(path)
    except (CalibrationLoadError, OSError) as exc:
        return _error(f"profile validation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "profile_id": profile.profile_id,
        "schema_version": profile.schema_version,
        "live_input_enabled": profile.live_input_enabled,
        "action_count": len(profile.actions),
        "movement_action_key": profile.movement.action_key,
        "executable_names": list(profile.target.executable_names),
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Profile: {profile.profile_id}")
        print(f"Schema version: {profile.schema_version}")
        print(f"Mapped actions: {len(profile.actions)}")
        print(f"Live input enabled: {profile.live_input_enabled}")
    return 0


def _validate_character_layout(path: Path, *, as_json: bool) -> int:
    try:
        layout = load_character_layout(path)
    except (CharacterLayoutError, OSError) as exc:
        return _error(f"character layout validation failed: {exc}", as_json=as_json)
    payload = {
        "ok": True,
        "layout_id": layout.layout_id,
        "schema_version": layout.schema_version,
        "live_capture_enabled": layout.target.live_capture_enabled,
        "expected_sha256": layout.target.expected_sha256,
        "pointer_size": layout.target.pointer_size,
        "executable_names": list(layout.target.executable_names),
        "root_count": len(layout.roots),
        "value_count": len(layout.values),
        "record_count": len(layout.records),
        "collection_count": len(layout.collections),
    }
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Layout: {layout.layout_id}")
        print(f"Pointer size: {layout.target.pointer_size}")
        print(f"Live capture enabled: {layout.target.live_capture_enabled}")
        print(
            "Declarations: "
            f"{len(layout.roots)} roots, {len(layout.values)} values, "
            f"{len(layout.records)} records, {len(layout.collections)} collections"
        )
    return 0


def _process_names(values: list[str] | None) -> tuple[str, ...]:
    return tuple(values) if values else ("Shadowbane.exe",)


def _inspect_character_process(
    *, process_names: list[str] | None, process_id: int | None, as_json: bool
) -> int:
    try:
        with WindowsProcessMemory.open(
            executable_names=_process_names(process_names), process_id=process_id
        ) as memory:
            payload = {
                "ok": True,
                "process": memory.process_info.as_dict(),
                "modules": [item.as_dict() for item in memory.modules()],
            }
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"character process inspection failed: {exc}", as_json=as_json)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        process = payload["process"]
        assert isinstance(process, dict)
        print(f"PID: {process['process_id']}")
        print(f"Executable: {process['executable_path']}")
        print(f"SHA-256: {process['executable_sha256']}")
        print(f"Pointer size: {process['pointer_size']}")
        print(f"Loaded modules: {len(payload['modules'])}")
    return 0


def _scan_character_text(
    *,
    text: str,
    encodings: list[str] | None,
    process_names: list[str] | None,
    process_id: int | None,
    max_matches: int,
    max_scan_mib: int,
    context_bytes: int,
    as_json: bool,
) -> int:
    try:
        with WindowsProcessMemory.open(
            executable_names=_process_names(process_names), process_id=process_id
        ) as memory:
            matches = memory.scan_text(
                text,
                encodings=tuple(encodings) if encodings else ("cp1252", "utf-8", "utf-16le"),
                max_matches=max_matches,
                max_scan_bytes=max_scan_mib * 1024 * 1024,
                context_bytes=context_bytes,
            )
            payload = {
                "ok": True,
                "process": memory.process_info.as_dict(),
                "query": text,
                "matches": [item.as_dict() for item in matches],
            }
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"character text scan failed: {exc}", as_json=as_json)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Matches: {len(matches)}")
        for match in matches:
            print(f"0x{match.address:x} [{match.encoding}] {match.preview_text}")
    return 0


def _scan_character_pointer(
    *,
    address: int,
    process_names: list[str] | None,
    process_id: int | None,
    max_matches: int,
    max_scan_mib: int,
    context_bytes: int,
    as_json: bool,
) -> int:
    try:
        with WindowsProcessMemory.open(
            executable_names=_process_names(process_names), process_id=process_id
        ) as memory:
            matches = memory.scan_pointer(
                address,
                max_matches=max_matches,
                max_scan_bytes=max_scan_mib * 1024 * 1024,
                context_bytes=context_bytes,
            )
            payload = {
                "ok": True,
                "process": memory.process_info.as_dict(),
                "query_address": f"0x{address:x}",
                "matches": [item.as_dict() for item in matches],
            }
    except (OSError, RuntimeError, ValueError) as exc:
        return _error(f"character pointer scan failed: {exc}", as_json=as_json)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Pointer references to 0x{address:x}: {len(matches)}")
        for match in matches:
            print(f"0x{match.address:x} {match.preview_text}")
    return 0


def _capture_character_snapshot(
    *, layout_path: Path, output_path: Path | None, process_id: int | None, as_json: bool
) -> int:
    try:
        layout = load_character_layout(layout_path)
        with WindowsProcessMemory.open(
            executable_names=layout.target.executable_names,
            process_id=process_id,
            expected_sha256=layout.target.expected_sha256,
            required_pointer_size=layout.target.pointer_size,
        ) as memory:
            capture = capture_character(layout, memory)
        payload = capture.as_dict()
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(encoded, encoding="utf-8")
    except (
        CharacterCaptureError,
        CharacterLayoutError,
        MemoryAccessError,
        ProcessSelectionError,
        OSError,
        ValueError,
    ) as exc:
        return _error(f"character snapshot failed: {exc}", as_json=as_json)

    if as_json or output_path is None:
        print(encoded, end="")
    else:
        print(f"Character snapshot: {output_path}")
        identity = payload.get("character", {}).get("identity", {})
        if isinstance(identity, dict) and identity.get("name"):
            print(f"Character: {identity['name']}")
        print(f"Warnings: {len(payload['warnings'])}")
    return 0


def _error(message: str, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    else:
        print(message, file=sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "client" and arguments.client_command == "inspect":
        return _inspect_client(as_json=arguments.json)
    if arguments.command == "client" and arguments.client_command == "validate-profile":
        return _validate_profile(arguments.profile, as_json=arguments.json)
    if arguments.command == "character" and arguments.character_command == "validate-layout":
        return _validate_character_layout(arguments.layout, as_json=arguments.json)
    if arguments.command == "character" and arguments.character_command == "inspect-process":
        return _inspect_character_process(
            process_names=arguments.process_names,
            process_id=arguments.pid,
            as_json=arguments.json,
        )
    if arguments.command == "character" and arguments.character_command == "scan-text":
        return _scan_character_text(
            text=arguments.text,
            encodings=arguments.encodings,
            process_names=arguments.process_names,
            process_id=arguments.pid,
            max_matches=arguments.max_matches,
            max_scan_mib=arguments.max_scan_mib,
            context_bytes=arguments.context_bytes,
            as_json=arguments.json,
        )
    if arguments.command == "character" and arguments.character_command == "scan-pointer":
        return _scan_character_pointer(
            address=arguments.address,
            process_names=arguments.process_names,
            process_id=arguments.pid,
            max_matches=arguments.max_matches,
            max_scan_mib=arguments.max_scan_mib,
            context_bytes=arguments.context_bytes,
            as_json=arguments.json,
        )
    if arguments.command == "character" and arguments.character_command == "snapshot":
        return _capture_character_snapshot(
            layout_path=arguments.layout,
            output_path=arguments.output,
            process_id=arguments.pid,
            as_json=arguments.json,
        )
    raise RuntimeError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())
