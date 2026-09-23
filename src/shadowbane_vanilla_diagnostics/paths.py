"""Filesystem-aware path comparisons for the Windows-only collector."""

from __future__ import annotations

import os
from pathlib import Path


def same_windows_path(left: str | Path, right: str | Path) -> bool:
    """Compare aliases without treating identical content as identical paths.

    Windows realpath expands existing 8.3 ancestors, including when the final
    output directory does not exist yet. This comparison does not prove file
    existence, process lifetime, package containment, or executable integrity;
    those checks remain with their respective owners.
    """
    left_text, right_text = str(left), str(right)
    if not left_text or not right_text or "\0" in left_text or "\0" in right_text:
        return False
    try:
        # Avoid filesystem/network work for already identical spellings.
        if os.path.normcase(os.path.abspath(left_text)) == os.path.normcase(
            os.path.abspath(right_text)
        ):
            return True
        return os.path.normcase(os.path.realpath(left_text)) == os.path.normcase(
            os.path.realpath(right_text)
        )
    except (OSError, ValueError, RuntimeError):
        return False
