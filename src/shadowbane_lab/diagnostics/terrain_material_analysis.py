"""Offline source-material comparison along actual captured terrain boundaries."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import struct
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from .terrain_material_poll import PROFILE
from .terrain_mesh_snapshot import LAYOUT_SIGNATURES, MAXIMUM_INDICES, MAXIMUM_VERTICES
from .terrain_trace_analysis import analyze_terrain_trace

MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_SAMPLES = 200_000
HEIGHT_TOLERANCE = 0.0001


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _bytes(record: dict, size: int) -> bytes:
    encoded = record["bytes_base64"]
    _require(isinstance(encoded, str) and len(encoded) <= 4 * ((size + 2) // 3),
             "oversized encoded buffer")
    raw = base64.b64decode(encoded, validate=True)
    _require(len(raw) == size == record["byte_count"], "buffer size mismatch")
    _require(hashlib.sha256(raw).hexdigest() == record["sha256"], "buffer digest mismatch")
    return raw


def _array(record: dict, count: int, components: int, scalar: str) -> list[tuple]:
    name = "little_endian_float32" if scalar == "f" else "little_endian_uint16"
    _require(record["scalar"] == name and record["components"] == components,
             "unsupported array layout")
    fmt = "<" + scalar * components
    return list(struct.iter_unpack(fmt, _bytes(record, count * struct.calcsize(fmt))))


def _token(texture: dict) -> str:
    _require(isinstance(texture, dict) and texture.get("reviewed_color_texture") is True,
             "unreviewed material token")
    token = texture["token"]
    group, resource = token["archive_group"], token["archive_resource"]
    _require(all(type(v) is int and 0 <= v <= 0xFFFFFFFF for v in (group, resource)),
             "invalid material token")
    _require((group, resource) != (0, 0), "unattributed color material")
    return f"{group}:{resource}"


@dataclass(frozen=True)
class Mask:
    token: str
    size: int
    pixels: bytes

    def sample(self, uv: tuple[float, float]) -> float:
        # The reviewed pass uses GL_LINEAR, CLAMP_TO_EDGE and an alpha8 mask.
        x, y = (max(0.0, min(self.size - 1.0, v * self.size - 0.5)) for v in uv)
        ix, iy = int(x), int(y)
        jx, jy = min(ix + 1, self.size - 1), min(iy + 1, self.size - 1)
        fx, fy = x - ix, y - iy
        a = self.pixels[iy * self.size + ix] * (1 - fx)
        a += self.pixels[iy * self.size + jx] * fx
        b = self.pixels[jy * self.size + ix] * (1 - fx)
        b += self.pixels[jy * self.size + jx] * fx
        return (a * (1 - fy) + b * fy) / 255


@dataclass(frozen=True)
class Segment:
    p: tuple[float, float, float]
    q: tuple[float, float, float]
    u: tuple[float, float]
    v: tuple[float, float]
    along: int

    @property
    def low(self) -> float:
        return self.p[self.along]

    @property
    def high(self) -> float:
        return self.q[self.along]

    def at(self, coordinate: float) -> tuple[tuple, tuple]:
        t = (coordinate - self.low) / (self.high - self.low)
        return (tuple(a + (b - a) * t for a, b in zip(self.p, self.q, strict=True)),
                tuple(a + (b - a) * t for a, b in zip(self.u, self.v, strict=True)))


def boundary_segments(positions: list[tuple], uv: list[tuple], indices: list[int]) -> dict:
    """Actual triangle boundaries on outer X/Z planes; no guessed corner adjacency."""
    referenced = set(indices)
    _require(referenced and max(referenced) < len(positions) and min(referenced) >= 0,
             "index outside vertex array")
    # Reject duplicated coordinates with conflicting UVs instead of welding a UV seam.
    coordinates = {}
    for i in referenced:
        _require(positions[i] not in coordinates or coordinates[positions[i]] == uv[i],
                 "ambiguous UVs at coincident vertices")
        coordinates[positions[i]] = uv[i]
    counts: Counter = Counter()
    for start in range(0, len(indices), 3):
        tri = [positions[i] for i in indices[start:start + 3]]
        _require(len(set(tri)) == 3, "degenerate triangle")
        u = tuple(b - a for a, b in zip(tri[0], tri[1], strict=True))
        v = tuple(b - a for a, b in zip(tri[0], tri[2], strict=True))
        _require(any(u[i] * v[j] != u[j] * v[i] for i, j in ((0, 1), (1, 2), (2, 0))),
                 "zero-area triangle")
        for a, b in ((0, 1), (1, 2), (2, 0)):
            counts[tuple(sorted((tri[a], tri[b])))] += 1
    _require(all(n <= 2 for n in counts.values()), "nonmanifold triangle edge")
    bounds = {axis: (min(p[axis] for p in coordinates), max(p[axis] for p in coordinates))
              for axis in (0, 2)}
    groups: dict[tuple, list[Segment]] = {}
    for (p, q), count in counts.items():
        if count != 1:
            continue
        for axis in (0, 2):
            along = 2 - axis
            if p[axis] != q[axis] or p[along] == q[along]:
                continue
            for side, plane in enumerate(bounds[axis]):
                if p[axis] != plane:
                    continue
                a, b = sorted((p, q), key=lambda point: point[along])
                groups.setdefault((axis, plane, side), []).append(
                    Segment(a, b, coordinates[a], coordinates[b], along))
    for segments in groups.values():
        segments.sort(key=lambda s: s.low)
        _require(all(a.high <= b.low for a, b in zip(segments, segments[1:], strict=False)),
                 "overlapping boundary segments")
    return groups


def overlaps(left: list[Segment], right: list[Segment]):
    """Intersect ordered intervals, including differently subdivided (LOD) edges."""
    i = j = 0
    while i < len(left) and j < len(right):
        a, b = left[i], right[j]
        low, high = max(a.low, b.low), min(a.high, b.high)
        if high > low:  # A common corner alone is not a shared edge.
            yield a, b, low, high
        if a.high <= b.high:
            i += 1
        else:
            j += 1


@dataclass
class Tile:
    ordinal: int
    source: str
    base: str
    masks: list[Mask]
    rotation: float
    boundaries: dict

    def rotate(self, uv: tuple) -> tuple[float, float]:
        angle = math.radians(self.rotation % 360)
        c, s = math.cos(angle), math.sin(angle)
        x, y = uv[0] - 0.5, uv[1] - 0.5
        return c * x + s * y + 0.5, -s * x + c * y + 0.5

    def weights(self, uv: tuple) -> dict[str, float]:
        weights = {self.base: 1.0}
        for mask in self.masks:
            alpha = mask.sample(self.rotate(uv))
            weights = {key: value * (1 - alpha) for key, value in weights.items()}
            weights[mask.token] = weights.get(mask.token, 0.0) + alpha
        return weights


def _tile(snapshot: dict) -> Tile:
    source, mesh = snapshot["source"], snapshot["mesh"]
    _require(mesh["state"] == "captured" and mesh["topology"] == "triangles",
             "mesh was not captured on the reviewed triangle path")
    n, m = mesh["vertex_count"], mesh["index_count"]
    _require(type(n) is int and 0 < n <= MAXIMUM_VERTICES, "invalid vertex count")
    _require(type(m) is int and 0 < m <= MAXIMUM_INDICES and m % 3 == 0,
             "invalid triangle index count")
    p = _array(mesh["positions"], n, 3, "f")
    uv = _array(mesh["uv"], n, 2, "f")
    indices = [v[0] for v in _array(mesh["indices"], m, 1, "H")]
    _require(all(math.isfinite(v) for point in p + uv for v in point),
             "nonfinite mesh coordinate")
    _require(all(0 <= v <= 1 for point in uv for v in point), "unsupported terrain UV range")
    rotation = source["mask_rotation_degrees"]
    _require(type(rotation) in (int, float) and math.isfinite(rotation), "invalid mask rotation")
    _require(source["layer_vector_counts_agree"] is True and len(source["layers"]) <= 32,
             "invalid layer vector")
    masks = []
    for index, layer in enumerate(source["layers"]):
        _require(layer["index"] == index, "unordered terrain layers")
        alpha = layer["source_mask"]["resident_alpha"]
        _require(alpha["state"] == "captured" and alpha["storage"] == "resident_cpu_alpha8",
                 "source alpha was not captured")
        size = alpha["width"]
        _require(type(size) is int and size in (64, 128) and alpha["height"] == size,
                 "unsupported alpha dimensions")
        masks.append(Mask(_token(layer["color"]), size, _bytes(alpha, size * size)))
    return Tile(snapshot["ordinal"], source["address"], _token(source["base"]), masks,
                rotation, boundary_segments(p, uv, indices))


def _validate_capture(payload: dict) -> None:
    _require(payload["schema_version"] == 4 and payload["status"] == "captured",
             "requires a completed schema-4 material capture")
    _require(payload["profile_id"] == PROFILE.profile_id, "unsupported capture profile")
    for field in ("executable_sha256", "extension_sha256"):
        _require(payload[field] == getattr(PROFILE.branch_profile, field), "unreviewed build")
    expected = {
        "draw_entry": PROFILE.draw_signature.hex(),
        "shader_vtable": f"0x{int(payload['image_base'], 16) + PROFILE.shader_vtable_rva:08x}",
        "pixel_accessor": PROFILE.pixel_accessor_signature.hex(),
        "mesh_layout_signatures": {f"0x{rva:08x}": raw.hex() for rva, raw in LAYOUT_SIGNATURES},
        "repaired_branches": {b.label: b.signature.hex() for b in PROFILE.branch_profile.branches},
    }
    _require(payload["signatures_before"] == payload["signatures_after"] == expected,
             "recorded signature validation disagrees")
    _require(type(payload["process_id"]) is int and payload["process_id"] > 0
             and type(payload["process_creation_filetime_utc"]) is int
             and payload["process_creation_filetime_utc"] > 0, "invalid process lifetime")
    _require(isinstance(payload["snapshots"], list) and len(payload["snapshots"]) <= 64,
             "invalid snapshot list")


def corroborate_draws(payload: dict, trace: dict) -> tuple[dict, dict]:
    """Match complete base/layer sequences, not isolated reused GL names or counts."""
    assessment = analyze_terrain_trace(trace)
    _require(assessment["status"] == "terrain_draws_attributed"
             and trace["reviewed_interval_complete"], "draw trace is not a reviewed interval")
    _require(trace["extension_version"] == "1.6.13", "draw trace renderer version mismatch")
    for key in ("process_id", "process_creation_filetime_utc", "executable_sha256"):
        _require(payload[key] == trace[key], "draw trace belongs to a different client lifetime")
    sequences = []
    for draw in trace["draws"]:
        stack = draw["client_stack_rvas"]
        if 0x4F1772 in stack:
            sequences.append([draw])
        elif 0x4F1864 in stack:
            _require(bool(sequences), "masked draw has no preceding terrain base")
            sequences[-1].append(draw)

    def binding(draw: dict, unit: int) -> int | None:
        values = [t["binding"] for t in draw["textures"] if t["unit"] == unit and t["enabled"]]
        return values[0] if len(values) == 1 else None

    matches = {}
    for snapshot in payload["snapshots"]:
        try:
            count = snapshot["mesh"]["index_count"]
            source = snapshot["source"]
            base = source["base"]["backing"]["binding"]
            layers = [(r["color"]["backing"]["binding"], r["gpu_mask"]["backing"]["binding"])
                      for r in source["layers"]]
            candidates = [seq for seq in sequences if seq[0]["count"] == count
                          and binding(seq[0], 0) == base
                          and all(d["count"] == count for d in seq)
                          and [(binding(d, 0), binding(d, 1)) for d in seq[1:]] == layers]
            matches[snapshot["ordinal"]] = {
                "state": "corroborated" if len(candidates) == 1 else "not_uniquely_corroborated",
                "candidate_count": len(candidates),
                "draw_ordinals": [d["ordinal"] for d in candidates[0]] if len(candidates) == 1
                else [],
            }
        except (KeyError, TypeError):
            matches[snapshot["ordinal"]] = {"state": "binding_evidence_unavailable"}
    owners = {}
    for snapshot in payload["snapshots"]:
        match = matches[snapshot["ordinal"]]
        if match["state"] == "corroborated":
            owners.setdefault(match["draw_ordinals"][0], set()).add(snapshot["fingerprint_sha256"])
    for match in matches.values():
        if match["state"] == "corroborated" and len(owners[match["draw_ordinals"][0]]) != 1:
            match["state"] = "conflicting_snapshots_for_draw"
    return matches, assessment["trace_assessment"]


def analyze_material_boundaries(payload: dict, *, draw_trace: dict | None = None) -> dict:
    _validate_capture(payload)
    tiles, skipped = [], []
    matches, trace_assessment = (corroborate_draws(payload, draw_trace) if draw_trace is not None
                                 else ({}, None))
    ordinals = set()
    for snapshot in payload["snapshots"]:
        ordinal = snapshot["ordinal"]
        _require(type(ordinal) is int and ordinal > 0 and ordinal not in ordinals,
                 "invalid or duplicate snapshot ordinal")
        ordinals.add(ordinal)
        _require(snapshot["source_pointer"] == snapshot["source"]["address"]
                 and snapshot["ownership_consistency"] in ("whole-read", "staged-root-and-graph"),
                 "invalid snapshot ownership")
        identity = {"source": snapshot["source"], "mesh": snapshot.get("mesh")}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest()
        _require(digest == snapshot["fingerprint_sha256"], "snapshot fingerprint mismatch")
        if draw_trace is not None and matches[ordinal]["state"] != "corroborated":
            skipped.append({"ordinal": ordinal, "reason": "no unique complete draw-sequence match"})
            continue
        try:
            tiles.append(_tile(snapshot))
        except (ValueError, KeyError, TypeError) as error:
            skipped.append({"ordinal": snapshot.get("ordinal"), "reason": str(error)})
    results = []
    sample_count = 0
    for left, right in combinations(tiles, 2):
        if left.source == right.source:
            continue  # Never mistake two observations of one source for adjacent tiles.
        for (axis, plane, side), segments in left.boundaries.items():
            opposite = right.boundaries.get((axis, plane, 1 - side), [])
            total_length = integral = maximum = 0.0
            fragments = samples = rejected = 0
            worst = None
            for a, b, low, high in overlaps(segments, opposite):
                if any(abs(a.at(t)[0][1] - b.at(t)[0][1]) > HEIGHT_TOLERANCE
                       for t in (low, high)):
                    rejected += 1
                    continue
                spans = []
                for tile, segment in ((left, a), (right, b)):
                    u, v = (tile.rotate(segment.at(t)[1]) for t in (low, high))
                    spans.append(max(abs(x - y) for x, y in zip(u, v, strict=True))
                                 * max((mask.size for mask in tile.masks), default=1))
                steps = max(1, math.ceil(2 * max(spans)))
                _require(sample_count + steps + 1 <= MAX_SAMPLES,
                         "analysis sample budget exhausted")
                distances = []
                for i in range(steps + 1):
                    coordinate = low + (high - low) * i / steps
                    position, lu = a.at(coordinate)
                    ru = b.at(coordinate)[1]
                    lw, rw = left.weights(lu), right.weights(ru)
                    distance = sum(abs(lw.get(k, 0) - rw.get(k, 0)) for k in lw.keys() | rw) / 2
                    distances.append(distance)
                    if worst is None or distance > maximum:
                        maximum = distance
                        worst = {"position": position, "left_uv": lu, "right_uv": ru,
                                 "left_weights": lw, "right_weights": rw}
                # Convert this fragment's trapezoidal sum to a length-weighted integral.
                integral += ((sum(distances) - (distances[0] + distances[-1]) / 2)
                             * (high - low) / steps)
                total_length += high - low
                fragments += 1
                samples += steps + 1
                sample_count += steps + 1
            if fragments or rejected:
                results.append({"left_ordinal": left.ordinal, "right_ordinal": right.ordinal,
                                "left_source": left.source, "right_source": right.source,
                                "plane_axis": "x" if axis == 0 else "z", "plane": plane,
                                "fragment_count": fragments, "sample_count": samples,
                                "rejected_height_fragments": rejected,
                                "compared_projected_length": total_length,
                                "sampled_max_weight_distance": maximum if fragments else None,
                                "length_weighted_mean_distance": integral / total_length
                                if fragments else None, "worst_sample": worst})
    return {
        "schema_version": 1, "status": "analyzed_with_limits",
        "process_id": payload["process_id"],
        "process_creation_filetime_utc": payload["process_creation_filetime_utc"],
        "input_snapshot_count": len(payload["snapshots"]), "analyzed_tiles": len(tiles),
        "skipped_snapshots": skipped, "sample_count": sample_count, "boundaries": results,
        "draw_corroboration": {"requested": draw_trace is not None,
                               "trace_assessment": trace_assessment,
                               "snapshots": matches},
        "model": "source-alpha8-linear-clamp-to-edge-ordered-source-alpha-composition",
        "scope": {"live_process_access": False, "gpu_readback": False, "cache_writes": False,
                  "atomic_frame": False, "framebuffer_color": False},
        "limitations": [
            "Recorded hashes/signatures are checked, not independently authenticated.",
            "Only captured triangle boundaries on opposite outer X/Z planes are compared.",
            "Plane coordinates match exactly; interpolated heights allow 0.0001 world units.",
            "Half-texel or finer spacing per UV axis; sampled maxima are not analytic bounds.",
            "Source masks and assumed pass state, not observed GPU pixels or array bindings.",
            "Level-zero alpha model; actual minification may use unobserved mip levels.",
            "RGB texture phase, lighting, fog and current screen projection are not measured.",
            "Snapshots are separate non-atomic observations; absent neighbors remain unobserved.",
            "Draw corroboration checks bindings/counts/order, not pointers "
            "or simultaneous ownership.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--draw-trace", type=Path,
                        help="require unique same-lifetime base/layer draw-sequence corroboration")
    args = parser.parse_args(argv)
    try:
        with args.capture.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        _require(len(raw) <= MAX_INPUT_BYTES, "capture exceeds 64 MiB")
        trace_raw = None
        if args.draw_trace is not None:
            with args.draw_trace.open("rb") as stream:
                trace_raw = stream.read(MAX_INPUT_BYTES + 1)
            _require(len(trace_raw) <= MAX_INPUT_BYTES, "draw trace exceeds 64 MiB")
        result = analyze_material_boundaries(
            json.loads(raw), draw_trace=json.loads(trace_raw) if trace_raw is not None else None,
        )
        result["input_sha256"] = hashlib.sha256(raw).hexdigest()
        if trace_raw is not None:
            result["draw_trace_sha256"] = hashlib.sha256(trace_raw).hexdigest()
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        print(json.dumps({"output": str(args.output), "boundaries": len(result["boundaries"]),
                          "samples": result["sample_count"],
                          "skipped": result["skipped_snapshots"]}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        print(json.dumps({"status": "not_analyzed", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
