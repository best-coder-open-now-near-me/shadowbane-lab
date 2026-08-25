"""Strict JSON loading for the versioned simulator-gap ledger."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from shadowbane_lab.differential.compare import (
    DifferenceCategory,
    GapEntry,
    GapLedger,
    GapStatus,
)

GAP_LEDGER_SCHEMA_VERSION = 1


class GapLedgerLoadError(ValueError):
    """Raised when a gap ledger is malformed or unsupported."""


def load_bundled_gap_ledger() -> GapLedger:
    resource = files("shadowbane_lab.differential").joinpath("data/simulator_gap_ledger_v1.json")
    return load_gap_ledger_text(resource.read_text(encoding="utf-8"))


def load_gap_ledger(path: str | Path) -> GapLedger:
    return load_gap_ledger_text(Path(path).read_text(encoding="utf-8"))


def load_gap_ledger_text(text: str) -> GapLedger:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GapLedgerLoadError("gap ledger is not valid JSON") from exc
    try:
        data = _mapping(raw, "gap ledger")
        if _integer(data, "schema_version") != GAP_LEDGER_SCHEMA_VERSION:
            raise GapLedgerLoadError("unsupported gap ledger schema version")
        return GapLedger(
            tuple(
                GapEntry(
                    gap_id=_string(item, "gap_id"),
                    status=GapStatus(_string(item, "status")),
                    category=DifferenceCategory(_string(item, "category")),
                    scenario_pattern=_string(item, "scenario_pattern"),
                    path_pattern=_string(item, "path_pattern"),
                    description=_string(item, "description"),
                    action_key=_nullable_string(item, "action_key"),
                    max_absolute_delta=_nullable_number(item, "max_absolute_delta"),
                    evidence_trace_ids=tuple(_strings(item, "evidence_trace_ids")),
                )
                for item in _objects(data, "entries")
            )
        )
    except GapLedgerLoadError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, KeyError):
            raise GapLedgerLoadError(f"missing required field: {exc.args[0]}") from exc
        raise GapLedgerLoadError(str(exc)) from exc


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GapLedgerLoadError(f"{field_name} must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(data: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = data[key]
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise GapLedgerLoadError(f"{key} must be an array")
    return value


def _objects(data: Mapping[str, Any], key: str) -> tuple[Mapping[str, Any], ...]:
    return tuple(_mapping(value, f"{key} item") for value in _sequence(data, key))


def _string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise GapLedgerLoadError(f"{key} must be a non-empty string")
    return value


def _nullable_string(data: Mapping[str, Any], key: str) -> str | None:
    value = data[key]
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise GapLedgerLoadError(f"{key} must be a non-empty string or null")
    return cast(str | None, value)


def _integer(data: Mapping[str, Any], key: str) -> int:
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise GapLedgerLoadError(f"{key} must be an integer")
    return value


def _nullable_number(data: Mapping[str, Any], key: str) -> float | None:
    value = data[key]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GapLedgerLoadError(f"{key} must be a number or null")
    return float(value)


def _strings(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    values = _sequence(data, key)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise GapLedgerLoadError(f"{key} must contain non-empty strings")
    return tuple(cast(str, value) for value in values)
