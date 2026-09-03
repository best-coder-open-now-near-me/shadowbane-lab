#!/usr/bin/env python3
"""Compatibility launcher for the read-only WonderBane texture exporter."""

from __future__ import annotations

import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _REPOSITORY_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))


def main(arguments: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if arguments is None else arguments)
    from shadowbane_lab.client_extension import texture_export

    module_main = getattr(texture_export, "main", None)
    if callable(module_main):
        return int(module_main(values))

    if not values:
        raise SystemExit("expected list, export, or samples")
    command = values[0]
    translated = {
        "list": "list-textures",
        "export": "export-texture",
        "samples": "export-texture-samples",
    }.get(command)
    if translated is None:
        raise SystemExit(f"unsupported texture export command: {command}")
    from shadowbane_lab.client_extension.__main__ import main as extension_main

    return int(extension_main((translated, *values[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
