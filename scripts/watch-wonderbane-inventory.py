"""Passive player-owned inventory observations; no packet or grant-cause claims."""
from __future__ import annotations

import argparse
import json
import struct
import time
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.client_observation.native_character_config import NativeCharacterConfigReader
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory

# Census-only layouts shared with native/wonderbane_extension/actor_inventory_native.cpp.
PREPARED_14 = "78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903"
CLASSES = {
    0x1142188: "ArcContainerObject", 0x1142468: "ArcDeed", 0x1142748: "ArcItem",
    0x1143278: "ArcRune", 0x1144154: "ArcKey",
}


def inventory_snapshot(memory, expected_key):
    """Read both actor containers, rechecking every dependency before publishing.

    External reads cannot lock native objects or prove wire ordering/ABA absence.
    Quantity is decoded only for the reviewed exact ArcItem class.
    """
    if memory.executable_sha256 != PREPARED_14 or memory.pointer_size != 4:
        raise ValueError("inventory census requires reviewed prepared 1.3.38.14")
    blocks = {}
    base = memory.base_address

    def read(at, count=1):
        if at % 4 or not 0x10000 <= at < 0x7FFF0000 or at + count * 4 > 0x7FFF0000:
            raise ValueError("invalid inventory pointer")
        if len(blocks) >= 12000:
            raise ValueError("inventory read budget exceeded")
        raw = memory.read_block(at, count * 4)
        if len(raw) != count * 4:
            raise ValueError("short inventory read")
        key = at, count * 4
        if key in blocks and blocks[key] != raw:
            raise ValueError("inventory changed during observation")
        blocks[key] = raw
        return struct.unpack("<" + "I" * count, raw)

    def require(at, expected):
        if read(at)[0] != expected:
            raise ValueError("inventory ownership/type mismatch")

    actor = read(base + 0x16A2D98)[0]
    require(actor, base + 0x114165C)
    require(actor + 8, base + 0x11417D4)
    if read(actor + 0x18, 2) != tuple(expected_key):
        raise ValueError("inventory actor identity mismatch")
    seen_nodes, seen_keys, items = set(), set(), []

    def walk(at, parent, head, low, high, depth, container):
        if not at:
            return []
        if at == head or at in seen_nodes or depth > 64 or len(seen_nodes) >= 512:
            raise ValueError("invalid or excessive inventory tree")
        seen_nodes.add(at)
        owner, left, right, item_id, item_type, item = read(at + 4, 6)
        key = item_id, item_type
        order = item_type, item_id
        if (owner not in ((parent,) if parent else (0, head)) or not all(key)
                or key in seen_keys or (low is not None and order <= low)
                or (high is not None and order >= high)):
            raise ValueError("invalid inventory tree ownership or key ordering")
        seen_keys.add(key)
        table = read(item)[0] - base
        if table not in CLASSES or read(item + 0x18, 2) != key:
            raise ValueError("unreviewed inventory item or mismatched identity")
        template = read(item + 0x10, 2)
        if not template[0] or template[1]:
            raise ValueError("invalid inventory template")
        items.append({
            "item_key": list(key), "template_key": list(template),
            "class": CLASSES[table], "container_offset": container,
            "quantity_raw": read(item + 0x744)[0] if table == 0x1142748 else None,
        })
        before = walk(left, at, head, low, order, depth + 1, container)
        after = walk(right, at, head, order, high, depth + 1, container)
        return before + [at] + after

    for offset, table in ((0x688, 0x11415E4), (0x6F0, 0x11415CC)):
        require(actor + offset, base + table)
        head = read(actor + offset + 0x44)[0]
        root, first, last = read(head + 4, 3)
        nodes = walk(root, 0, head, None, None, 0, offset)
        if (first, last) != ((nodes[0], nodes[-1]) if nodes else (head, head)):
            raise ValueError("inventory tree endpoints mismatch")
    for (at, size), expected in reversed(tuple(blocks.items())):
        if memory.read_block(at, size) != expected:
            raise ValueError("inventory changed during observation")
    return sorted(items, key=lambda item: item["item_key"])


