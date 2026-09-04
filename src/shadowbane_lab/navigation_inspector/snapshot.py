"""Bounded, replayable inspector state, independent of movement policy and rendering."""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

from .events import ContextEvent, DiagnosticEvent, MotionEvent, PlanEvent, RouteEvent

SCHEMA_VERSION = 1
MAX_CAPTURE_BYTES = 1_048_576
MAX_EVENTS = 256
MAX_TRAIL = 2048
MAX_TEXT = 512


def _number(value: object, name: str, *, minimum: float = -1e9) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or not minimum <= value <= 1e9:
        raise ValueError(f"{name} is outside the finite coordinate range")
    return float(value)


def _integer(value: object, name: str, maximum: int = (1 << 64) - 1) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be a bounded nonnegative integer")
    return value


def _text(value: object, name: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        raise ValueError(f"{name} must be bounded text")
    return value


def _record(value: object, cls: type) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {f.name for f in fields(cls)}:
        raise ValueError(f"invalid {cls.__name__} fields")
    return value


def _points(value: object, width: int, limit: int, name: str) -> tuple:
    if not isinstance(value, (list, tuple)) or len(value) > limit:
        raise ValueError(f"{name} exceeds its capacity")
    result = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != width:
            raise ValueError(f"invalid {name} point")
        result.append(tuple(_number(x, name) for x in point))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    process_id: int
    process_creation_filetime: int
    executable_sha256: str
    source_revision: str
    package_version: str
    extension_sha256: str

    def __post_init__(self) -> None:
        if _integer(self.process_id, "process_id", 0xFFFFFFFF) == 0:
            raise ValueError("process_id must be positive")
        if _integer(self.process_creation_filetime, "creation") == 0:
            raise ValueError("process creation identity is required")
        for name in ("executable_sha256", "source_revision", "extension_sha256"):
            value = getattr(self, name)
            size = 40 if name == "source_revision" else 64
            if value != "unavailable" and (
                not isinstance(value, str)
                or len(value) != size
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise ValueError(f"invalid {name}")
        _text(self.package_version, "package_version")


@dataclass(frozen=True, slots=True)
class Clearance:
    character_radius: float = 4.0
    movement_uncertainty: float = 1.0
    margin: float = 1.0
    provenance: str = "operator estimate; not measured collision dimensions"

    def __post_init__(self) -> None:
        for name in ("character_radius", "movement_uncertainty", "margin"):
            value = _number(getattr(self, name), name, minimum=0)
            if value > 1000:
                raise ValueError("clearance exceeds 1000 world units")
        _text(self.provenance, "clearance provenance")

    @property
    def radius(self) -> float:
        return self.character_radius + self.movement_uncertainty + self.margin


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    received_ms: int
    value: MotionEvent


@dataclass(frozen=True, slots=True)
class Snapshot:
    schema: int
    identity: SourceIdentity
    session_id: int
    sequence: int
    sampled_ms: int
    context: ContextEvent
    map_revision: int
    route_revision: int
    plan: PlanEvent | None
    route: RouteEvent | None
    active: MotionEvent | None
    events: tuple[RecordedEvent, ...]
    trail: tuple[tuple[float, float, float], ...]
    clearance: Clearance
    frozen: bool
    omitted_events: int
    omitted_trail: int
    dropped_observations: int
    coordinate_convention: str = (
        "LT/LG world units; world X=LT, Y=measured altitude, Z=-LG; "
        "alignment requires live acceptance"
    )

    def to_bytes(self) -> bytes:
        payload = json.dumps(asdict(self), allow_nan=False, separators=(",", ":")).encode()
        if len(payload) > MAX_CAPTURE_BYTES:
            raise ValueError("snapshot exceeds capture capacity")
        return payload

    def save(self, path: Path) -> None:
        """Called by the panel, never the render thread; refuse accidental overwrite."""
        with path.open("xb") as destination:
            destination.write(self.to_bytes())

    @classmethod
    def load(cls, path: Path) -> Snapshot:
        with path.open("rb") as source:
            return cls.from_bytes(source.read(MAX_CAPTURE_BYTES + 1))

    @classmethod
    def from_bytes(cls, payload: bytes) -> Snapshot:
        if not isinstance(payload, bytes) or len(payload) > MAX_CAPTURE_BYTES:
            raise ValueError("snapshot exceeds capture capacity")

        def unique(pairs: list) -> dict:
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate snapshot field")
                result[key] = value
            return result

        try:
            data = _record(json.loads(payload, object_pairs_hook=unique), cls)
        except (RecursionError, UnicodeError) as error:
            raise ValueError("invalid snapshot encoding") from error
        if type(data["schema"]) is not int or data["schema"] != SCHEMA_VERSION:
            raise ValueError("unsupported snapshot schema")
        for name in (
            "session_id",
            "sequence",
            "sampled_ms",
            "map_revision",
            "route_revision",
            "omitted_events",
            "omitted_trail",
            "dropped_observations",
        ):
            _integer(data[name], name)
        if not data["session_id"] or type(data["frozen"]) is not bool:
            raise ValueError("invalid snapshot session or freeze state")
        identity = SourceIdentity(**_record(data["identity"], SourceIdentity))
        clearance = Clearance(**_record(data["clearance"], Clearance))
        context = parse_context(data["context"])
        plan = parse_plan(data["plan"]) if data["plan"] is not None else None
        active = parse_motion(data["active"]) if data["active"] is not None else None
        route = parse_route(data["route"]) if data["route"] is not None else None
        events = data["events"]
        if not isinstance(events, list) or len(events) > MAX_EVENTS:
            raise ValueError("event history exceeds capacity")
        recorded = []
        for value in events:
            item = _record(value, RecordedEvent)
            recorded.append(
                RecordedEvent(
                    _integer(item["received_ms"], "received_ms"), parse_motion(item["value"])
                )
            )
        return cls(
            **{
                **data,
                "identity": identity,
                "clearance": clearance,
                "context": context,
                "plan": plan,
                "route": route,
                "active": active,
                "events": tuple(recorded),
                "trail": _points(data["trail"], 3, MAX_TRAIL, "trail"),
                "coordinate_convention": _text(data["coordinate_convention"], "coordinates"),
            }
        )


def parse_route(value: object) -> RouteEvent:
    data = _record(value, RouteEvent)
    if data["kind"] != "route":
        raise ValueError("invalid route kind")
    destinations = _points(data["destinations"], 3, 4096, "route destinations")
    if not destinations or any(point[2] < 0 for point in destinations):
        raise ValueError("invalid route destinations")
    return RouteEvent(
        "route",
        _text(data["plan_id"], "plan_id"),
        _points([data["start"]], 2, 1, "route start")[0],
        destinations,
        _integer(data["omitted_destinations"], "omitted destinations"),
    )


def parse_context(value: object) -> ContextEvent:
    data = _record(value, ContextEvent)
    if data["kind"] != "context":
        raise ValueError("invalid context kind")
    return ContextEvent(
        "context",
        _text(data["zone_token"], "zone", optional=True),
        _text(data["map_token"], "map"),
        _text(data["obstacle_provenance"], "obstacles"),
        _text(data["height_provenance"], "height"),
    )


def parse_motion(value: object) -> MotionEvent:
    data = _record(value, MotionEvent).copy()
    if data["kind"] != "motion":
        raise ValueError("invalid motion kind")
    for name in ("event", "plan_id", "reason"):
        data[name] = _text(data[name], name, optional=name == "reason")
    _integer(data["now_ms"], "now_ms")
    if data["waypoint_index"] is not None:
        _integer(data["waypoint_index"], "waypoint_index", 1_000_000)
    for name, width in (("position", 3), ("destination", 3), ("direction", 2)):
        if data[name] is not None:
            data[name] = _points([data[name]], width, 1, name)[0]
    if data["destination"] is not None and data["destination"][2] < 0:
        raise ValueError("negative arrival radius")
    return MotionEvent(**data)


def parse_plan(value: object) -> PlanEvent:
    data = _record(value, PlanEvent).copy()
    if data["kind"] != "plan" or data["mode"] not in ("complete", "frontier", "failed"):
        raise ValueError("invalid plan kind/mode")
    for name in (
        "planner_clearance_cells",
        "expanded_cells",
        "omitted_route_points",
        "omitted_map_cells",
    ):
        _integer(data[name], name)
    _number(data["total_cost"], "total_cost", minimum=0)
    if _number(data["cell_size"], "cell_size", minimum=0) == 0:
        raise ValueError("cell size must be positive")
    _text(data["failure_reason"], "failure_reason", optional=True)
    for name, width in (("start", 2), ("destination", 3)):
        data[name] = _points([data[name]], width, 1, name)[0]
    for name, width in (
        ("raw_path", 2),
        ("smoothed_path", 2),
        ("destinations", 3),
        ("physical_blocked", 2),
        ("learned_blocked", 2),
        ("costs", 3),
    ):
        data[name] = _points(data[name], width, 4096, name)
    for name in ("physical_blocked", "learned_blocked", "costs"):
        if any(x != int(x) or y != int(y) for x, y, *_ in data[name]):
            raise ValueError("map cell coordinates must be integers")
    if data["destination"][2] < 0 or any(p[2] < 0 for p in data["destinations"]):
        raise ValueError("negative arrival radius")
    if any(p[2] < 0 for p in data["costs"]):
        raise ValueError("negative traversal cost")
    return PlanEvent(**data)


class Collector:
    """Single worker-owned state. Producers only enqueue immutable owner events."""

    def __init__(
        self, identity: SourceIdentity, session_id: int, *, clearance: Clearance | None = None
    ):
        self.identity = identity
        self.session_id = session_id
        self.clearance = clearance or Clearance()
        self.context = ContextEvent("context", None, "unavailable", "unavailable")
        self.plan: PlanEvent | None = None
        self.route: RouteEvent | None = None
        self.active: MotionEvent | None = None
        self.events: deque[RecordedEvent] = deque(maxlen=MAX_EVENTS)
        self.trail: deque[tuple[float, float, float]] = deque(maxlen=MAX_TRAIL)
        self.map_revision = self.route_revision = self.sequence = 0
        self.omitted_events = self.omitted_trail = self.dropped_observations = 0
        self.sampled_ms = 0
        self.freeze_on_failure = True
        self.frozen: Snapshot | None = None

    def observe(self, event: DiagnosticEvent, received_ms: int) -> None:
        if isinstance(event, ContextEvent):
            event = parse_context(asdict(event))
            if event.zone_token != self.context.zone_token:
                self.plan = self.route = self.active = None
                self.events.clear()
                self.trail.clear()
                self.frozen = None
                self.omitted_events = self.omitted_trail = 0
                self.route_revision += 1
            if event != self.context:
                self.map_revision += 1
                self.context = event
        elif isinstance(event, PlanEvent):
            self.plan = parse_plan(asdict(event))
            self.route_revision += 1
        elif isinstance(event, RouteEvent):
            route = parse_route(asdict(event))
            if route != self.route:
                self.route = route
                self.route_revision += 1
        else:
            event = parse_motion(asdict(event))
            if event.event == "target_changed":
                self.route = self.plan = None
                self.route_revision += 1
            if event.position is not None or event.destination is not None:
                previous = self.active
                self.active = event
                if previous is not None and (
                    previous.plan_id == event.plan_id or event.plan_id == "runtime"
                ):
                    self.active = replace(
                        event,
                        plan_id=previous.plan_id if event.plan_id == "runtime" else event.plan_id,
                        destination=event.destination or previous.destination,
                        waypoint_index=(
                            event.waypoint_index
                            if event.waypoint_index is not None
                            else previous.waypoint_index
                        ),
                    )
            if event.position is not None and (not self.trail or self.trail[-1] != event.position):
                self.omitted_trail += int(len(self.trail) == MAX_TRAIL)
                self.trail.append(event.position)
            if event.event != "observation":
                self.omitted_events += int(len(self.events) == MAX_EVENTS)
                self.events.append(RecordedEvent(received_ms, event))
        self.sequence += 1
        self.sampled_ms = received_ms
        if isinstance(event, MotionEvent) and event.event == "failure" and self.freeze_on_failure:
            self.freeze()

    def snapshot(self) -> Snapshot:
        if self.frozen is not None:
            return self.frozen
        return self._snapshot(False)

    def _snapshot(self, frozen: bool) -> Snapshot:
        return Snapshot(
            SCHEMA_VERSION,
            self.identity,
            self.session_id,
            self.sequence,
            self.sampled_ms,
            self.context,
            self.map_revision,
            self.route_revision,
            self.plan,
            self.route,
            self.active,
            tuple(self.events),
            tuple(self.trail),
            self.clearance,
            frozen,
            self.omitted_events,
            self.omitted_trail,
            self.dropped_observations,
        )

    def freeze(self) -> None:
        if self.frozen is None:
            self.frozen = self._snapshot(True)

    def resume(self) -> None:
        self.frozen = None
