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

from shadowbane_lab.client_observation.native_character_config import NativeCharacterConfigReader
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


class ObservationFilter:
    """Keep distinct structural states and membership, with compact sighting totals."""

    def __init__(self):
        self.entities = {}
        self.active = set()
        self.channels = {}
        self.suppressed = 0

    def filter(self, row):
        result = {"at": row["at"]}
        for channel in ("identity", "population", "zone"):
            error = row.get(channel + "_error")
            if error is not None:
                marker = ("error", error)
                if self.channels.get(channel) != marker:
                    result[channel + "_error"] = error
                self.channels[channel] = marker
                continue
            if channel not in row:
                continue
            value = row[channel]
            if channel != "population":
                marker = ("ok", json.dumps(value, sort_keys=True))
                if self.channels.get(channel) != marker:
                    result[channel] = value
                self.channels[channel] = marker
                continue
            marker = ("ok", json.dumps(value["local_player_object_key"], sort_keys=True))
            events = []
            active = set()
            for character in value["characters"]:
                if character["object_key"] is None:
                    raise ValueError("Cannot deduplicate an unkeyed character")
                key = json.dumps(character["object_key"], sort_keys=True)
                active.add(key)
                signature = {
                    "kind": character["kind"],
                    "roles": sorted(character["roles"]),
                    "owner_object_key": character["owner_object_key"],
                    "maximum_health": character["health"][1],
                    "alive": character["health"][0] > 0,
                }
                record = self.entities.get(key)
                if record is None:
                    if len(self.entities) >= 10000:
                        raise ValueError("Unique-entity limit reached")
                    record = {
                        "first_seen": row["at"],
                        "sightings": 0,
                        "changes": 0,
                        "appearances": 0,
                    }
                    self.entities[key] = record
                    event = "first_seen"
                elif record["signature"] != signature:
                    event = "changed"
                    record["changes"] += 1
                elif key not in self.active:
                    event = "returned"
                else:
                    event = None
                    self.suppressed += 1
                if key not in self.active:
                    record["appearances"] += 1
                record.update(
                    last_seen=row["at"],
                    last_observation=character,
                    signature=signature,
                    present=True,
                )
                record["sightings"] += 1
                if event:
                    events.append({"event": event, **character})
            for key in sorted(self.active - active):
                self.entities[key]["present"] = False
                events.append({"event": "left", "object_key": json.loads(key)})
            self.active = active
            if events or self.channels.get(channel) != marker:
                result["population"] = {
                    "local_player_object_key": value["local_player_object_key"],
                    "events": events,
                }
            self.channels[channel] = marker
        return result if len(result) > 1 else None

    def summary(self):
        return {
            "schema_version": 2,
            "suppressed_repeated_sightings": self.suppressed,
            "entities": list(self.entities.values()),
        }


def collect(
    output_dir,
    process_id=None,
    *,
    seconds=7200,
    interval=2.0,
    max_bytes=64 * 1024**2,
    expected_character=None,
    expected_server=None,
    skip_cache=False,
):
    output_dir.mkdir(parents=True, exist_ok=False)
    state = {
        "schema_version": 2,
        "started_at": utc_now(),
        "status": "starting",
        "samples": 0,
        "errors": 0,
        "bytes": 0,
        "written_records": 0,
        "suppressed_samples": 0,
        "cache_inventory": "skipped" if skip_cache else "requested",
    }
    write_json(output_dir / "status.json", state)
    process = None
    evidence = ObservationFilter()
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
        identity_reader = NativeCharacterConfigReader(process)
        initial_identity = identity_reader.observe()
        initial_key = identity_reader.observe_local_key()
        if identity_reader.observe() != initial_identity:
            raise ValueError("Character changed during initial binding")
        if (
            expected_character
            and initial_identity.character_name.casefold() != expected_character.casefold()
        ) or (
            expected_server
            and initial_identity.server_name.casefold() != expected_server.casefold()
        ):
            raise ValueError("Running character/server does not match requested watcher")
        state["character"] = {
            "name": initial_identity.character_name,
            "server": initial_identity.server_name,
            "object_key": asdict(initial_key),
        }
        population = NativeCharacterPopulationReader(
            load_bundled_native_character_population_profile(), process
        )
        zone = NativeCurrentZoneReader(load_bundled_native_zone_profile(), process)
        state["status"] = "recording"
        write_json(output_dir / "status.json", state)
        deadline = time.monotonic() + seconds
        cache_done = skip_cache
        with (output_dir / "observations.jsonl").open("x", encoding="utf-8") as stream:
            while time.monotonic() < deadline:
                if (output_dir / "STOP").exists():
                    state["stop_reason"] = "requested"
                    break
                row = {"at": utc_now()}
                try:
                    before = identity_reader.observe()
                    if (before.character_name, before.server_name) != (
                        initial_identity.character_name,
                        initial_identity.server_name,
                    ) or identity_reader.observe_local_key() != initial_key:
                        state["stop_reason"] = "character_changed"
                        break
                    row["identity"] = state["character"]
                    try:
                        observed = population.observe()
                        if observed.local_player_object_key != initial_key:
                            raise ValueError("Population local identity changed")
                        row["population"] = project_population(observed)
                    except (OSError, RuntimeError, ValueError) as exc:
                        row["population_error"] = str(exc)
                        state["errors"] += 1
                    try:
                        row["zone"] = asdict(zone.observe())
                    except (OSError, RuntimeError, ValueError) as exc:
                        row["zone_error"] = str(exc)
                    if identity_reader.observe() != before:
                        row = {"at": row["at"], "identity_error": "Identity changed during sample"}
                except (OSError, RuntimeError, ValueError) as exc:
                    row = {"at": row["at"], "identity_error": str(exc)}
                    state["errors"] += 1
                filtered = evidence.filter(row)
                if filtered is not None:
                    encoded = json.dumps(filtered, sort_keys=True) + "\n"
                    size = len(encoded.encode("utf-8"))
                    if state["bytes"] + size > max_bytes:
                        state["stop_reason"] = "size_limit"
                        break
                    stream.write(encoded)
                    stream.flush()
                    state["bytes"] += size
                    state["written_records"] += 1
                else:
                    state["suppressed_samples"] += 1
                state["samples"] += 1
                state["last_sample_at"] = row["at"]
                state["last_population_ok"] = "population" in row
                state["unique_entities"] = len(evidence.entities)
                state["suppressed_repeated_sightings"] = evidence.suppressed
                if state["samples"] == 1 or state["samples"] % 15 == 0:
                    write_json(output_dir / "entity-summary.json", evidence.summary())
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
        write_json(output_dir / "entity-summary.json", evidence.summary())
        write_json(output_dir / "status.json", state)
    return 1 if state["status"] == "failed" else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--seconds", type=int, default=7200)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--character")
    parser.add_argument("--server")
    parser.add_argument("--skip-cache", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 14400 or not 1 <= args.interval <= 60:
        parser.error("seconds must be 1..14400 and interval must be 1..60")
    return collect(
        args.output,
        args.pid,
        seconds=args.seconds,
        interval=args.interval,
        expected_character=args.character,
        expected_server=args.server,
        skip_cache=args.skip_cache,
    )


if __name__ == "__main__":
    raise SystemExit(main())