def inventory_delta(previous, current):
    if previous is None:
        return {"kind": "initial_inventory", "items": current}
    old = {tuple(item["item_key"]): item for item in previous}
    new = {tuple(item["item_key"]): item for item in current}
    delta = {
        "kind": "inventory_change",
        "first_observed": [new[k] for k in sorted(new.keys() - old.keys())],
        "no_longer_observed": [old[k] for k in sorted(old.keys() - new.keys())],
        "changed": [{"before": old[k], "after": new[k]}
                    for k in sorted(old.keys() & new.keys()) if old[k] != new[k]],
    }
    changed = any(delta[k] for k in ("first_observed", "no_longer_observed", "changed"))
    return delta if changed else None


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    # Shared-folder readers can briefly hold a Windows rename-denying handle.
    # The append-only journal is authoritative; a busy summary waits for next sample.
    for _attempt in range(10):
        try:
            temporary.replace(path)
            return True
        except PermissionError:
            time.sleep(0.05)
    return False


def collect(pid, output, *, seconds=7200, interval=0.5):
    output.mkdir(parents=True, exist_ok=False)
    process = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", pid)
    try:
        reader = NativeCharacterConfigReader(process)
        if process.executable_sha256 != PREPARED_14:
            raise ValueError("unreviewed inventory client")
        binding, previous, last_error = None, None, None
        status = {
            "schema_version": 1, "status": "waiting_for_character", "samples": 0,
            "written_records": 0, "suppressed_samples": 0, "errors": 0,
            "pid": pid, "creation_filetime": process.process_creation_filetime_utc,
            "client_sha256": process.executable_sha256,
            "evidence": "polled_native_actor_inventory; not packets or server grant receipts",
        }
        started = time.monotonic()
        with (output / "inventory.jsonl").open("x", encoding="utf-8") as journal:
            while time.monotonic() - started < seconds:
                if (output / "STOP").exists():
                    status["stop_reason"] = "requested"
                    break
                if journal.tell() >= 8 * 1024 * 1024:
                    status["stop_reason"] = "byte_limit"
                    break
                status["samples"] += 1
                at = datetime.now(UTC).isoformat()
                event = None
                try:
                    identity = reader.observe()
                    key = reader.observe_local_key()
                    current = (identity.character_name, identity.server_name,
                               key.object_type, key.object_uuid)
                    if current[1].casefold() != "wonderbane":
                        raise ValueError("waiting for Wonderbane character")
                    if binding is not None and binding != current:
                        status["stop_reason"] = "character_changed"
                        break
                    snapshot = inventory_snapshot(process, current[2:])
                    if reader.observe() != identity or reader.observe_local_key() != key:
                        raise ValueError("character changed during inventory sample")
                    binding = current
                    event = inventory_delta(previous, snapshot)
                    if last_error is not None:
                        event = {"kind": "observation_recovered", "delta": event}
                    previous, last_error = snapshot, None
                    status.update(status="recording", character=list(binding), items=len(snapshot))
                    write_json(output / "latest-inventory.json", {
                        "at": at, "character": list(binding), "items": snapshot,
                        "scope": "two_native_actor_containers", "server_completeness": "unproved",
                    })
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    status["errors"] += 1
                    status["status"] = "waiting_for_character" if binding is None else "unavailable"
                    if error != last_error:
                        event = {"kind": "observation_unavailable", "error": error}
                    last_error = error
                if event is not None:
                    status["written_records"] += 1
                    journal.write(json.dumps({"at": at, "sample": status["samples"],
                                              "character": binding, **event}) + "\n")
                    journal.flush()
                else:
                    status["suppressed_samples"] += 1
                status["last_sample_at"] = at
                write_json(output / "status.json", status)
                time.sleep(interval)
        status.update(status="stopped", finished_at=datetime.now(UTC).isoformat())
        status.setdefault("stop_reason", "duration")
        write_json(output / "status.json", status)
    finally:
        process.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    collect(args.pid, args.output)
