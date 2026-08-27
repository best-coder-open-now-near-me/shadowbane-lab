"""Compile live PvE trace evidence into simulator-consumable observations."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from statistics import fmean, median

from shadowbane_lab.pve.evidence import (
    load_pve_trace_evidence,
    validate_pve_trace_evidence,
)

PVE_COMBAT_CALIBRATION_SCHEMA_VERSION = 1
_SHADOW_TOUCH = "shadowbane.assassin.shadow_touch"


class PvECombatCalibrationError(ValueError):
    """Raised when PvE evidence cannot produce a valid combat calibration."""


@dataclass(frozen=True, slots=True)
class ObservedSampleSummary:
    count: int
    minimum: float
    maximum: float
    mean: float
    median: float
    histogram: tuple[tuple[float, int], ...]

    def __post_init__(self) -> None:
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count <= 0:
            raise ValueError("observed sample count must be positive")
        values = (self.minimum, self.maximum, self.mean, self.median)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            for value in values
        ):
            raise ValueError("observed sample statistics must be finite numbers")
        if not self.minimum <= self.median <= self.maximum:
            raise ValueError("observed sample median must lie within its range")
        if not self.minimum <= self.mean <= self.maximum:
            raise ValueError("observed sample mean must lie within its range")
        if (
            not self.histogram
            or sum(item[1] for item in self.histogram) != self.count
            or tuple(sorted(self.histogram)) != self.histogram
        ):
            raise ValueError("observed sample histogram must be sorted and complete")
        for value, frequency in self.histogram:
            if not isfinite(value) or frequency <= 0:
                raise ValueError("observed sample histogram entries must be valid")

    @classmethod
    def from_samples(cls, samples: Sequence[float]) -> ObservedSampleSummary | None:
        values = tuple(float(item) for item in samples)
        if not values:
            return None
        if any(not isfinite(item) for item in values):
            raise PvECombatCalibrationError("observed samples must be finite")
        counts = Counter(values)
        return cls(
            count=len(values),
            minimum=min(values),
            maximum=max(values),
            mean=fmean(values),
            median=float(median(values)),
            histogram=tuple(sorted(counts.items())),
        )

    @classmethod
    def from_dict(cls, payload: object) -> ObservedSampleSummary:
        data = _mapping(payload, "sample summary")
        histogram = data.get("histogram")
        if not isinstance(histogram, list):
            raise PvECombatCalibrationError("sample histogram must be an array")
        parsed_histogram: list[tuple[float, int]] = []
        for item in histogram:
            entry = _mapping(item, "sample histogram entry")
            parsed_histogram.append(
                (_number(entry, "value"), _integer(entry, "count", minimum=1))
            )
        try:
            return cls(
                count=_integer(data, "count", minimum=1),
                minimum=_number(data, "minimum"),
                maximum=_number(data, "maximum"),
                mean=_number(data, "mean"),
                median=_number(data, "median"),
                histogram=tuple(parsed_histogram),
            )
        except ValueError as exc:
            raise PvECombatCalibrationError(str(exc)) from exc

    def as_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "mean": self.mean,
            "median": self.median,
            "histogram": [
                {"value": value, "count": count}
                for value, count in self.histogram
            ],
        }


@dataclass(frozen=True, slots=True)
class PvECombatCalibration:
    profile_id: str
    source_trace_sha256s: tuple[str, ...]
    executable_sha256s: tuple[str, ...]
    policies: tuple[str, ...]
    confirmed_kills: int
    player_hits: int
    player_misses: int
    target_hits: int
    target_misses: int
    target_maximum_health: ObservedSampleSummary | None
    player_damage: ObservedSampleSummary | None
    target_damage: ObservedSampleSummary | None
    player_attack_interval_ms: ObservedSampleSummary | None
    target_attack_interval_ms: ObservedSampleSummary | None
    experience_reward: ObservedSampleSummary | None
    starting_player_health: ObservedSampleSummary | None
    starting_player_mana: ObservedSampleSummary | None
    starting_player_stamina: ObservedSampleSummary | None
    engagement_planar_distance: ObservedSampleSummary | None
    shadow_touch_mana_delta: ObservedSampleSummary | None
    native_target_health_decrease: ObservedSampleSummary | None
    native_target_health_decrease_interval_ms: ObservedSampleSummary | None
    native_player_health_decrease: ObservedSampleSummary | None
    native_player_health_decrease_interval_ms: ObservedSampleSummary | None
    limitations: tuple[str, ...]
    schema_version: int = PVE_COMBAT_CALIBRATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("calibration profile_id must be non-empty")
        for values, field_name in (
            (self.source_trace_sha256s, "source_trace_sha256s"),
            (self.executable_sha256s, "executable_sha256s"),
            (self.policies, "policies"),
            (self.limitations, "limitations"),
        ):
            if not values or any(not isinstance(item, str) or not item.strip() for item in values):
                raise ValueError(f"calibration {field_name} must contain strings")
            if len(values) != len(set(values)):
                raise ValueError(f"calibration {field_name} must be unique")
        if any(not _is_sha256(item) for item in self.source_trace_sha256s):
            raise ValueError("source trace hashes must be SHA-256 digests")
        if any(not _is_sha256(item) for item in self.executable_sha256s):
            raise ValueError("executable hashes must be SHA-256 digests")
        for value, field_name in (
            (self.confirmed_kills, "confirmed_kills"),
            (self.player_hits, "player_hits"),
            (self.player_misses, "player_misses"),
            (self.target_hits, "target_hits"),
            (self.target_misses, "target_misses"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"calibration {field_name} must be non-negative")
        if self.schema_version != PVE_COMBAT_CALIBRATION_SCHEMA_VERSION:
            raise ValueError("unsupported PvE combat calibration schema")

    @property
    def player_hit_rate(self) -> float | None:
        opportunities = self.player_hits + self.player_misses
        return None if opportunities == 0 else self.player_hits / opportunities

    @property
    def target_hit_rate(self) -> float | None:
        opportunities = self.target_hits + self.target_misses
        return None if opportunities == 0 else self.target_hits / opportunities

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "source_trace_sha256s": list(self.source_trace_sha256s),
            "executable_sha256s": list(self.executable_sha256s),
            "policies": list(self.policies),
            "confirmed_kills": self.confirmed_kills,
            "player_attacks": {
                "hits": self.player_hits,
                "misses": self.player_misses,
                "hit_rate": self.player_hit_rate,
                "damage": _summary_dict(self.player_damage),
                "interval_ms": _summary_dict(self.player_attack_interval_ms),
            },
            "target_attacks": {
                "hits": self.target_hits,
                "misses": self.target_misses,
                "hit_rate": self.target_hit_rate,
                "damage": _summary_dict(self.target_damage),
                "interval_ms": _summary_dict(self.target_attack_interval_ms),
            },
            "target_maximum_health": _summary_dict(self.target_maximum_health),
            "experience_reward": _summary_dict(self.experience_reward),
            "starting_player": {
                "health": _summary_dict(self.starting_player_health),
                "mana": _summary_dict(self.starting_player_mana),
                "stamina": _summary_dict(self.starting_player_stamina),
            },
            "engagement_planar_distance": _summary_dict(
                self.engagement_planar_distance
            ),
            "shadow_touch_mana_delta": _summary_dict(self.shadow_touch_mana_delta),
            "native_health_changes": {
                "target_decrease": _summary_dict(
                    self.native_target_health_decrease
                ),
                "target_decrease_interval_ms": _summary_dict(
                    self.native_target_health_decrease_interval_ms
                ),
                "player_decrease": _summary_dict(
                    self.native_player_health_decrease
                ),
                "player_decrease_interval_ms": _summary_dict(
                    self.native_player_health_decrease_interval_ms
                ),
            },
            "limitations": list(self.limitations),
        }


def compile_pve_combat_calibration(
    evidence_payloads: Sequence[Mapping[str, object]],
) -> PvECombatCalibration:
    if not evidence_payloads:
        raise PvECombatCalibrationError("at least one PvE evidence artifact is required")
    trace_hashes: list[str] = []
    executable_hashes: set[str] = set()
    policies: set[str] = set()
    confirmed_kills = 0
    player_hits = 0
    player_misses = 0
    target_hits = 0
    target_misses = 0
    target_health_samples: list[float] = []
    player_damage_samples: list[float] = []
    target_damage_samples: list[float] = []
    player_intervals: list[float] = []
    target_intervals: list[float] = []
    experience_samples: list[float] = []
    starting_health: list[float] = []
    starting_mana: list[float] = []
    starting_stamina: list[float] = []
    engagement_distances: list[float] = []
    shadow_touch_deltas: list[float] = []
    native_target_decreases: list[float] = []
    native_target_decrease_intervals: list[float] = []
    native_player_decreases: list[float] = []
    native_player_decrease_intervals: list[float] = []
    same_poll_opportunities = 0

    for payload_index, raw_payload in enumerate(evidence_payloads):
        payload = validate_pve_trace_evidence(dict(raw_payload))
        canonical = json.dumps(
            payload,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        trace_hash = hashlib.sha256(canonical).hexdigest()
        if trace_hash in trace_hashes:
            raise PvECombatCalibrationError(
                "duplicate PvE evidence artifacts would double-count observations"
            )
        trace_hashes.append(trace_hash)
        native = _mapping(payload["native_observation"], "native_observation")
        executable_hashes.add(_string(native, "executable_sha256"))
        policies.add(_string(payload, "policy"))
        confirmed_kills += _integer(payload, "kills", minimum=0)
        trace = payload["trace"]
        assert isinstance(trace, list)
        seen_tokens: set[str] = set()
        seen_event_sequences: set[int] = set()
        player_opportunity_times: list[int] = []
        target_opportunity_times: list[int] = []
        target_health_by_token: dict[str, float] = {}
        target_decrease_times: dict[str, list[int]] = {}
        previous_player_health: float | None = None
        player_decrease_times: list[int] = []
        steps = tuple(_mapping(item, "trace step") for item in trace)
        if steps:
            player = _mapping(steps[0].get("player"), "starting player")
            _append_optional_number(starting_health, player.get("current_health"))
            _append_optional_number(starting_mana, player.get("current_mana"))
            _append_optional_number(starting_stamina, player.get("current_stamina"))

        for step_index, step in enumerate(steps):
            at_ms = _integer(step, "at_ms", minimum=0)
            target = _mapping(step.get("target"), "trace target")
            token = target.get("token")
            if isinstance(token, str) and token and token not in seen_tokens:
                seen_tokens.add(token)
                _append_optional_number(
                    target_health_samples,
                    target.get("maximum_health"),
                    positive=True,
                )
                _append_optional_number(
                    engagement_distances,
                    target.get("planar_distance"),
                )
            if isinstance(token, str) and token:
                current_target_health = _optional_number(target.get("current_health"))
                if current_target_health is not None:
                    previous_target_health = target_health_by_token.get(token)
                    if (
                        previous_target_health is not None
                        and previous_target_health - current_target_health > 0.0001
                    ):
                        native_target_decreases.append(
                            previous_target_health - current_target_health
                        )
                        target_decrease_times.setdefault(token, []).append(at_ms)
                    target_health_by_token[token] = current_target_health
            player = _mapping(step.get("player"), "trace player")
            current_player_health = _optional_number(player.get("current_health"))
            if current_player_health is not None:
                if (
                    previous_player_health is not None
                    and previous_player_health - current_player_health > 0.0001
                ):
                    native_player_decreases.append(
                        previous_player_health - current_player_health
                    )
                    player_decrease_times.append(at_ms)
                previous_player_health = current_player_health
            events = step.get("combat_events")
            assert isinstance(events, list)
            for event_raw in events:
                event = _mapping(event_raw, "combat event")
                sequence = _integer(event, "sequence", minimum=0)
                if sequence in seen_event_sequences:
                    raise PvECombatCalibrationError(
                        f"trace {payload_index} repeats combat event sequence {sequence}"
                    )
                seen_event_sequences.add(sequence)
                kind = _string(event, "kind")
                amount = event.get("amount")
                if kind == "player_hit_target":
                    player_hits += 1
                    player_opportunity_times.append(at_ms)
                    _append_optional_number(player_damage_samples, amount)
                elif kind == "player_missed_target":
                    player_misses += 1
                    player_opportunity_times.append(at_ms)
                elif kind == "target_hit_player":
                    target_hits += 1
                    target_opportunity_times.append(at_ms)
                    _append_optional_number(target_damage_samples, amount)
                elif kind == "target_missed_player":
                    target_misses += 1
                    target_opportunity_times.append(at_ms)
                elif kind == "experience_gained":
                    _append_optional_number(experience_samples, amount, positive=True)

            if step.get("intent") == _SHADOW_TOUCH:
                player = _mapping(step.get("player"), "trace player")
                before = _optional_number(player.get("current_mana"))
                if before is not None:
                    for following in steps[step_index + 1 :]:
                        if _integer(following, "at_ms", minimum=0) <= at_ms:
                            continue
                        after_player = _mapping(
                            following.get("player"),
                            "trace player",
                        )
                        after = _optional_number(after_player.get("current_mana"))
                        if after is not None:
                            delta = before - after
                            if delta >= 0:
                                shadow_touch_deltas.append(delta)
                            break

        added, same_poll = _positive_intervals(player_opportunity_times)
        player_intervals.extend(added)
        same_poll_opportunities += same_poll
        added, same_poll = _positive_intervals(target_opportunity_times)
        target_intervals.extend(added)
        same_poll_opportunities += same_poll
        for decrease_times in target_decrease_times.values():
            added, same_poll = _positive_intervals(decrease_times)
            native_target_decrease_intervals.extend(added)
            same_poll_opportunities += same_poll
        added, same_poll = _positive_intervals(player_decrease_times)
        native_player_decrease_intervals.extend(added)
        same_poll_opportunities += same_poll

    unique_trace_hashes = tuple(sorted(set(trace_hashes)))
    digest = hashlib.sha256("".join(unique_trace_hashes).encode("ascii")).hexdigest()[:16]
    return PvECombatCalibration(
        profile_id=f"wonderbane.live-pve.{digest}",
        source_trace_sha256s=unique_trace_hashes,
        executable_sha256s=tuple(sorted(executable_hashes)),
        policies=tuple(sorted(policies)),
        confirmed_kills=confirmed_kills,
        player_hits=player_hits,
        player_misses=player_misses,
        target_hits=target_hits,
        target_misses=target_misses,
        target_maximum_health=ObservedSampleSummary.from_samples(target_health_samples),
        player_damage=ObservedSampleSummary.from_samples(player_damage_samples),
        target_damage=ObservedSampleSummary.from_samples(target_damage_samples),
        player_attack_interval_ms=ObservedSampleSummary.from_samples(player_intervals),
        target_attack_interval_ms=ObservedSampleSummary.from_samples(target_intervals),
        experience_reward=ObservedSampleSummary.from_samples(experience_samples),
        starting_player_health=ObservedSampleSummary.from_samples(starting_health),
        starting_player_mana=ObservedSampleSummary.from_samples(starting_mana),
        starting_player_stamina=ObservedSampleSummary.from_samples(starting_stamina),
        engagement_planar_distance=ObservedSampleSummary.from_samples(
            engagement_distances
        ),
        shadow_touch_mana_delta=ObservedSampleSummary.from_samples(shadow_touch_deltas),
        native_target_health_decrease=ObservedSampleSummary.from_samples(
            native_target_decreases
        ),
        native_target_health_decrease_interval_ms=ObservedSampleSummary.from_samples(
            native_target_decrease_intervals
        ),
        native_player_health_decrease=ObservedSampleSummary.from_samples(
            native_player_decreases
        ),
        native_player_health_decrease_interval_ms=ObservedSampleSummary.from_samples(
            native_player_decrease_intervals
        ),
        limitations=(
            "Combat-event timing uses the controller poll that observed each native log "
            "record, not the client's internal action timestamp.",
            "Intervals with multiple opportunities observed in one poll are omitted; "
            f"{same_poll_opportunities} same-poll intervals were omitted.",
            "Damage records do not identify which weapon, proc, resistance, or mitigation "
            "component produced the final logged amount.",
            "Target tokens are process-local opaque identities; target maximum health and "
            "engagement distance are aggregated across observed selections.",
            "Observed Shadow Touch mana deltas include any regeneration between adjacent "
            "controller polls.",
            "Native health decreases are exact aggregate state changes but are not attributed "
            "to a specific attacker, weapon, power, proc, mitigation component, or heal.",
        ),
    )


def compile_pve_combat_calibration_files(
    paths: Sequence[str | Path],
) -> PvECombatCalibration:
    if not paths:
        raise PvECombatCalibrationError("at least one PvE evidence path is required")
    return compile_pve_combat_calibration(
        tuple(load_pve_trace_evidence(path) for path in paths)
    )


def save_pve_combat_calibration(
    path: str | Path,
    calibration: PvECombatCalibration,
) -> None:
    if not isinstance(calibration, PvECombatCalibration):
        raise PvECombatCalibrationError("calibration must be PvECombatCalibration")
    output_path = Path(path)
    temporary_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(calibration.as_dict(), allow_nan=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(output_path)
    except (OSError, TypeError, ValueError) as exc:
        raise PvECombatCalibrationError(
            f"could not save PvE combat calibration: {exc}"
        ) from exc
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def load_pve_combat_calibration(path: str | Path) -> PvECombatCalibration:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PvECombatCalibrationError(
            f"could not read PvE combat calibration: {exc}"
        ) from exc
    data = _mapping(raw, "PvE combat calibration")
    if data.get("schema_version") != PVE_COMBAT_CALIBRATION_SCHEMA_VERSION:
        raise PvECombatCalibrationError("unsupported PvE combat calibration schema")
    player_attacks = _mapping(data.get("player_attacks"), "player_attacks")
    target_attacks = _mapping(data.get("target_attacks"), "target_attacks")
    starting_player = _mapping(data.get("starting_player"), "starting_player")
    native_health_changes = _mapping(
        data.get("native_health_changes"),
        "native_health_changes",
    )
    try:
        return PvECombatCalibration(
            profile_id=_string(data, "profile_id"),
            source_trace_sha256s=_string_tuple(data, "source_trace_sha256s"),
            executable_sha256s=_string_tuple(data, "executable_sha256s"),
            policies=_string_tuple(data, "policies"),
            confirmed_kills=_integer(data, "confirmed_kills", minimum=0),
            player_hits=_integer(player_attacks, "hits", minimum=0),
            player_misses=_integer(player_attacks, "misses", minimum=0),
            target_hits=_integer(target_attacks, "hits", minimum=0),
            target_misses=_integer(target_attacks, "misses", minimum=0),
            target_maximum_health=_optional_summary(data.get("target_maximum_health")),
            player_damage=_optional_summary(player_attacks.get("damage")),
            target_damage=_optional_summary(target_attacks.get("damage")),
            player_attack_interval_ms=_optional_summary(
                player_attacks.get("interval_ms")
            ),
            target_attack_interval_ms=_optional_summary(
                target_attacks.get("interval_ms")
            ),
            experience_reward=_optional_summary(data.get("experience_reward")),
            starting_player_health=_optional_summary(starting_player.get("health")),
            starting_player_mana=_optional_summary(starting_player.get("mana")),
            starting_player_stamina=_optional_summary(starting_player.get("stamina")),
            engagement_planar_distance=_optional_summary(
                data.get("engagement_planar_distance")
            ),
            shadow_touch_mana_delta=_optional_summary(
                data.get("shadow_touch_mana_delta")
            ),
            native_target_health_decrease=_optional_summary(
                native_health_changes.get("target_decrease")
            ),
            native_target_health_decrease_interval_ms=_optional_summary(
                native_health_changes.get("target_decrease_interval_ms")
            ),
            native_player_health_decrease=_optional_summary(
                native_health_changes.get("player_decrease")
            ),
            native_player_health_decrease_interval_ms=_optional_summary(
                native_health_changes.get("player_decrease_interval_ms")
            ),
            limitations=_string_tuple(data, "limitations"),
        )
    except ValueError as exc:
        raise PvECombatCalibrationError(str(exc)) from exc


def _summary_dict(summary: ObservedSampleSummary | None) -> dict[str, object] | None:
    return None if summary is None else summary.as_dict()


def _optional_summary(payload: object) -> ObservedSampleSummary | None:
    return None if payload is None else ObservedSampleSummary.from_dict(payload)


def _positive_intervals(times: Sequence[int]) -> tuple[list[float], int]:
    intervals: list[float] = []
    same_poll = 0
    for previous, current in zip(times, times[1:], strict=False):
        interval = current - previous
        if interval > 0:
            intervals.append(float(interval))
        else:
            same_poll += 1
    return intervals, same_poll


def _append_optional_number(
    destination: list[float],
    value: object,
    *,
    positive: bool = False,
) -> None:
    parsed = _optional_number(value)
    if parsed is None:
        return
    if positive and parsed <= 0:
        raise PvECombatCalibrationError("observed sample must be positive")
    destination.append(parsed)


def _optional_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise PvECombatCalibrationError("observed value must be a finite number or null")
    return float(value)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PvECombatCalibrationError(f"{label} must be an object")
    return value


def _string(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise PvECombatCalibrationError(f"{field_name} must be a non-empty string")
    return value


def _string_tuple(payload: Mapping[str, object], field_name: str) -> tuple[str, ...]:
    value = payload.get(field_name)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise PvECombatCalibrationError(f"{field_name} must be an array of strings")
    return tuple(value)


def _integer(
    payload: Mapping[str, object],
    field_name: str,
    *,
    minimum: int,
) -> int:
    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PvECombatCalibrationError(
            f"{field_name} must be an integer greater than or equal to {minimum}"
        )
    return value


def _number(payload: Mapping[str, object], field_name: str) -> float:
    value = _optional_number(payload.get(field_name))
    if value is None:
        raise PvECombatCalibrationError(f"{field_name} must be a number")
    return value


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
