"""Shared CLI presentation helpers."""

from __future__ import annotations

import json
import sys


def _error(message: str, *, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    else:
        print(message, file=sys.stderr)
    return 2
