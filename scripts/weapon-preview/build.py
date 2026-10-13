"""Build a self-contained preview of the verified Archon asset, without Blender.

Uses the existing cache reader; output contains private game assets and stays local.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import struct
from pathlib import Path

from PIL import Image

from shadowbane_lab.world_data.cache import CacheArchive


def decode_mesh(payload):
    # Common mesh layout; named meshes have a variable UTF-16 prefix.
    if len(payload) < 4:
        raise ValueError("Missing mesh header")
    chars = struct.unpack_from("<I", payload)[0]
    offset = 4 + chars * 2 + 40
    if chars > 4096 or offset + 2 > len(payload):
        raise ValueError("Invalid mesh header")
    flags = payload[offset : offset + 2]
    if any(x not in (0, 1) for x in flags):
        raise ValueError("Unknown mesh flags")
    offset += 2

    def array(fmt, maximum=65536):
        nonlocal offset
        if offset + 4 > len(payload):
            raise ValueError("Missing mesh count")
        count = struct.unpack_from("<I", payload, offset)[0]
        offset += 4
        stride = struct.calcsize(fmt)
        if count > maximum or offset + count * stride > len(payload):
            raise ValueError("Mesh section exceeds payload")
        values = list(struct.iter_unpack(fmt, payload[offset : offset + count * stride]))
        offset += count * stride
        return values

    vertices = array("<3f")
    array("<3f")  # Normals are reconstructed for the preview.
    uv = array("<2f")
    if flags[1]:
        array("<3f")
    indices = [x[0] for x in array("<H", maximum=1000000)]
    if not vertices or len(uv) != len(vertices) or len(indices) % 3:
        raise ValueError("Unsupported vertex/UV/triangle layout")
    if any(i >= len(vertices) for i in indices):
        raise ValueError("Mesh index out of bounds")
    if not all(math.isfinite(x) for row in [*vertices, *uv] for x in row):
        raise ValueError("Nonfinite mesh geometry")
    if max(v[1] for v in vertices) <= min(v[1] for v in vertices):
        raise ValueError("Mesh has no vertical extent")
    return {"vertices": vertices, "uv": uv, "indices": indices}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mesh_cache", type=Path)
    parser.add_argument("texture_payload", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with CacheArchive(args.mesh_cache) as c:
        entries = [e for e in c.entries_for_id(29243) if e.group_id == 0]
        if len(entries) != 1:
            raise ValueError("Archon mesh 0:29243 must be unique")
        model = decode_mesh(c.read_resource(entries[0]))
    payload = args.texture_payload.read_bytes()
    width, height, channels = struct.unpack_from("<III", payload)
    if (width, height, channels) != (256, 512, 4) or len(payload) != 26 + width * height * channels:
        raise ValueError("Unexpected Archon texture layout")
    png = io.BytesIO()
    Image.frombytes("RGBA", (width, height), payload[26:]).save(png, format="PNG")
    model["texture"] = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode("ascii")
    template = Path(__file__).with_name("archon.html").read_text(encoding="utf-8-sig")
    args.output.write_text(template.replace("__ASSET__", json.dumps(model)), encoding="utf-8")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
