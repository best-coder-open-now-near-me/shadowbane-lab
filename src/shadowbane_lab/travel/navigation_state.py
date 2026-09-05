"""Durable exact obstacles learned from live movement failures."""

from __future__ import annotations

import json
from math import isfinite
from pathlib import Path

from shadowbane_lab.record_store import exclusive_record_lock, publish_atomic_record
from shadowbane_lab.travel.pathfinding import NavigationCell, SparseNavigationMap

_SCHEMA_VERSION = 2
_SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})
_MAXIMUM_LEARNED_CELLS = 50_000
_MAXIMUM_REFINED_CELLS = 200_000


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
    if not isinstance(payload, dict) or payload.get("schema_version") not in (
        _SUPPORTED_SCHEMA_VERSIONS
    ):
        raise LearnedNavigationStateError("learned navigation state has an unsupported schema")
    schema_version = payload["schema_version"]
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
    if schema_version == 1:
        for cell in restored:
            navigation_map.mark_learned_blocked(cell)
        return navigation_map

    stored_refined_cell_size = payload.get("refined_cell_size")
    if (
        isinstance(stored_refined_cell_size, bool)
        or not isinstance(stored_refined_cell_size, (int, float))
        or not isfinite(stored_refined_cell_size)
        or float(stored_refined_cell_size) != navigation_map.refined_cell_size
    ):
        raise LearnedNavigationStateError(
            "learned navigation state targets a different refined cell size"
        )
    refined_cells = payload.get("refined_blocked_cells")
    if not isinstance(refined_cells, list):
        raise LearnedNavigationStateError(
            "learned navigation refined_blocked_cells must be an array"
        )
    if len(refined_cells) > _MAXIMUM_REFINED_CELLS:
        raise LearnedNavigationStateError("learned navigation state exceeds its refined cell limit")
    try:
        restored_refined = {_parse_cell(item) for item in refined_cells}
    except ValueError as exc:
        raise LearnedNavigationStateError(
            f"learned navigation state contains an invalid refined cell: {exc}"
        ) from exc
    if len(restored_refined) != len(refined_cells):
        raise LearnedNavigationStateError("learned navigation refined_blocked_cells must be unique")
    refined_by_parent: dict[NavigationCell, list[NavigationCell]] = {}
    factor = navigation_map.refinement_factor
    for refined_cell in restored_refined:
        parent = NavigationCell(refined_cell.x // factor, refined_cell.y // factor)
        if parent not in restored:
            raise LearnedNavigationStateError(
                "refined learned blocker has no matching coarse blocker"
            )
        refined_by_parent.setdefault(parent, []).append(refined_cell)
    for cell in restored:
        precise = refined_by_parent.get(cell)
        if not precise:
            navigation_map.mark_learned_blocked(cell)
            continue
        for refined_cell in precise:
            navigation_map.mark_refined_learned_blocked(cell, refined_cell)
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
    # The lock owns read/merge/write across worker processes, not just replacement.
    # Learned evidence is monotonic; a stale independently loaded map cannot erase
    # another worker's observations. Atomic replacement preserves the prior complete
    # generation on failure; the OS releases the lock if a writer crashes.
    try:
        with exclusive_record_lock(state_path.with_name(f".{state_path.name}.lock")):
            prior = load_learned_navigation_map(state_path, cell_size=navigation_map.cell_size)
            if prior.refined_cell_size != navigation_map.refined_cell_size:
                raise LearnedNavigationStateError("incompatible refined navigation cell size")
            cells = sorted(prior.learned_blocked | navigation_map.learned_blocked)
            refined_cells = sorted(
                prior.refined_learned_blocked | navigation_map.refined_learned_blocked
            )
            if len(cells) > _MAXIMUM_LEARNED_CELLS:
                raise LearnedNavigationStateError("learned navigation state exceeds its cell limit")
            if len(refined_cells) > _MAXIMUM_REFINED_CELLS:
                raise LearnedNavigationStateError(
                    "learned navigation exceeds its refined cell limit"
                )
            payload = {
                "schema_version": _SCHEMA_VERSION,
                "cell_size": navigation_map.cell_size,
                "refined_cell_size": navigation_map.refined_cell_size,
                "blocked_cells": [{"x": cell.x, "y": cell.y} for cell in cells],
                "refined_blocked_cells": [{"x": cell.x, "y": cell.y} for cell in refined_cells],
            }
            publish_atomic_record(
                state_path,
                (json.dumps(payload, sort_keys=True) + "\n").encode(),
                temporary_label="learned-navigation",
            )
            # Feed merged observations back into the active planner only after
            # publication succeeds. Structural/cost data stays local to its owner.
            factor = navigation_map.refinement_factor
            for cell in refined_cells:
                parent = NavigationCell(cell.x // factor, cell.y // factor)
                navigation_map.mark_refined_learned_blocked(parent, cell)
    except (OSError, TimeoutError) as exc:
        raise LearnedNavigationStateError(
            f"could not save learned navigation state: {exc}"
        ) from exc


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
