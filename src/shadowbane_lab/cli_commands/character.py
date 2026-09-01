"""Character capture command implementations."""

from __future__ import annotations

import json
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
    WindowSnapshot,
)

from .common import _error


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
                encodings=(tuple(encodings) if encodings else ("cp1252", "utf-8", "utf-16le")),
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
        character = payload.get("character")
        identity = character.get("identity") if isinstance(character, dict) else None
        if isinstance(identity, dict) and identity.get("name"):
            print(f"Character: {identity['name']}")
        print(f"Warnings: {len(payload['warnings'])}")
    return 0


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
        "executable_path": snapshot.executable_path,
    }
