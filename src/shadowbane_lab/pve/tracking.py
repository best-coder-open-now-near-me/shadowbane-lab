"""Player-tracking intent, query cadence and copied awareness; never attack authority."""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, replace


def _uint(value, bits=64, *, positive=False):
    if type(value) is not int or not int(positive) <= value < 2**bits:
        raise ValueError("invalid tracking integer")


def _key(value):
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError("tracking object key must be a pair")
    for part in value:
        _uint(part, 32)
    if not any(value):
        raise ValueError("tracking object key is empty")


@dataclass(frozen=True, slots=True)
class TrackingSettings:
    enabled: bool = False
    refresh_interval_seconds: int = 10

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("tracking enabled must be boolean")
        if (type(self.refresh_interval_seconds) is not int
                or not 1 <= self.refresh_interval_seconds <= 3600):
            raise ValueError("tracking refresh interval must be 1..3600 seconds")

    def as_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("invalid tracking settings fields")
        return cls(**value)


@dataclass(frozen=True, slots=True)
class TrackingActor:
    process_id: int
    process_creation_filetime_utc: int
    scene_epoch: int
    object_key: tuple[int, int]

    def __post_init__(self):
        _uint(self.process_id, 32, positive=True)
        _uint(self.process_creation_filetime_utc, positive=True)
        _uint(self.scene_epoch, positive=True)
        _key(self.object_key)


@dataclass(frozen=True, slots=True)
class TrackingContact:
    object_key: tuple[int, int]
    name: str
    flags_raw: int

    def __post_init__(self):
        _key(self.object_key)
        _uint(self.flags_raw, 32)
        if (not isinstance(self.name, str) or not self.name or len(self.name) > 256
                or any(ord(c) < 32 for c in self.name)):
            raise ValueError("invalid tracking contact name")


@dataclass(frozen=True, slots=True)
class TrackingStatus:
    enabled: bool = False
    state: str = "disabled"
    current: bool = False
    generation: int | None = None
    observed_at: float | None = None
    response_age_seconds: float | None = None
    contacts: tuple[TrackingContact, ...] = ()
    query_state: str = "idle"
    detail: str | None = None
    capture_incomplete: bool = False
    actor: TrackingActor | None = None
    freshness_seconds: int = 20

    def __post_init__(self):
        if any(type(v) is not bool for v in (self.enabled, self.current, self.capture_incomplete)):
            raise ValueError("invalid tracking status flags")
        if type(self.freshness_seconds) is not int or not 2 <= self.freshness_seconds <= 7200:
            raise ValueError("invalid tracking freshness bound")
        if self.state not in {"disabled", "waiting", "current", "stale", "unavailable"}:
            raise ValueError("invalid tracking state")
        if self.query_state not in {"idle", "queued", "not_ready", "unknown"}:
            raise ValueError("invalid tracking query state")
        if self.current != (self.state == "current") or self.enabled == (self.state == "disabled"):
            raise ValueError("contradictory tracking status")
        if not isinstance(self.contacts, tuple) or len(self.contacts) > 256 or any(
                not isinstance(v, TrackingContact) for v in self.contacts):
            raise ValueError("invalid tracking contacts")
        if self.actor is not None and not isinstance(self.actor, TrackingActor):
            raise ValueError("invalid tracking actor")
        if self.detail is not None and (not isinstance(self.detail, str) or len(self.detail) > 256
                                       or any(ord(c) < 32 for c in self.detail)):
            raise ValueError("invalid tracking detail")
        if self.generation is not None:
            _uint(self.generation, positive=True)
        for value in (self.observed_at, self.response_age_seconds):
            if value is not None and (type(value) not in (int, float)
                                      or not math.isfinite(value) or value < 0):
                raise ValueError("invalid tracking observation time")
        if self.generation is None:
            if (self.contacts or self.observed_at is not None
                    or self.response_age_seconds is not None):
                raise ValueError("tracking contacts require an observed generation")
        elif self.actor is None or self.observed_at is None or self.response_age_seconds is None:
            raise ValueError("tracking generation requires exact actor and observation time")
        if self.current and self.generation is None:
            raise ValueError("current tracking requires an observed native response")

    def at(self, now):
        """Age copied awareness for presentation without a native read or new response."""
        if self.observed_at is None:
            return self
        if type(now) not in (int, float) or not math.isfinite(now) or now < self.observed_at:
            return replace(self, current=False, state="unavailable")
        age = self.response_age_seconds + now - self.observed_at
        current = self.current and age <= self.freshness_seconds
        return replace(self, observed_at=now, response_age_seconds=age, current=current,
                       state="stale" if self.state == "current" and not current else self.state)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("invalid tracking status fields")
        values = dict(value)
        contacts = values["contacts"]
        if not isinstance(contacts, (list, tuple)):
            raise ValueError("invalid tracking contacts")
        values["contacts"] = tuple(TrackingContact(
            tuple(v["object_key"]), v["name"], v["flags_raw"],
        ) if isinstance(v, dict) and set(v) == set(TrackingContact.__dataclass_fields__)
            else _invalid_contact() for v in contacts)
        actor = values["actor"]
        if actor is not None:
            if not isinstance(actor, dict) or set(actor) != set(TrackingActor.__dataclass_fields__):
                raise ValueError("invalid tracking actor fields")
            values["actor"] = TrackingActor(**{**actor, "object_key": tuple(actor["object_key"])})
        return cls(**values)


