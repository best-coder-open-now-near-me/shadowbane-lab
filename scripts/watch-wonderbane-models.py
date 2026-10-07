"""Passive, bounded client-model evidence collector. No client writes or input."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterPopulationReader,
    load_bundled_native_character_population_profile,
)
from shadowbane_lab.client_observation.native_zone import (
    NativeCurrentZoneReader,
    load_bundled_native_zone_profile,
)
from shadowbane_lab.world_data.cache import CacheArchive
from shadowbane_lab.world_data.object_navigation import parse_object_navigation_metadata


def utc_now():
    return datetime.now(UTC).isoformat()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def project_population(observation):
    # A key is a native field pair, not a proven server UUID or mesh/template ID.
    return {
        "local_player_object_key": (
            asdict(observation.local_player_object_key)
            if observation.local_player_object_key
            else None
        ),
        "rejected_candidates": observation.rejected_candidates,
        "characters": [
            {
                "object_key": asdict(c.object_key) if c.object_key else None,
                "kind": c.character_kind.value,
                "roles": list(c.protected_roles),
                "owner_object_key": asdict(c.owner_object_key) if c.owner_object_key else None,
                "health": [c.current_health, c.maximum_health],
                "position": [c.lt, c.lg, c.altitude],
            }
            for c in observation.characters
        ],
    }


def cache_inventory(cache_dir, output_dir):
    """Index shipped definitions, without exporting asset payloads."""
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"Client cache directory missing: {cache_dir}")
    summaries = []
    with (output_dir / "cache-resources.jsonl").open("x", encoding="utf-8") as records:
        for path in sorted(cache_dir.glob("*.cache")):
            before = path.stat()
            summary = {"archive": path.name, "size": before.st_size}
            try:
                with path.open("rb") as stream:
                    summary["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
                types = Counter()
                with CacheArchive(path) as archive:
                    summary["resource_count"] = len(archive.entries)
                    errors = 0
                    for entry in archive.entries:
                        row = {"archive": path.name, **asdict(entry)}
                        if path.name.casefold() == "cobjects.cache":
                            try:
                                model = parse_object_navigation_metadata(
                                    archive.read_resource(entry)
                                )
                                row["object_prefix"] = asdict(model)
                                types[str(model.object_type)] += 1
                            except ValueError as exc:
                                errors += 1
                                row["parse_error"] = str(exc)
                        records.write(json.dumps(row, sort_keys=True) + "\n")
                    summary["object_type_counts"] = dict(types)
                    summary["object_prefix_errors"] = errors
                after = path.stat()
                summary["stable_file"] = (
                    before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns
                )
            except (OSError, ValueError) as exc:
                summary["error"] = str(exc)
            summaries.append(summary)
    write_json(
        output_dir / "cache-summary.json",
        {
            "archives": summaries,
            "scope": "Shipped resource catalog, not proof of live use or server compatibility.",
        },
    )


def collect(output_dir, process_id=None, *, seconds=7200, interval=2.0, max_bytes=64 * 1024**2):
    output_dir.mkdir(parents=True, exist_ok=False)
    state = {
        "schema_version": 1,
        "started_at": utc_now(),
        "status": "starting",
        "samples": 0,
        "errors": 0,
        "bytes": 0,
    }
    write_json(output_dir / "status.json", state)
    process = None
    try:
        process = (
            WindowsReadOnlyProcessMemory.open_unique("sb.exe")
            if process_id is None
            else WindowsReadOnlyProcessMemory.open_for_process("sb.exe", process_id)
        )
        state["client"] = {
            "pid": process.pid,
            "creation_filetime": process.process_creation_filetime_utc,
            "executable_sha256": process.executable_sha256,
            "executable_path": str(process.executable_path),
        }
        population = NativeCharacterPopulationReader(
            load_bundled_native_character_population_profile(), process
        )
        zone = NativeCurrentZoneReader(load_bundled_native_zone_profile(), process)
        state["status"] = "recording"
        write_json(output_dir / "status.json", state)
        deadline = time.monotonic() + seconds
        previous_zone = None
        cache_done = False
        with (output_dir / "observations.jsonl").open("x", encoding="utf-8") as stream:
            while time.monotonic() < deadline:
                if (output_dir / "STOP").exists():
                    state["stop_reason"] = "requested"
                    break
                row = {"at": utc_now()}
                try:
                    row["population"] = project_population(population.observe())
                except (OSError, RuntimeError, ValueError) as exc:
                    row["population_error"] = str(exc)
                    state["errors"] += 1
                try:
                    zone_value = asdict(zone.observe())
                    if zone_value != previous_zone:
                        row["zone"] = zone_value
                        previous_zone = zone_value
                except (OSError, RuntimeError, ValueError) as exc:
                    row["zone_error"] = str(exc)
                encoded = json.dumps(row, sort_keys=True) + "\n"
                size = len(encoded.encode("utf-8"))
                if state["bytes"] + size > max_bytes:
                    state["stop_reason"] = "size_limit"
                    break
                stream.write(encoded)
                stream.flush()
                state["bytes"] += size
                state["samples"] += 1
                state["last_sample_at"] = row["at"]
                state["last_population_ok"] = "population" in row
                write_json(output_dir / "status.json", state)
                if not cache_done:
                    cache_done = True
                    try:
                        cache_inventory(process.executable_path.parent / "cache", output_dir)
                    except (OSError, ValueError) as exc:
                        state["cache_error"] = str(exc)
                time.sleep(interval)
            else:
                state["stop_reason"] = "duration_limit"
        state["status"] = "stopped"
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = str(exc)
    finally:
        if process is not None:
            process.close()
        state["finished_at"] = utc_now()
        write_json(output_dir / "status.json", state)
    return 1 if state["status"] == "failed" else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--seconds", type=int, default=7200)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 14400 or not 1 <= args.interval <= 60:
        parser.error("seconds must be 1..14400 and interval must be 1..60")
    return collect(args.output, args.pid, seconds=args.seconds, interval=args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
