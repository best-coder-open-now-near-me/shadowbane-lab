#!/usr/bin/env python3
"""Read-only WonderBane texture-cache listing and PNG export."""

from __future__ import annotations

import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _REPOSITORY_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from shadowbane_lab.client_extension.texture_export import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
