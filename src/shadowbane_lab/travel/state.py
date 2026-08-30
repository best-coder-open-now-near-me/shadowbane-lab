"""Durable local state for resuming the last explicit travel destination."""

from __future__ import annotations

import json
import os
from pathlib import Path

from shadowbane_lab.travel.model import TravelDestination

_SCHEMA_VERSION = 1


class TravelDestinationStateError(ValueError):
    """Raised when remembered travel state cannot be loaded or saved safely."""


def resolve_travel_destination(
    state_path: Path,
    *,
    lt: float | None,
    lg: float | None,
    radius: float | None,
    default_arrival_radius: float = 75.0,
) -> TravelDestination:
    """Resolve explicit coordinates or load the last destination for bare ``go``."""

    if not isinstance(state_path, Path):
        raise TravelDestinationStateError("state_path must be Path")
    if (lt is None) != (lg is None):
        raise TravelDestinationStateError("LT and LG must be supplied together")
    if lt is None:
        previous = load_travel_destination(state_path)
        destination = (
            previous if radius is None else TravelDestination(previous.lt, previous.lg, radius)
        )
        if destination != previous:
            save_travel_destination(state_path, destination)
        return destination

    destination = TravelDestination(
        lt,
        lg,
        default_arrival_radius if radius is None else radius,
    )
    save_travel_destination(state_path, destination)
    return destination


def load_travel_destination(state_path: Path) -> TravelDestination:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TravelDestinationStateError(
            "bare go has no remembered destination; use go LT LG first"
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TravelDestinationStateError(f"could not read remembered destination: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != _SCHEMA_VERSION:
        raise TravelDestinationStateError("remembered destination has an unsupported schema")
    try:
        lt = _json_number(payload, "lt")
        lg = _json_number(payload, "lg")
        radius = _json_number(payload, "arrival_radius")
        return TravelDestination(lt, lg, radius)
    except ValueError as exc:
        raise TravelDestinationStateError(f"remembered destination is invalid: {exc}") from exc


def save_travel_destination(
    state_path: Path,
    destination: TravelDestination,
) -> None:
    if not isinstance(state_path, Path):
        raise TravelDestinationStateError("state_path must be Path")
    if not isinstance(destination, TravelDestination):
        raise TravelDestinationStateError("destination must be TravelDestination")
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "lt": destination.lt,
        "lg": destination.lg,
        "arrival_radius": destination.arrival_radius,
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
        raise TravelDestinationStateError(f"could not save remembered destination: {exc}") from exc
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _json_number(payload: dict[str, object], field_name: str) -> float:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    return float(value)
