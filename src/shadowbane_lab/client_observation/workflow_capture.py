"""Continuous read-only workflow evidence for one reviewed game-process lifetime.

Run this file with the installed host Python; no native extension update is needed.
Samples are sequential, not a transaction or a server receipt. Short-lived states
between polls can be missed. This module never acquires an action channel.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.client_observation.native_building_hirelings import (
    read_native_building_hirelings,
)
from shadowbane_lab.client_observation.native_guard_upgrade import read_native_guard_upgrade
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
from shadowbane_lab.client_observation.native_nearby_vendor_roster import (
    read_native_nearby_hirelings,
)
from shadowbane_lab.client_observation.native_structure_deposit import read_native_structure_deposit
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCompatibilityError,
)
from shadowbane_lab.client_observation.native_vendor_queue import _ReadSet
from shadowbane_lab.client_observation.native_vendor_roster import _text
from shadowbane_lab.client_observation.native_warehouse_withdrawal import (
    read_native_warehouse_withdrawal,
)
from shadowbane_lab.client_observation.reviewed_vendor_builds import REVIEWED_VENDOR_EXECUTABLES


def validate_identity(memory, process_id, creation):
    if (
        memory.pid != process_id or memory.process_creation_filetime_utc != creation
        or memory.executable_name.casefold() != "sb.exe" or memory.pointer_size != 4
        or memory.executable_sha256 not in REVIEWED_VENDOR_EXECUTABLES
    ):
        raise NativeVendorDialogCompatibilityError("workflow process identity/build mismatch")


def read_window_context(memory):
    """Retain ordered HUD identity even when strict semantic readers reject a menu.

    Only reviewed management HUD layouts supply controls. Unknown HUDs retain
    their address/class without interpreting their fields or collecting chat.
    Raw manager fields are diagnostic values, never command admission.
    """
    r, base = _ReadSet(memory), memory.base_address
    root = r.word(base + 0x16A7BFC)
    r.require(root, base + 0x1174884, "game window type")
    world_state = r.word(root + 0x64)
    result = {"root": root, "world_state": world_state, "huds": []}
    if world_state != 2:
        r.verify()
        return result
    manager = r.word(root + 0xA4)
    if manager and r.word(manager) == base + 0x1171ADC:
        result["asset_manager"] = {
            "address": manager,
            "raw": {name: r.word(manager + offset) for name, offset in (
                ("initialized", 0x48), ("hireling_initialized", 0x50),
                ("building_hud", 0x68), ("hireling_hud", 0x78),
                ("mode", 0xD0), ("offline", 0xD8),
                ("building_id", 0xF0), ("building_type", 0xF4),
                ("selection_id", 0xF8), ("selection_type", 0xFC),
                ("building_funds", 0x1CC), ("upgrade_cost", 0x274),
                ("upgrade_flags", 0x2AC), ("occupied", 0x37C), ("capacity", 0x380),
            )},
        }
    owners = {r.word(root + offset) for offset in (0x90, 0xA4, 0xD4)} - {0}
    for hud in r.hud_stack(root):
        kind = r.word(hud) - base
        entry = {"address": hud, "class_rva": kind}
        if kind == 0x116A058:
            entry["owner_address"] = r.word(hud + 0x104)
        if (kind in (0x1170308, 0x1168044)
                or (kind == 0x116A058 and entry["owner_address"] in owners)):
            controls = []
            for child in r.vector(hud + 0x54, 512):
                r.require(child + 0x3BC, hud, "workflow control owner")
                controls.append({
                    "address": child, "class_rva": r.word(child) - base,
                    "name": _text(r, child + 0x164),
                    "disabled_raw": r.word(child + 0x1A8),
                    "hidden_byte_raw": r.read(child + 0x304, 4)[1],
                })
            entry["controls"] = controls
        result["huds"].append(entry)
    r.verify()
    return result


READERS = {
    "windows": read_window_context,
    "nearby": read_native_nearby_hirelings,
    "building": read_native_building_hirelings,
    "guard": read_native_guard_upgrade,
    "withdrawal": read_native_warehouse_withdrawal,
    "deposit": read_native_structure_deposit,
}


def record_workflow(
    memory, output, stop_file, *, process_id, creation, duration=1800, interval=0.2,
    readers=None, clock=time.monotonic, sleep=time.sleep, alive=None, armed=None,
):
    """Flush changes and periodic health records until explicit stop or deadline.

    Per-channel failures are first-class observations, not empty successful menus.
    A dead process ends the session without attaching to a replacement process.
    """
    for value in (duration, interval):
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError("duration and interval must be finite positive numbers")
        if not math.isfinite(value) or value <= 0:
            raise ValueError("duration and interval must be finite positive numbers")
    if not 0.05 <= interval <= 10 or not interval <= duration <= 3600:
        raise ValueError("workflow capture bounds exceeded")
    validate_identity(memory, process_id, creation)
    output, stop_file = Path(output), Path(stop_file)
    if stop_file.exists() or output.resolve() == stop_file.resolve():
        raise ValueError("stop marker must be absent and distinct from output")
    readers = READERS if readers is None else readers
    if not readers:
        raise ValueError("at least one observation channel is required")
    alive = alive or (lambda: memory.read_block(memory.base_address, 2) == b"MZ")
    started, last_health = clock(), -math.inf
    sequence, samples = 0, 0
    previous, counts = {}, {name: {"observed": 0, "unavailable": 0} for name in readers}
    stop_reason = "error"
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        def emit(kind, **data):
            nonlocal sequence
            sequence += 1
            record = {
                "schema_version": 1, "record_type": kind, "sequence": sequence,
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "elapsed_seconds": clock() - started, **data,
            }
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()

        emit("session_start", process_id=process_id, process_creation_filetime_utc=creation,
             executable_sha256=memory.executable_sha256, interval_seconds=interval,
             duration_seconds=duration, channels=list(readers), read_only=True,
             capture_method="sequential_memory_polling", server_acceptance_verified=False,
             transient_states_may_be_missed=True)
        try:
            while True:
                if stop_file.exists():
                    stop_reason = "requested"
                    break
                if clock() - started >= duration:
                    stop_reason = "deadline"
                    break
                try:
                    if not alive():
                        stop_reason = "process_unavailable"
                        break
                except Exception as exc:
                    emit("process_unavailable", error_type=type(exc).__name__, detail=str(exc))
                    stop_reason = "process_unavailable"
                    break
                cycle_start = clock()
                samples += 1
                for name, reader in readers.items():
                    before = clock() - started
                    try:
                        value = {"state": "observed", "data": reader(memory)}
                    except Exception as exc:
                        value = {"state": "unavailable", "error_type": type(exc).__name__,
                                 "detail": str(exc)}
                    counts[name][value["state"]] += 1
                    encoded = json.dumps(value, sort_keys=True)
                    if previous.get(name) != encoded:
                        emit("channel_change", channel=name, sample=samples,
                             observation_started_seconds=before,
                             observation_finished_seconds=clock() - started, **value)
                        previous[name] = encoded
                if samples == 1:
                    emit("armed", sample=samples, counts=counts)
                    if armed:
                        armed()
                if clock() - last_health >= 5:
                    emit("health", sample=samples, counts=counts,
                         sample_duration_seconds=clock() - cycle_start)
                    last_health = clock()
                sleep(max(0, interval - (clock() - cycle_start)))
        except KeyboardInterrupt:
            stop_reason = "interrupted"
        finally:
            emit("session_end", reason=stop_reason, samples=samples, counts=counts,
                 workflow_completeness_verified=False)
    return {"reason": stop_reason, "samples": samples, "counts": counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-id", type=int, required=True)
    parser.add_argument("--creation", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=1800)
    parser.add_argument("--interval", type=float, default=0.2)
    args = parser.parse_args()
    memory = WindowsReadOnlyProcessMemory.open_for_process("sb.exe", args.process_id)
    try:
        result = record_workflow(
            memory, args.output, args.stop_file, process_id=args.process_id,
            creation=args.creation, duration=args.duration, interval=args.interval,
            armed=lambda: print("Workflow recorder armed.", flush=True),
        )
        print(json.dumps(result), flush=True)
        return 0 if result["reason"] in ("requested", "deadline", "interrupted") else 1
    finally:
        memory.close()


if __name__ == "__main__":
    raise SystemExit(main())