def _invalid_contact():
    raise ValueError("invalid tracking contact fields")


@dataclass(frozen=True, slots=True)
class TrackingQueryResult:
    state: str
    detail: str | None = None

    def __post_init__(self):
        if self.state not in {"queued", "not_ready", "unknown"}:
            raise ValueError("invalid tracking query result")


class TrackingActorChanged(RuntimeError):
    """A complete native publication proves this owner's scene/actor changed."""


class TrackingScheduler:
    """One query at a time; native returned records alone supply awareness.

    The refresh clock schedules requests, never creates a response. A missing
    acknowledgement polls the original immutable command through the caller.
    Native admission refusals are reported and retried on the next request slot.
    Later complete native records remain useful despite a reported history gap.
    """

    def __init__(self, settings, ability, actor, reader, query, *, tick_clock,
                 clock=time.monotonic, wall_clock=time.time):
        if not isinstance(settings, TrackingSettings) or not settings.enabled:
            raise ValueError("tracking scheduler requires enabled saved intent")
        from shadowbane_lab.client_observation.native_tracking_ability import NativeTrackingAbility
        if not isinstance(ability, NativeTrackingAbility) or not isinstance(actor, TrackingActor):
            raise ValueError("tracking scheduler requires typed learned ability and actor")
        self.settings, self.ability, self.actor = settings, ability, actor
        self.reader, self.query = reader, query
        self.tick_clock, self.clock, self.wall_clock = tick_clock, clock, wall_clock
        self._due = 0.0
        self._query = TrackingQueryResult("not_ready", "awaiting first query")
        self._generation = self._tick = None
        self._contacts = ()
        self._incomplete = False
        self.status = TrackingStatus(enabled=True, state="waiting", actor=actor)

    def step(self, *, allow_new=True):
        error = None
        try:
            batch = self.reader.drain()
            if (batch["process_id"], batch["process_creation_filetime_utc"]) != (
                    self.actor.process_id, self.actor.process_creation_filetime_utc):
                raise ValueError("tracking publication belongs to another process")
            if batch["stopped"]:
                raise ValueError("tracking publication stopped")
            self._incomplete |= bool(batch["capture_incomplete"] or batch["missed_records"])
            # Initial retained history has no new observation in this capture.
            for record in (() if batch["initial_history"] else batch["records"]):
                if record["stage"] != "returned" or record["flags"] != 7:
                    continue
                generation, tick = record["processing_generation"], record["tick_ms"]
                _uint(generation, positive=True)
                _uint(tick)
                if self._generation is not None and generation <= self._generation:
                    continue
                if (record["scene_epoch"] != self.actor.scene_epoch
                        or tuple(record["local"]) != self.actor.object_key):
                    self.status = replace(self.status, state="unavailable", current=False,
                                          detail="tracking scene or actor changed")
                    raise TrackingActorChanged("tracking scene or actor changed")
                if record["payload"]["power_id"] != self.ability.power_id:
                    continue
                contacts = tuple(TrackingContact(tuple(v["object_key"]), v["name"], v["flags_raw"])
                                 for v in record["payload"]["contacts"])
                if len(contacts) > 256:
                    raise ValueError("tracking contact count exceeds bound")
                self._generation, self._tick, self._contacts = generation, tick, contacts
        except TrackingActorChanged:
            raise
        except Exception as exc:
            self._incomplete = True
            error = f"tracking observation unavailable:{type(exc).__name__}"
        now = self.clock()
        if self._query.state == "unknown" or (allow_new and now >= self._due):
            try:
                result = self.query(self.ability.power_id, allow_new=allow_new and now >= self._due)
                if not isinstance(result, TrackingQueryResult):
                    raise TypeError("untyped tracking query result")
                self._query = result
            except TrackingActorChanged:
                self.status = replace(self.status, state="unavailable", current=False,
                                      detail="tracking native owner retired")
                raise
            except Exception as exc:
                self._query = TrackingQueryResult("unknown", f"tracking query:{type(exc).__name__}")
            self._due = now + self.settings.refresh_interval_seconds
        age = None
        if self._tick is not None:
            tick_now = self.tick_clock()
            if tick_now >= self._tick:
                age = (tick_now - self._tick) / 1000
            else:
                error = "tracking response clock is unavailable"
        current = bool(age is not None
                       and age <= self.settings.refresh_interval_seconds * 2 and not error)
        state = ("unavailable" if error else "current" if current else
                 "stale" if self._generation is not None else "waiting")
        # A clock fault cannot create fresh time or contacts without a timestamp.
        generation = self._generation if age is not None else None
        self.status = TrackingStatus(
            enabled=True, state=state, current=current, generation=generation,
            observed_at=None if age is None else self.wall_clock(),
            response_age_seconds=age, contacts=self._contacts if generation is not None else (),
            query_state=self._query.state, detail=error or self._query.detail,
            capture_incomplete=self._incomplete, actor=self.actor,
            freshness_seconds=self.settings.refresh_interval_seconds * 2,
        )
        return self.status
