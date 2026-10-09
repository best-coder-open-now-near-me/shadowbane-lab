"""Bounded inspection and tinting of native Visual.cache records.

Layout reference: MagicBane mbEditorPro, commit 75efa29012592d7d0e35ebfd0703990f90f10995,
arcane/ArcVisual.py. This does not resolve native bone enums or weapon bindings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path

from shadowbane_lab.world_data.cache import CacheArchive

# Native fixed-width effect bodies. Offsets are relative to their body, after type/time.
_BODY_BYTES = {0: 256, 1: 56, 2: 108}
_NAMES = {0: "particle", 1: "lightning", 2: "geometry"}


@dataclass(frozen=True)
class NativeEffect:
    index: int
    kind: str
    starts_at: float
    body_offset: int
    attached_bone: int
    texture_id: int


@dataclass(frozen=True)
class NativeVisual:
    duration: float
    effects: tuple[NativeEffect, ...]


def decode_visual(payload: bytes) -> NativeVisual:
    """Reject unknown, truncated, trailing and opaque records without guessing."""
    if len(payload) < 8:
        raise ValueError("Truncated native visual header")
    count, duration = struct.unpack_from("<If", payload)
    if count > 1024 or not math.isfinite(duration):
        raise ValueError("Unsupported native visual header (possibly opaque data)")
    effects, offset = [], 8
    for index in range(count):
        if offset + 8 > len(payload):
            raise ValueError("Truncated native effect header")
        kind, starts_at = struct.unpack_from("<If", payload, offset)
        offset += 8
        size = _BODY_BYTES.get(kind)
        if size is None or not math.isfinite(starts_at):
            raise ValueError("Unsupported native effect type or time")
        if offset + size > len(payload):
            raise ValueError("Truncated native effect body")
        bone_offset, texture_offset = (0, 224) if kind == 0 else (4, 0)
        effects.append(
            NativeEffect(
                index,
                _NAMES[kind],
                starts_at,
                offset,
                struct.unpack_from("<I", payload, offset + bone_offset)[0],
                struct.unpack_from("<I", payload, offset + texture_offset)[0],
            )
        )
        offset += size
    if offset != len(payload):
        raise ValueError("Unrecognized trailing native visual data")
    return NativeVisual(duration, tuple(effects))


def moonfire_tint(payload: bytes, *, source_sha256: str, effect_index: int) -> bytes:
    """Tint one selected particle's RGB keys; preserve alpha and every other byte.

    The texture still modulates these keys: this alone does not make a colored
    texture white, attach it to a sword, or publish/install an effect.
    """
    if hashlib.sha256(payload).hexdigest() != source_sha256:
        raise ValueError("Native visual source digest changed")
    visual = decode_visual(payload)
    if type(effect_index) is not int or not 0 <= effect_index < len(visual.effects):
        raise ValueError("Invalid effect index")
    effect = visual.effects[effect_index]
    if effect.kind != "particle":
        raise ValueError("Moon-fire tint requires a particle effect")
    result = bytearray(payload)
    # White peak, a restrained cool edge; retain the source alpha animation.
    colors = (
        (0.88, 0.94, 1.0),
        (1.0, 1.0, 1.0),
        (0.96, 0.98, 1.0),
        (0.86, 0.92, 1.0),
        (0.78, 0.86, 1.0),
    )
    for index, color in enumerate(colors):
        position = effect.body_offset + 96 + index * 16
        original = struct.unpack_from("<4f", payload, position)
        if not all(math.isfinite(v) for v in original):
            raise ValueError("Nonfinite source particle color")
        struct.pack_into("<3f", result, position, *color)
    return bytes(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect a native visual without changing the client"
    )
    parser.add_argument("cache", type=Path)
    parser.add_argument("resource", type=int)
    parser.add_argument("--group", type=int, default=0)
    parser.add_argument("--tint-effect", type=int)
    parser.add_argument("--source-sha256")
    parser.add_argument("--output", type=Path, help="New standalone payload; never a game cache")
    args = parser.parse_args()
    if args.tint_effect is not None and (not args.source_sha256 or not args.output):
        parser.error("Tinting requires --source-sha256 and --output")
    if args.tint_effect is None and (args.source_sha256 or args.output):
        parser.error("Output and source digest require --tint-effect")
    with CacheArchive(args.cache) as archive:
        matches = [e for e in archive.entries_for_id(args.resource) if e.group_id == args.group]
        if len(matches) != 1:
            parser.error("Resource must resolve to exactly one group/id record")
        payload = archive.read_resource(matches[0])
    visual = decode_visual(payload)
    report = {
        "group": args.group,
        "resource": args.resource,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
        "duration": visual.duration,
        "effects": [vars(e) for e in visual.effects],
        "weapon_binding_verified": False,
        "installed": False,
    }
    if args.tint_effect is not None:
        candidate = moonfire_tint(
            payload, source_sha256=args.source_sha256, effect_index=args.tint_effect
        )
        # Exclusive creation also prevents replacing the source or any existing data.
        with args.output.open("xb") as stream:
            stream.write(candidate)
        report["candidate_sha256"] = hashlib.sha256(candidate).hexdigest()
        report["candidate_path"] = str(args.output.resolve())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
