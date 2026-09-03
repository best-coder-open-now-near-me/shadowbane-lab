"""Request one opt-in renderer trace locally; no input, pixels, copies, or network."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import stat
import time
from collections.abc import Callable
from pathlib import Path

from shadowbane_lab.graphics_lab.control import (
    GraphicsControlTarget,
    discover_graphics_targets,
    target_process_is_alive,
    verify_target_identity,
)

TRACE_VERSION = "1.6.12"
MAX_TRACE_BYTES = 64 * 1024 * 1024


def _integer(payload: dict, key: str, minimum: int = 0) -> int:
    value = payload.get(key)
    if type(value) is not int or value < minimum:
        raise ValueError(f"invalid trace field: {key}")
    return value


def assess_trace(payload: object, target: GraphicsControlTarget, requested_qpc: int) -> dict:
    """Validate provenance and distinguish interval continuity from data coverage."""
    if not isinstance(payload, dict):
        raise ValueError("trace is not an object")
    expected = {
        "schema_version": 1,
        "extension_version": TRACE_VERSION,
        "process_id": target.process_id,
        "process_creation_filetime_utc": target.process_creation_filetime_utc,
        "executable_sha256": target.executable_sha256,
    }
    for key, value in expected.items():
        if type(payload.get(key)) is not type(value) or payload.get(key) != value:
            raise ValueError(f"trace identity/schema mismatch: {key}")
    if _integer(payload, "requested_qpc", 1) < requested_qpc:
        raise ValueError("trace predates this request")
    frequency = _integer(payload, "qpc_frequency", 1)
    sequence = _integer(payload, "sequence", 1)
    start = _integer(payload, "start_qpc")
    end = _integer(payload, "end_qpc", 1)
    if end < payload["requested_qpc"] or (start and not payload["requested_qpc"] <= start <= end):
        raise ValueError("trace timestamps are inconsistent")
    units = _integer(payload, "unit_count")
    retained = _integer(payload, "retained_submissions")
    observed = _integer(payload, "observed_submissions")
    skipped = {
        key: _integer(payload, key)
        for key in ("capacity_skipped", "unsafe_query_skipped", "query_budget_skipped")
    }
    draws = payload.get("draws")
    if (not isinstance(draws, list) or len(draws) != retained or retained > 8192
            or units > 4 or observed != retained + sum(skipped.values())):
        raise ValueError("trace record bounds/counts are inconsistent")
    limitations: list[str] = []
    for key, value in skipped.items():
        if value:
            limitations.append(f"{key}={value}")
    omitted = _integer(payload, "omitted_units")
    if omitted:
        limitations.append(f"omitted_units={omitted}")
    if payload.get("helpers_available") is not True:
        limitations.append("GL helpers unavailable")
    if retained == 0:
        limitations.append("no retained submissions")
    bindings: set[tuple[int, int]] = set()
    for ordinal, draw in enumerate(draws, 1):
        if not isinstance(draw, dict) or draw.get("ordinal") != ordinal:
            raise ValueError("trace draw order is inconsistent")
        textures = draw.get("textures")
        if not isinstance(textures, list) or len(textures) != units:
            raise ValueError("trace texture unit coverage is inconsistent")
        if draw.get("active_unit_restored") is not True:
            limitations.append(f"active texture unit restoration failed at {ordinal}")
        for unit, texture in enumerate(textures):
            if not isinstance(texture, dict) or texture.get("unit") != unit:
                raise ValueError("trace texture unit order is inconsistent")
            bindings.add((unit, _integer(texture, "binding")))
        # Null explicitly means a nonfinite input, not a zero/default transform.
        for name, size in (("state", 11), ("model_view", 16), ("projection", 16),
                           ("viewport", 4), ("color", 4), ("alpha_ref", 1)):
            values = draw.get(name)
            if not isinstance(values, list) or len(values) != size:
                raise ValueError(f"invalid draw {name}")
            if any(value is None for value in values):
                limitations.append(f"nonfinite {name} at {ordinal}")
            if any(value is not None and (type(value) not in (int, float)
                   or not math.isfinite(value)) for value in values):
                raise ValueError(f"invalid draw {name} number")
    interval = all(payload.get(key) is True for key in (
        "reviewed_interval_complete", "main_clear_seen", "done3d_seen"
    )) and all(payload.get(key) is False for key in (
        "extra_depth_clear", "context_or_thread_mismatch"
    ))
    if not interval:
        limitations.append("reviewed world interval incomplete")
    scope = payload.get("scope")
    if (not isinstance(scope, dict) or scope.get("pixels_read") is not False
            or scope.get("texture_bytes_read") is not False):
        raise ValueError("unexpected trace pixel/texture scope")
    return {
        "status": "captured_with_limits" if limitations else "captured",
        "sequence": sequence,
        "reviewed_interval_complete": interval,
        "retained_submissions": retained,
        "unique_unit_bindings": len(bindings),
        "observer_query_ms": _integer(payload, "query_ticks") * 1000 / frequency,
        "limitation_count": len(set(limitations)),
        "limitations": list(dict.fromkeys(limitations))[:20],
        "scope_note": "2D entry-state evidence; not cache IDs or a frame-time benchmark",
    }


def read_local_trace(path: Path) -> object:
    information = path.lstat()
    if (information.st_size > MAX_TRACE_BYTES or not stat.S_ISREG(information.st_mode)
            or getattr(information, "st_file_attributes", 0) & 0x400):
        raise ValueError("trace is oversized or not an ordinary file")
    return json.loads(path.read_text(encoding="utf-8"))


def wait_for_trace(
    target: GraphicsControlTarget,
    existing: set[Path],
    requested_qpc: int,
    timeout: float,
    *,
    alive: Callable[[GraphicsControlTarget], bool] = target_process_is_alive,
) -> tuple[Path, dict]:
    prefix = f"terrain-trace-{target.process_id}-{target.process_creation_filetime_utc}-"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not alive(target):
            raise RuntimeError("the selected client lifetime ended")
        candidates = set(target.status_path.parent.glob(f"{prefix}*.json")) - existing
        if len(candidates) > 1:
            raise RuntimeError("multiple new traces; refusing ambiguous attribution")
        if candidates:
            path = candidates.pop()
            return path, assess_trace(read_local_trace(path), target, requested_qpc)
        time.sleep(0.1)
    raise TimeoutError(
        "no complete local trace arrived; do not treat this as a successful capture. "
        "A pending/crashed request may require a normal client restart."
    )


def request_trace(target: GraphicsControlTarget, timeout: float = 30) -> tuple[Path, dict]:
    if os.name != "nt":
        raise RuntimeError("trace requests must run locally inside the Windows client VM")
    if not math.isfinite(timeout) or not 1 <= timeout <= 60:
        raise ValueError("timeout must be between 1 and 60 seconds")
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel.GetDriveTypeW.restype = wintypes.UINT
    directory = target.status_path.parent.absolute()
    if kernel.GetDriveTypeW(directory.anchor) != 3:
        raise ValueError("trace directory must be on a local fixed drive")
    for parent in (directory, *directory.parents):
        if getattr(parent.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError("trace directory contains a reparse point")
    status = json.loads(target.status_path.read_text(encoding="utf-8"))
    if (status.get("extension_version") != TRACE_VERSION
            or status.get("runtime_profile") != "full-renderer"
            or not verify_target_identity(target)):
        raise ValueError("client build/profile/lifetime is not the reviewed trace target")
    kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenEventW.restype = wintypes.HANDLE
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    for name in ("CloseHandle", "SetEvent", "ResetEvent", "ReleaseMutex"):
        function = getattr(kernel, name)
        function.argtypes = [wintypes.HANDLE]
        function.restype = wintypes.BOOL
    kernel.QueryPerformanceCounter.argtypes = [ctypes.POINTER(ctypes.c_longlong)]
    kernel.QueryPerformanceCounter.restype = wintypes.BOOL
    name = (f"Local\\WonderBaneTerrainTrace-{target.process_id}-"
            f"{target.process_creation_filetime_utc}")
    mutex = kernel.CreateMutexW(None, False, f"{name}-collector")
    event = idle = None
    locked = False
    try:
        mutex_wait = kernel.WaitForSingleObject(mutex, 0) if mutex else 0xFFFFFFFF
        locked = mutex_wait in (0, 0x80)  # WAIT_ABANDONED also transfers ownership.
        if mutex_wait != 0:
            raise RuntimeError("another or interrupted collector owns this client")
        event = kernel.OpenEventW(0x0002, False, name)
        idle = kernel.OpenEventW(0x100002, False, f"{name}-idle")
        if not event or not idle:
            raise RuntimeError("tracing is unavailable; launch the trace-enabled 1.6.12 package")
        if kernel.WaitForSingleObject(idle, 0) != 0:
            raise RuntimeError("a trace is pending; refusing a second request")
        existing = set(directory.glob("terrain-trace-*.json"))
        now = ctypes.c_longlong()
        if (not kernel.QueryPerformanceCounter(ctypes.byref(now))
                or not verify_target_identity(target)):
            raise RuntimeError("client identity changed before the trace request")
        if not kernel.ResetEvent(idle):
            raise OSError("could not reserve the trace channel")
        if not kernel.SetEvent(event):
            kernel.SetEvent(idle)
            raise OSError("could not signal the trace request")
        return wait_for_trace(target, existing, now.value, timeout)
    finally:
        for handle in (event, idle):
            if handle:
                kernel.CloseHandle(handle)
        if locked:
            kernel.ReleaseMutex(mutex)
        if mutex:
            kernel.CloseHandle(mutex)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--creation-filetime", type=int)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args(argv)
    try:
        targets = tuple(target for target in discover_graphics_targets()
                        if (args.pid is None or target.process_id == args.pid)
                        and (args.creation_filetime is None
                             or target.process_creation_filetime_utc == args.creation_filetime))
        if len(targets) != 1:
            raise ValueError(f"expected exactly one verified client; found {len(targets)}")
        path, result = request_trace(targets[0], args.timeout)
        print(json.dumps({"local_trace": str(path), **result}, indent=2, allow_nan=False))
        return 0 if result["status"] == "captured" else 2
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "not_captured", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
