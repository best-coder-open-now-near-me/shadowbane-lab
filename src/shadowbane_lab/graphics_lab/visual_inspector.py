"""On-demand, process-bound visual snapshots and read-only cache enrichment."""

from __future__ import annotations

import ctypes
import struct
from collections import defaultdict
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path

from shadowbane_lab.world_data.cache import CacheArchive
from shadowbane_lab.world_data.object_navigation import (
    parse_object_navigation_metadata,
    parse_render_navigation_metadata,
)

from . import control

MAGIC = 0x49564257
SIZE = 2112
HEADER = struct.Struct("<4IQ8IQ")
NODE = struct.Struct("<4I")
STATUSES = (
    "Captured",
    "No supported selection or scene",
    "Unsupported or oversized render tree",
    "Selection or render tree changed; capture again",
    "Invalid capture request",
)


def unpack(data, target):
    if len(data) != SIZE:
        raise ValueError("Visual snapshot size mismatch")
    (
        magic,
        version,
        size,
        pid,
        creation,
        request,
        selection,
        publication,
        applied,
        status,
        kind,
        uuid,
        count,
        tick,
    ) = HEADER.unpack_from(data)
    if (magic, version, size, pid, creation) != (
        MAGIC,
        1,
        SIZE,
        target.process_id,
        target.process_creation_filetime_utc,
    ):
        raise ValueError("Visual snapshot identity mismatch")
    if publication & 1 or request & 1 or selection > 1 or status >= len(STATUSES):
        raise ValueError("Visual snapshot is unavailable or being updated")
    if count > 128 or (status and count) or (not status and not count):
        raise ValueError("Invalid visual node count")
    nodes, seen = [], set()
    for index in range(count):
        address, parent, resource, reserved = NODE.unpack_from(data, 64 + index * NODE.size)
        if (
            not 0x10000 <= address <= 0x7FFEEFFF
            or address in seen
            or reserved
            or (parent != 0xFFFFFFFF if index == 0 else parent >= index)
        ):
            raise ValueError("Invalid visual tree")
        seen.add(address)
        nodes.append(
            {
                "index": index,
                "parent": None if index == 0 else parent,
                "address": address,
                "render_id": resource,
            }
        )
    return {
        "schema": 1,
        "process_id": pid,
        "process_creation": creation,
        "request": request,
        "applied": applied,
        "selection": selection,
        "status": status,
        "status_text": STATUSES[status],
        "capture_tick_ms": tick,
        "object_type": kind,
        "object_uuid": uuid,
        "nodes": nodes,
    }


class VisualInspectorClient:
    def __init__(self, target):
        self.target = target
        self.mapping = self.address = self.mutex = None
        if not control.verify_target_identity(target):
            raise OSError("The selected game instance has changed")
        api = control._kernel32
        name = (
            f"Local\\WonderBaneVisuals-{target.process_id}-{target.process_creation_filetime_utc}"
        )
        try:
            self.mapping = api.OpenFileMappingW(0xF001F, False, name)
            if not self.mapping:
                raise OSError("Install the Visual Inspector DLL to enable live capture")
            self.address = api.MapViewOfFile(self.mapping, 0xF001F, 0, 0, SIZE)
            if not self.address:
                raise OSError("Could not open visual snapshots")
            self.mutex = api.CreateMutexW(None, False, name + "-writer")
            if not self.mutex:
                raise OSError("Could not open visual request writer")
            self.read()
        except Exception:
            self.close()
            raise

    def read(self):
        if not self.address or not control.target_process_is_alive(self.target):
            raise OSError("Game closed or changed")
        first = ctypes.c_uint32.from_address(self.address + 32).value
        data = ctypes.string_at(self.address, SIZE)
        last = ctypes.c_uint32.from_address(self.address + 32).value
        if first != last or HEADER.unpack_from(data)[7] != first:
            raise ValueError("Visual snapshot is being published")
        return unpack(data, self.target)

    def request(self, selection):
        if type(selection) is not int or selection not in (0, 1):
            raise ValueError("Invalid selection")
        api = control._kernel32
        if not self.mutex or api.WaitForSingleObject(self.mutex, 100) not in (0, 0x80):
            raise TimeoutError("Visual Inspector is busy")
        try:
            snapshot = self.read()
            sequence = max(snapshot["request"], snapshot["applied"]) + 2
            if sequence >= 0x7FFFFFFE:
                sequence = 2
            word = ctypes.c_uint32.from_address(self.address + 24)
            word.value = sequence - 1
            ctypes.c_uint32.from_address(self.address + 28).value = selection
            word.value = sequence
            return sequence
        finally:
            api.ReleaseMutex(self.mutex)

    def close(self):
        api = control._kernel32
        if self.address:
            api.UnmapViewOfFile(self.address)
        for handle in (self.mapping, self.mutex):
            if handle:
                api.CloseHandle(handle)
        self.mapping = self.address = self.mutex = None


