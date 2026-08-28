"""Durable exact obstacles learned from live movement failures."""

from __future__ import annotations

import json
import os
from math import isfinite
from pathlib import Path

from shadowbane_lab.travel.pathfinding import NavigationCell, SparseNavigationMap

_SCHEMA_VERSION = 1
_MAXIMUM_LEARNED_CELLS = 50_000


class LearnedNavigationStateError(ValueError):
    """Raised when learned navigation state cannot be loaded or saved safely."""


def load_learned_navigation_map(
    state_path: Path,
    *,
    cell_size: float = 20.0,
) -> SparseNavigationMap:
    """Load exact learned blockers, or create an empty map before the first route."""

    if not isinstance(state_path, Path):
        raise LearnedNavigationStateError("state_path must be Path")
    _validate_cell_size(cell_size)
    navigation_map = SparseNavigationMap(cell_size=cell_size)
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return navigation_map
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LearnedNavigationStateError(
            f"could not read learned navigation state: {exc}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA_VERSION:
        raise LearnedNavigationStateError("learned navigation state has an unsupported schema")
    stored_cell_size = payload.get("cell_size")
    if (
        isinstance(stored_cell_size, bool)
        or not isinstance(stored_cell_size, (int, float))
        or not isfinite(stored_cell_size)
        or float(stored_cell_size) != float(cell_size)
    ):
        raise LearnedNavigationStateError(
            "learned navigation state targets a different navigation cell size"
        )
    cells = payload.get("blocked_cells")
    if not isinstance(cells, list):
        raise LearnedNavigationStateError("learned navigation blocked_cells must be an array")
    if len(cells) > _MAXIMUM_LEARNED_CELLS:
        raise LearnedNavigationStateError("learned navigation state exceeds its cell limit")
    try:
        restored = {_parse_cell(item) for item in cells}
    except ValueError as exc:
        raise LearnedNavigationStateError(
            f"learned navigation state contains an invalid cell: {exc}"
        ) from exc
    if len(restored) != len(cells):
        raise LearnedNavigationStateError("learned navigation blocked_cells must be unique")
    for cell in restored:
        navigation_map.mark_learned_blocked(cell)
    return navigation_map


def save_learned_navigation_map(
    state_path: Path,
    navigation_map: SparseNavigationMap,
) -> None:
    """Atomically persist only live-learned blockers, excluding derived terrain costs."""

    if not isinstance(state_path, Path):
        raise LearnedNavigationStateError("state_path must be Path")
    if not isinstance(navigation_map, SparseNavigationMap):
        raise LearnedNavigationStateError("navigation_map must be SparseNavigationMap")
    cells = sorted(navigation_map.learned_blocked)
    if len(cells) > _MAXIMUM_LEARNED_CELLS:
        raise LearnedNavigationStateError("learned navigation state exceeds its cell limit")
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "cell_size": navigation_map.cell_size,
        "blocked_cells": [{"x": cell.x, "y": cell.y} for cell in cells],
    }
    temporary_path = state_path.with_name(f".{state_path.name}.{os.getpid()}.tmp")
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(state_path)
    except OSError as exc:
        raise LearnedNavigationStateError(
            f"could not save learned navigation state: {exc}"
        ) from exc
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _parse_cell(value: object) -> NavigationCell:
    if not isinstance(value, dict):
        raise ValueError("cell must be an object")
    if set(value) != {"x", "y"}:
        raise ValueError("cell must contain only x and y")
    x = value["x"]
    y = value["y"]
    if isinstance(x, bool) or not isinstance(x, int):
        raise ValueError("cell x must be an integer")
    if isinstance(y, bool) or not isinstance(y, int):
        raise ValueError("cell y must be an integer")
    return NavigationCell(x, y)


def _validate_cell_size(value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0
    ):
        raise LearnedNavigationStateError("cell_size must be finite and positive")
