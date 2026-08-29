"""Classless build exploration over the simulator's compiled behavior recipes.

A loadout is only numbers, tags, and a requested action set. Race, class,
promotion, and discipline labels may be retained as metadata by importers, but
they have no authority in this module.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import combinations
from math import isfinite
from pathlib import Path
from statistics import fmean
from typing import Any

from shadowbane_lab.rollouts.duel import (
    CombatantConfig,
    DuelConfig,
    DuelResult,
    TerminationReason,
    run_duel,
)
from shadowbane_lab.rollouts.ruleset import load_assassin_warlock_duel_ruleset
from shadowbane_lab.rulesets import CharacterBuild, CompiledRuleset
from shadowbane_lab.sim import DeterministicRandom


class OpenBuildError(ValueError):
    """Raised when a primitive loadout or roster is malformed."""


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise OpenBuildError(f"{field_name} must be a non-empty string")


def _positive(value: float, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0
    ):
        raise OpenBuildError(f"{field_name} must be a positive finite number")


def _unique_strings(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise OpenBuildError(f"{field_name} must not contain duplicates")
    for value in values:
        _identifier(value, field_name)


@dataclass(frozen=True, slots=True)
class PrimitiveLoadout:
    """A freely composable bag of active behavior recipes."""

    loadout_id: str
    display_name: str
    action_keys: tuple[str, ...]
    health: float = 500.0
    mana: float = 300.0
    stamina: float = 200.0
    move_speed: float = 15.0
    tags: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.loadout_id, "loadout_id")
        _identifier(self.display_name, "display_name")
        _unique_strings(self.action_keys, "action_keys")
        _unique_strings(self.tags, "tags")
        _unique_strings(self.notes, "notes")
        for value, name in (
            (self.health, "health"),
            (self.mana, "mana"),
            (self.stamina, "stamina"),
            (self.move_speed, "move_speed"),
        ):
            _positive(value, name)
        keys = tuple(key for key, _ in self.metadata)
        if len(keys) != len(set(keys)):
            raise OpenBuildError("metadata must not contain duplicate keys")
        for key, value in self.metadata:
            _identifier(key, "metadata key")
            _identifier(value, f"metadata.{key}")

    def as_dict(self) -> dict[str, object]:
        return {
            "loadout_id": self.loadout_id,
            "display_name": self.display_name,
            "action_keys": list(self.action_keys),
            "health": self.health,
            "mana": self.mana,
            "stamina": self.stamina,
            "move_speed": self.move_speed,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class ResolvedPrimitiveLoadout:
    loadout: PrimitiveLoadout
    common_action_keys: tuple[str, ...]
    executable_action_keys: tuple[str, ...]
    omitted_action_keys: tuple[str, ...]
    auto_added_tags: tuple[str, ...]
    unsatisfied_requirement_tags: tuple[str, ...]
    capability_tags: tuple[str, ...]

    @property
    def all_action_keys(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.common_action_keys, *self.executable_action_keys)))

    @property
    def coverage_fraction(self) -> float:
        requested = len(self.loadout.action_keys)
        return 1.0 if requested == 0 else len(self.executable_action_keys) / requested

    def as_dict(self) -> dict[str, object]:
        payload = self.loadout.as_dict()
        payload.update(
            {
                "common_action_keys": list(self.common_action_keys),
                "executable_action_keys": list(self.executable_action_keys),
                "omitted_action_keys": list(self.omitted_action_keys),
                "auto_added_tags": list(self.auto_added_tags),
                "unsatisfied_requirement_tags": list(self.unsatisfied_requirement_tags),
                "capability_tags": list(self.capability_tags),
                "coverage_fraction": self.coverage_fraction,
            }
        )
        return payload


@dataclass(frozen=True, slots=True)
class OpenDuelRun:
    left: ResolvedPrimitiveLoadout
    right: ResolvedPrimitiveLoadout
    duel: DuelResult

    def as_dict(self) -> dict[str, object]:
        return {
            "left": self.left.as_dict(),
            "right": self.right.as_dict(),
            "duel": self.duel.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class OpenMatchupCell:
    first_loadout_id: str
    second_loadout_id: str
    matches: int
    first_wins: int
    second_wins: int
    draws: int
    time_limits: int
    mean_ticks: float
    unique_trace_count: int
    mean_coverage: float
    sample: OpenDuelRun

    def as_dict(self) -> dict[str, object]:
        return {
            "first_loadout_id": self.first_loadout_id,
            "second_loadout_id": self.second_loadout_id,
            "matches": self.matches,
            "first_wins": self.first_wins,
            "second_wins": self.second_wins,
            "draws": self.draws,
            "time_limits": self.time_limits,
            "mean_ticks": self.mean_ticks,
            "unique_trace_count": self.unique_trace_count,
            "mean_coverage": self.mean_coverage,
            "sample": self.sample.as_dict(),
        }


def resolve_primitive_loadout(
    loadout: PrimitiveLoadout,
    ruleset: CompiledRuleset,
    *,
    auto_satisfy_action_requirements: bool = True,
) -> ResolvedPrimitiveLoadout:
    """Select every executable requested action without class/progression checks."""

    records = {record.action_key: record for record in ruleset.records}
    common = tuple(
        sorted(
            record.action_key
            for record in ruleset.records
            if record.action is not None and record.progression is None
        )
    )
    executable: list[str] = []
    omitted: list[str] = []
    required_tags: set[str] = set()
    capability_tags: set[str] = set()
    for action_key in loadout.action_keys:
        record = records.get(action_key)
        if record is None or record.action is None:
            omitted.append(action_key)
            continue
        executable.append(action_key)
        capability_tags.update(f"capability.{tag}" for tag in record.action.tags)
        if auto_satisfy_action_requirements:
            required_tags.update(record.action.required_actor_tags)
    provided_tags = set(loadout.tags)
    auto_satisfied_prefixes = (
        "capability.",
        "equipment.",
        "form.",
        "power.",
        "stance.",
    )
    auto_added = {
        tag for tag in required_tags - provided_tags if tag.startswith(auto_satisfied_prefixes)
    }
    unsatisfied = required_tags - provided_tags - auto_added
    return ResolvedPrimitiveLoadout(
        loadout=loadout,
        common_action_keys=common,
        executable_action_keys=tuple(executable),
        omitted_action_keys=tuple(omitted),
        auto_added_tags=tuple(sorted(auto_added)),
        unsatisfied_requirement_tags=tuple(sorted(unsatisfied)),
        capability_tags=tuple(sorted(capability_tags)),
    )


def run_open_duel(
    ruleset: CompiledRuleset,
    left: PrimitiveLoadout,
    right: PrimitiveLoadout,
    *,
    starting_distance: float = 15.0,
    max_ticks: int = 1_200,
    seed: int = 1,
) -> OpenDuelRun:
    """Run two arbitrary primitive bags through the ordinary duel harness."""

    if left.loadout_id == right.loadout_id:
        raise OpenBuildError("open duel loadout ids must differ")
    resolved_left = resolve_primitive_loadout(left, ruleset)
    resolved_right = resolve_primitive_loadout(right, ruleset)
    duel = run_duel(
        DuelConfig(
            left=_combatant(resolved_left, left.loadout_id, "left"),
            right=_combatant(resolved_right, right.loadout_id, "right"),
            starting_distance=starting_distance,
            max_ticks=max_ticks,
            seed=seed,
        ),
        ruleset=ruleset,
    )
    return OpenDuelRun(left=resolved_left, right=resolved_right, duel=duel)


def round_robin_open_duels(
    ruleset: CompiledRuleset,
    loadouts: tuple[PrimitiveLoadout, ...],
    *,
    starting_distances: tuple[float, ...] = (15.0, 60.0, 110.0),
    seeds: tuple[int, ...] = (1, 2, 3),
    max_ticks: int = 1_200,
    mirrored: bool = True,
) -> tuple[OpenMatchupCell, ...]:
    """Cross all loadout pairs; reverse sides by default to reduce spawn bias."""

    if len(loadouts) < 2:
        raise OpenBuildError("round robin requires at least two loadouts")
    ids = tuple(item.loadout_id for item in loadouts)
    if len(ids) != len(set(ids)):
        raise OpenBuildError("loadout ids must be unique")
    if not starting_distances or not seeds:
        raise OpenBuildError("distances and seeds must not be empty")

    cells: list[OpenMatchupCell] = []
    for first, second in combinations(loadouts, 2):
        results: list[OpenDuelRun] = []
        for distance in starting_distances:
            _positive(distance, "starting distance")
            for seed in seeds:
                if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
                    raise OpenBuildError("seeds must be non-negative integers")
                results.append(
                    run_open_duel(
                        ruleset,
                        first,
                        second,
                        starting_distance=distance,
                        max_ticks=max_ticks,
                        seed=seed,
                    )
                )
                if mirrored:
                    results.append(
                        run_open_duel(
                            ruleset,
                            second,
                            first,
                            starting_distance=distance,
                            max_ticks=max_ticks,
                            seed=seed,
                        )
                    )
        cells.append(
            OpenMatchupCell(
                first_loadout_id=first.loadout_id,
                second_loadout_id=second.loadout_id,
                matches=len(results),
                first_wins=sum(item.duel.winner_entity_id == first.loadout_id for item in results),
                second_wins=sum(
                    item.duel.winner_entity_id == second.loadout_id for item in results
                ),
                draws=sum(item.duel.winner_entity_id is None for item in results),
                time_limits=sum(
                    item.duel.reason is TerminationReason.TIME_LIMIT for item in results
                ),
                mean_ticks=fmean(item.duel.ticks for item in results),
                unique_trace_count=len({item.duel.trace_digest for item in results}),
                mean_coverage=fmean(
                    (item.left.coverage_fraction + item.right.coverage_fraction) / 2.0
                    for item in results
                ),
                sample=results[0],
            )
        )
    return tuple(cells)


def generate_primitive_loadouts(
    ruleset: CompiledRuleset,
    *,
    count: int,
    seed: int,
    minimum_actions: int = 2,
    maximum_actions: int = 6,
    required_tag_groups: tuple[tuple[str, ...], ...] = (("damage", "attack", "control"),),
) -> tuple[PrimitiveLoadout, ...]:
    """Create reproducible mixes from behavior tags, ignoring source classes."""

    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise OpenBuildError("count must be a positive integer")
    if (
        isinstance(minimum_actions, bool)
        or not isinstance(minimum_actions, int)
        or minimum_actions < 1
    ):
        raise OpenBuildError("minimum_actions must be a positive integer")
    if (
        isinstance(maximum_actions, bool)
        or not isinstance(maximum_actions, int)
        or maximum_actions < minimum_actions
    ):
        raise OpenBuildError("maximum_actions must be at least minimum_actions")

    candidates = tuple(
        record
        for record in ruleset.records
        if record.action is not None and record.progression is not None
    )
    if len(candidates) < minimum_actions:
        raise OpenBuildError("ruleset has too few executable selectable actions")
    maximum_actions = min(maximum_actions, len(candidates))
    for group in required_tag_groups:
        _unique_strings(group, "required tag group")
        if not any(set(record.action.tags) & set(group) for record in candidates):
            raise OpenBuildError("no executable action satisfies required group " + "/".join(group))

    rng = DeterministicRandom(seed)
    signatures: set[tuple[str, ...]] = set()
    loadouts: list[PrimitiveLoadout] = []
    attempts = 0
    while len(loadouts) < count and attempts < max(100, count * 100):
        attempts += 1
        desired = minimum_actions + rng.randbelow(maximum_actions - minimum_actions + 1)
        selected: list[str] = []
        for group in required_tag_groups:
            eligible = tuple(
                record for record in candidates if set(record.action.tags) & set(group)
            )
            key = eligible[rng.randbelow(len(eligible))].action_key
            if key not in selected:
                selected.append(key)
        remaining = [
            record.action_key for record in candidates if record.action_key not in selected
        ]
        while len(selected) < desired and remaining:
            index = rng.randbelow(len(remaining))
            selected.append(remaining.pop(index))
        signature = tuple(sorted(selected))
        if signature in signatures:
            continue
        signatures.add(signature)
        index = len(loadouts)
        loadouts.append(
            PrimitiveLoadout(
                loadout_id=f"generated.{seed}.{index:03d}",
                display_name=f"Generated primitive mix {index:03d}",
                action_keys=signature,
                health=round(rng.uniform(350.0, 750.0), 3),
                mana=round(rng.uniform(180.0, 500.0), 3),
                stamina=round(rng.uniform(140.0, 350.0), 3),
                move_speed=round(rng.uniform(12.0, 22.0), 3),
                tags=("profile.generated",),
                metadata=(
                    ("generation_seed", str(seed)),
                    ("generation_index", str(index)),
                ),
                notes=("Generated without race, class, promotion, or discipline constraints.",),
            )
        )
    if len(loadouts) != count:
        raise OpenBuildError(f"could generate only {len(loadouts)} unique loadouts from this pool")
    return tuple(loadouts)


def load_open_roster(path: str | Path) -> tuple[PrimitiveLoadout, ...]:
    return load_open_roster_text(Path(path).read_text(encoding="utf-8"))


def load_open_roster_text(text: str) -> tuple[PrimitiveLoadout, ...]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OpenBuildError("roster is not valid JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise OpenBuildError("roster must be a schema-version-1 object")
    values = raw.get("loadouts")
    if not isinstance(values, list) or not values:
        raise OpenBuildError("roster loadouts must be a non-empty array")
    loadouts = tuple(_parse_loadout(item, index) for index, item in enumerate(values))
    ids = tuple(item.loadout_id for item in loadouts)
    if len(ids) != len(set(ids)):
        raise OpenBuildError("roster loadout ids must be unique")
    return loadouts


def _parse_loadout(raw: Any, index: int) -> PrimitiveLoadout:
    if not isinstance(raw, dict):
        raise OpenBuildError(f"loadouts[{index}] must be an object")

    def strings(key: str) -> tuple[str, ...]:
        value = raw.get(key, [])
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise OpenBuildError(f"loadouts[{index}].{key} must contain strings")
        return tuple(value)

    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in metadata.items()
    ):
        raise OpenBuildError(f"loadouts[{index}].metadata must map strings to strings")

    return PrimitiveLoadout(
        loadout_id=raw.get("loadout_id", ""),
        display_name=raw.get("display_name", ""),
        action_keys=strings("action_keys"),
        health=raw.get("health", 500.0),
        mana=raw.get("mana", 300.0),
        stamina=raw.get("stamina", 200.0),
        move_speed=raw.get("move_speed", 15.0),
        tags=strings("tags"),
        metadata=tuple(metadata.items()),
        notes=strings("notes"),
    )


def _combatant(
    resolved: ResolvedPrimitiveLoadout,
    entity_id: str,
    team_id: str,
) -> CombatantConfig:
    tags = tuple(
        dict.fromkeys(
            (
                *resolved.loadout.tags,
                *resolved.auto_added_tags,
                *resolved.capability_tags,
            )
        )
    )
    return CombatantConfig(
        entity_id=entity_id,
        team_id=team_id,
        build=CharacterBuild(profession="open", level=1),
        health=resolved.loadout.health,
        mana=resolved.loadout.mana,
        stamina=resolved.loadout.stamina,
        move_speed=resolved.loadout.move_speed,
        tags=tags,
        action_keys_override=resolved.all_action_keys,
    )


def _csv(value: str, *, integer: bool) -> tuple[int, ...] | tuple[float, ...]:
    parts = tuple(part.strip() for part in value.split(",") if part.strip())
    if not parts:
        raise argparse.ArgumentTypeError("expected a comma-separated list")
    try:
        return (
            tuple(int(item) for item in parts) if integer else tuple(float(item) for item in parts)
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError("list contains an invalid number") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m shadowbane_lab.rollouts.open_builds",
        description="Generate classless behavior mixes and run mirrored tournaments.",
    )
    parser.add_argument("--roster", type=Path)
    parser.add_argument("--generate", type=int, default=8)
    parser.add_argument("--generation-seed", type=int, default=1)
    parser.add_argument("--min-actions", type=int, default=2)
    parser.add_argument("--max-actions", type=int, default=6)
    parser.add_argument("--distances", default="15,60,110")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--max-ticks", type=int, default=1_200)
    parser.add_argument("--no-mirror", action="store_true")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)

    ruleset = load_assassin_warlock_duel_ruleset()
    loadouts: list[PrimitiveLoadout] = []
    if arguments.roster is not None:
        loadouts.extend(load_open_roster(arguments.roster))
    if arguments.generate:
        loadouts.extend(
            generate_primitive_loadouts(
                ruleset,
                count=arguments.generate,
                seed=arguments.generation_seed,
                minimum_actions=arguments.min_actions,
                maximum_actions=arguments.max_actions,
            )
        )
    if len(loadouts) < 2:
        parser.error("provide or generate at least two loadouts")
    distances = _csv(arguments.distances, integer=False)
    seeds = _csv(arguments.seeds, integer=True)
    cells = round_robin_open_duels(
        ruleset,
        tuple(loadouts),
        starting_distances=distances,
        seeds=seeds,
        max_ticks=arguments.max_ticks,
        mirrored=not arguments.no_mirror,
    )
    payload = {
        "ruleset_id": ruleset.ruleset_id,
        "loadouts": [resolve_primitive_loadout(item, ruleset).as_dict() for item in loadouts],
        "matchups": [item.as_dict() for item in cells],
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8")
        print(
            f"Wrote {len(loadouts)} loadouts and {len(cells)} matchup cells to {arguments.output}"
        )
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