def _key(value):
    return f"{value.group_id}:{value.resource_id}"


def enrich(snapshot, folder):
    """Join observed render IDs to local templates, retaining all ambiguous matches.

    Runtime reads do not establish resource groups or item slots. Template links
    describe cache assets, not proof of a particular equipped item or live material.
    """
    folder = Path(folder).resolve()
    result = dict(snapshot, cache_folder=str(folder), cache_files={}, warnings=[], nodes=[])
    wanted = {row["render_id"] for row in snapshot["nodes"]}
    with ExitStack() as stack:
        archives = {}
        signatures = {}
        for name in ("Render", "CObjects", "Mesh", "Textures"):
            path = folder / f"{name}.cache"
            if not path.is_file():
                result["warnings"].append(f"{path.name} unavailable")
                continue
            before = path.stat()
            archive = stack.enter_context(CacheArchive(path))
            if len(archive.entries) > 250_000:
                raise ValueError(f"{path.name} exceeds inspector resource limit")
            archives[name] = archive
            signatures[path] = (before.st_size, before.st_mtime_ns)
            result["cache_files"][name] = {"bytes": before.st_size, "mtime_ns": before.st_mtime_ns}
        indexed = {}
        for name, archive in archives.items():
            by_id = defaultdict(list)
            for entry in archive.entries:
                by_id[entry.resource_id].append(entry)
            indexed[name] = by_id

        candidates = defaultdict(list)
        skipped = 0
        if "CObjects" in archives:
            for entry in archives["CObjects"].entries:
                if entry.uncompressed_size > 4 * 1024 * 1024:
                    skipped += 1
                    continue
                try:
                    meta = parse_object_navigation_metadata(
                        archives["CObjects"].read_resource(entry)
                    )
                except ValueError:
                    skipped += 1
                    continue
                if meta.render_key.resource_id in wanted:
                    candidates[_key(meta.render_key)].append(
                        {
                            "key": f"{entry.group_id}:{entry.resource_id}",
                            "name": meta.name,
                            "object_type": meta.object_type,
                            "match": "shared primary-render candidate; item/slot not verified",
                        }
                    )
        if skipped:
            result["warnings"].append(f"{skipped} CObject records unsupported or oversized")

        resolved = {}
        for resource in wanted:
            options = []
            for entry in indexed.get("Render", {}).get(resource, []):
                key = f"{entry.group_id}:{entry.resource_id}"
                option = {"render_key": key, "object_candidates": candidates[key]}
                try:
                    if entry.uncompressed_size > 4 * 1024 * 1024:
                        raise ValueError("Render payload exceeds inspector limit")
                    meta = parse_render_navigation_metadata(archives["Render"].read_resource(entry))
                    option.update(asdict(meta))
                    option["mesh_keys"] = [_key(k) for k in meta.mesh_keys]
                    option["texture_keys"] = [_key(k) for k in meta.texture_keys]
                    option["child_keys"] = [_key(k) for k in meta.child_keys]
                    option["specular_key"] = _key(meta.specular_key)
                    option["missing_resources"] = []
                    for name, keys in (("Mesh", meta.mesh_keys), ("Textures", meta.texture_keys)):
                        for k in keys:
                            if not k.resource_id:
                                continue
                            matches = [
                                e
                                for e in indexed.get(name, {}).get(k.resource_id, [])
                                if e.group_id == k.group_id
                            ]
                            if len(matches) != 1:
                                option["missing_resources"].append(
                                    f"{name} {_key(k)}: {len(matches)} matches"
                                )
                except ValueError as error:
                    option["error"] = str(error)
                options.append(option)
            resolved[resource] = options
        for row in snapshot["nodes"]:
            options = resolved[row["render_id"]]
            result["nodes"].append(
                dict(
                    row,
                    templates=options,
                    resolution=(
                        "unique resource ID; runtime group unverified"
                        if len(options) == 1
                        else "ambiguous groups/records"
                        if options
                        else "render not found in chosen cache"
                    ),
                )
            )
        for path, signature in signatures.items():
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != signature:
                raise ValueError("Cache changed during inspection; capture again")
    return result
