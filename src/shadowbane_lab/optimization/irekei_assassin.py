"""First catalog-backed Irekei Assassin quality-diversity experiment."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from shadowbane_lab.equipment import EquipmentCatalog, load_bundled_equipment_catalog
from shadowbane_lab.progression import (
    StatLine,
    WonderbaneCalculatorCatalog,
    WonderbaneCalculatorImportError,
    load_bundled_wonderbane_calculator_catalog,
)
from shadowbane_lab.rollouts.presets import (
    CombatantPreset,
    wonderbane_deflock,
    wonderbane_elf_healer_druid,
    wonderbane_sundancer_proc_assassin,
)
from shadowbane_lab.rollouts.ruleset import load_wonderbane_guide_duel_ruleset
from shadowbane_lab.rulesets import CompiledRuleset

from .build_compiler import LegalBuildCompiler
from .build_model import (
    EquipmentSelection,
    LegalBuildCompileError,
    LegalBuildCompilePolicy,
    LegalBuildGenome,
)
from .map_elites import (
    ArchiveAdmission,
    DescriptorAxis,
    MapElitesArchive,
    MapElitesRun,
    run_map_elites,
)
from .training import (
    CatalogBackedLegalityGate,
    CompilerBackedGenomeMutator,
    DuelScenario,
    LegalBuildLeagueEvaluator,
    genome_mechanical_digest,
)


@dataclass(frozen=True, slots=True)
class IrekeiAssassinSearchConfig:
    iterations: int = 24
    mutation_seed: int = 7
    rollout_seeds: tuple[int, ...] = (1, 2, 3)
    starting_distances: tuple[float, ...] = (6.0, 15.0, 40.0)
    max_ticks: int = 600
    equipment_pool_size: int = 12

    def __post_init__(self) -> None:
        for value, field_name, minimum in (
            (self.iterations, "iterations", 0),
            (self.mutation_seed, "mutation_seed", 0),
            (self.max_ticks, "max_ticks", 1),
            (self.equipment_pool_size, "equipment_pool_size", 1),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise LegalBuildCompileError(
                    f"{field_name} must be an integer of at least {minimum}"
                )
        if not self.rollout_seeds or len(self.rollout_seeds) != len(
            set(self.rollout_seeds)
        ):
            raise LegalBuildCompileError(
                "rollout_seeds must be non-empty and unique"
            )
        if any(
            isinstance(seed, bool) or not isinstance(seed, int) or seed < 0
            for seed in self.rollout_seeds
        ):
            raise LegalBuildCompileError(
                "rollout_seeds must contain non-negative integers"
            )
        if not self.starting_distances:
            raise LegalBuildCompileError("starting_distances must not be empty")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value <= 0
            for value in self.starting_distances
        ):
            raise LegalBuildCompileError(
                "starting_distances must contain positive numbers"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "iterations": self.iterations,
            "mutation_seed": self.mutation_seed,
            "rollout_seeds": list(self.rollout_seeds),
            "starting_distances": list(self.starting_distances),
            "max_ticks": self.max_ticks,
            "equipment_pool_size": self.equipment_pool_size,
        }


@dataclass(frozen=True, slots=True)
class IrekeiAssassinSearchReport:
    config: IrekeiAssassinSearchConfig
    ruleset_id: str
    initial_genomes: tuple[LegalBuildGenome, ...]
    opponents: tuple[LegalBuildGenome, ...]
    run: MapElitesRun[LegalBuildGenome]
    caveats: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "experiment": "wonderbane.irekei-assassin-map-elites.v1",
            "config": self.config.as_dict(),
            "ruleset_id": self.ruleset_id,
            "initial_genomes": [item.as_dict() for item in self.initial_genomes],
            "opponents": [item.as_dict() for item in self.opponents],
            "run": self.run.as_dict(lambda genome: genome.as_dict()),
            "caveats": list(self.caveats),
        }


def run_irekei_assassin_search(
    config: IrekeiAssassinSearchConfig | None = None,
    *,
    calculator: WonderbaneCalculatorCatalog | None = None,
    equipment: EquipmentCatalog | None = None,
    ruleset: CompiledRuleset | None = None,
) -> IrekeiAssassinSearchReport:
    """Run a bounded, deterministic candidate-grade build search."""

    if config is None:
        config = IrekeiAssassinSearchConfig()
    if not isinstance(config, IrekeiAssassinSearchConfig):
        raise LegalBuildCompileError("config must be IrekeiAssassinSearchConfig")
    calculator = calculator or load_bundled_wonderbane_calculator_catalog()
    equipment = equipment or load_bundled_equipment_catalog()
    assassin_preset = wonderbane_sundancer_proc_assassin()
    deflock_preset = wonderbane_deflock()
    druid_preset = wonderbane_elf_healer_druid()
    if ruleset is None:
        ruleset = load_wonderbane_guide_duel_ruleset(
            rank_overrides=_rank_overrides(
                assassin_preset,
                deflock_preset,
                druid_preset,
            )
        )
    policy = LegalBuildCompilePolicy(
        allow_ruleset_overrides=True,
        apply_candidate_equipment_values=True,
    )
    compiler = LegalBuildCompiler(
        calculator,
        equipment,
        ruleset=ruleset,
        policy=policy,
    )
    gate = CatalogBackedLegalityGate(calculator, equipment)

    powers = assassin_preset.build.power_ranks
    assassin_skills = dict(assassin_preset.skill_ranks)
    selected_runes = _rune_ids(calculator, ("Sun Dancer", "Saboteur"))
    weapon_ids = _unarmed_weapon_ids(
        equipment,
        limit=config.equipment_pool_size,
    )
    initial_genomes = tuple(
        _assassin_genome(
            calculator,
            genome_id=f"irekei-assassin-75-{label}",
            selected_runes=selected_runes,
            skill_ranks=tuple(sorted(assassin_skills.items())),
            power_ranks=powers,
            priority=priority,
            weapon_id=weapon_ids[0],
        )
        for label, priority in (
            ("int-dex-con", (3, 1, 2, 4, 0)),
            ("dex-int-con", (1, 3, 2, 4, 0)),
            ("con-int-dex", (2, 3, 1, 4, 0)),
        )
    )
    opponents = (
        _first_legal_profession_genome(
            calculator,
            deflock_preset,
            priority=(3, 2, 1, 4, 0),
        ),
        _first_legal_profession_genome(
            calculator,
            druid_preset,
            priority=(3, 2, 4, 1, 0),
        ),
    )
    for genome in (*initial_genomes, *opponents):
        gate.validate(genome)
        compiler.compile(genome)

    scenarios = tuple(
        DuelScenario(
            scenario_id=f"clean-duel-{distance:g}",
            starting_distance=float(distance),
            max_ticks=config.max_ticks,
            mirrored=True,
        )
        for distance in config.starting_distances
    )
    evaluator = LegalBuildLeagueEvaluator(
        compiler,
        ruleset,
        opponents,
        scenarios,
        config.rollout_seeds,
        gate=gate,
    )
    eligible_runes = tuple(
        rune.record_id
        for rune in calculator.eligible_runes(
            race_id=2013,
            base_class_id=2502,
            promotion_id=2504,
            level=75,
            trained_modifiers=initial_genomes[0].trained_modifiers,
        )
    )
    mutator = CompilerBackedGenomeMutator(
        compiler,
        gate=gate,
        rune_ids=eligible_runes,
        equipment_options=(
            ("main_hand", weapon_ids),
            ("off_hand", weapon_ids),
        ),
        power_options=powers,
        maximum_attempts=64,
    )
    archive = MapElitesArchive[LegalBuildGenome](
        (
            DescriptorAxis("survival_rate", (0.25, 0.5, 0.75)),
            DescriptorAxis("action_count", (5.0, 8.0, 12.0)),
            DescriptorAxis("resource_depth", (2_000.0, 3_000.0, 4_000.0)),
        ),
        required_admission=ArchiveAdmission.CANDIDATE,
    )
    run = run_map_elites(
        initial_genomes,
        archive=archive,
        iterations=config.iterations,
        seed=config.mutation_seed,
        candidate_digest=genome_mechanical_digest,
        evaluate=evaluator,
        mutate=mutator,
    )
    return IrekeiAssassinSearchReport(
        config=config,
        ruleset_id=ruleset.ruleset_id,
        initial_genomes=initial_genomes,
        opponents=opponents,
        run=run,
        caveats=(
            "The archive is candidate-grade because current equipment values are "
            "historical candidates and selected action rows use reviewed overrides.",
            "Named item skill requirements and two-handed conflicts are enforced; "
            "opaque requirement tokens and general skill-train costs remain unresolved.",
            "Power-rank points are checked only as a necessary lower bound against the "
            "sourced Rogue pool.",
            "The readable reference simulator remains the correctness oracle; this "
            "experiment is not yet the high-throughput NumPy/Numba backend.",
            "Results compare the current legal-build adapter against deterministic "
            "Shade Fighter Deflock and Elf Healer Druid identities, not the whole live "
            "metagame; when a guide omits sex, the lowest reviewed sex-specific record "
            "is selected deterministically.",
        ),
    )


def _rank_overrides(*presets: CombatantPreset) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for preset in presets:
        for action_key, rank in preset.build.power_ranks:
            current = overrides.get(action_key)
            if current is not None and current != rank:
                raise LegalBuildCompileError(
                    f"conflicting requested ranks for {action_key}: {current} and {rank}"
                )
            overrides[action_key] = rank
    return overrides


def _rune_ids(
    calculator: WonderbaneCalculatorCatalog,
    names: tuple[str, ...],
) -> tuple[int, ...]:
    selected: list[int] = []
    for name in names:
        matches = tuple(
            rune for rune in calculator.runes if rune.name.casefold() == name.casefold()
        )
        if len(matches) != 1:
            raise LegalBuildCompileError(
                f"expected one calculator rune named {name}, found {len(matches)}"
            )
        selected.append(matches[0].record_id)
    return tuple(sorted(selected))


def _fully_allocate(
    calculator: WonderbaneCalculatorCatalog,
    *,
    race_id: int,
    base_class_id: int,
    promotion_id: int,
    level: int,
    rune_ids: tuple[int, ...],
    priority: tuple[int, ...],
) -> StatLine:
    if tuple(sorted(priority)) != (0, 1, 2, 3, 4):
        raise LegalBuildCompileError(
            "attribute priority must be a permutation of five stat indexes"
        )
    values = [0, 0, 0, 0, 0]
    while True:
        current = calculator.calculate(
            race_id=race_id,
            base_class_id=base_class_id,
            promotion_id=promotion_id,
            level=level,
            trained_modifiers=StatLine.from_values(tuple(values)),
            rune_ids=rune_ids,
        )
        if current.available_points <= 0:
            return StatLine.from_values(tuple(values))
        progressed = False
        for index in priority:
            trial = list(values)
            trial[index] += 1
            try:
                result = calculator.calculate(
                    race_id=race_id,
                    base_class_id=base_class_id,
                    promotion_id=promotion_id,
                    level=level,
                    trained_modifiers=StatLine.from_values(tuple(trial)),
                    rune_ids=rune_ids,
                )
            except WonderbaneCalculatorImportError:
                continue
            if result.available_points >= current.available_points:
                continue
            values = trial
            progressed = True
            break
        if not progressed:
            return StatLine.from_values(tuple(values))


def _assassin_genome(
    calculator: WonderbaneCalculatorCatalog,
    *,
    genome_id: str,
    selected_runes: tuple[int, ...],
    skill_ranks: tuple[tuple[str, int], ...],
    power_ranks: tuple[tuple[str, int], ...],
    priority: tuple[int, ...],
    weapon_id: int,
) -> LegalBuildGenome:
    modifiers = _fully_allocate(
        calculator,
        race_id=2013,
        base_class_id=2502,
        promotion_id=2504,
        level=75,
        rune_ids=selected_runes,
        priority=priority,
    )
    return LegalBuildGenome(
        genome_id=genome_id,
        display_name=genome_id.replace("-", " ").title(),
        race_id=2013,
        base_class_id=2502,
        promotion_id=2504,
        level=75,
        move_speed=31.5,
        trained_modifiers=modifiers,
        rune_ids=selected_runes,
        skill_ranks=skill_ranks,
        power_ranks=power_ranks,
        equipment=(
            EquipmentSelection("main_hand", weapon_id),
            EquipmentSelection("off_hand", weapon_id),
        ),
    )


def _first_legal_profession_genome(
    calculator: WonderbaneCalculatorCatalog,
    preset: CombatantPreset,
    *,
    priority: tuple[int, ...],
) -> LegalBuildGenome:
    profession = preset.profession
    level = preset.level
    race_key = _single_profile_tag(preset, "race.")
    base_key = _single_profile_tag(preset, "base.")
    promotions = tuple(
        item
        for item in calculator.promotions
        if item.name.casefold() == profession.casefold()
    )
    if len(promotions) != 1:
        raise LegalBuildCompileError(
            f"expected one calculator promotion named {profession}"
        )
    bases = tuple(
        item for item in calculator.base_classes if _key(item.name) == base_key
    )
    if len(bases) != 1:
        raise LegalBuildCompileError(
            f"expected one calculator base class tagged {base_key}"
        )
    races = tuple(
        item for item in calculator.races if _key(item.family) == race_key
    )
    if not races:
        raise LegalBuildCompileError(
            f"expected at least one calculator race record tagged {race_key}"
        )
    promotion = promotions[0]
    base = bases[0]
    if base.name not in promotion.allowed_base_classes:
        raise LegalBuildCompileError(
            f"guide identity {race_key}/{base_key}/{profession} is not calculator-legal"
        )
    for race in sorted(races, key=lambda item: item.record_id):
        try:
            calculator.calculate(
                race_id=race.record_id,
                base_class_id=base.record_id,
                promotion_id=promotion.record_id,
                level=level,
            )
        except WonderbaneCalculatorImportError:
            continue
        modifiers = _fully_allocate(
            calculator,
            race_id=race.record_id,
            base_class_id=base.record_id,
            promotion_id=promotion.record_id,
            level=level,
            rune_ids=(),
            priority=priority,
        )
        return LegalBuildGenome(
            genome_id=(
                f"baseline-{race_key}-{base_key}-{profession}-{level}"
            ),
            display_name=(
                f"{race.family} {base.name} {promotion.name} baseline"
            ),
            race_id=race.record_id,
            base_class_id=base.record_id,
            promotion_id=promotion.record_id,
            level=level,
            move_speed=preset.move_speed,
            trained_modifiers=modifiers,
            skill_ranks=tuple(sorted(preset.skill_ranks)),
            power_ranks=tuple(sorted(preset.build.power_ranks)),
        )
    raise LegalBuildCompileError(
        f"no calculator-legal sex record found for {race_key}/{base_key}/{profession}"
    )


def _single_profile_tag(preset: CombatantPreset, prefix: str) -> str:
    values = {
        tag.removeprefix(prefix)
        for tag in (*preset.tags, *preset.combat_sheet.tags)
        if tag.startswith(prefix)
    }
    if len(values) != 1:
        raise LegalBuildCompileError(
            f"{preset.preset_id} must expose exactly one {prefix} profile tag"
        )
    return next(iter(values))


def _unarmed_weapon_ids(
    equipment: EquipmentCatalog,
    *,
    limit: int,
) -> tuple[int, ...]:
    candidates = tuple(
        item.item_id
        for item in sorted(equipment.base_items, key=lambda value: value.item_id)
        if item.current_name_verified
        and "unarmed" in item.skill_required.casefold()
        and item.damage_type is not None
        and item.maximum_damage > item.minimum_damage
        and not item.two_handed
    )
    if 29390 not in candidates:
        raise LegalBuildCompileError(
            "reviewed Rha'khanakar item 29390 is absent from the equipment catalog"
        )
    ordered = (29390, *(item for item in candidates if item != 29390))
    selected = tuple(ordered[:limit])
    if not selected:
        raise LegalBuildCompileError("no candidate unarmed weapons are available")
    return selected


def _key(value: str) -> str:
    return "-".join(part for part in value.casefold().split() if part)


def _csv_ints(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc
    if not result:
        raise argparse.ArgumentTypeError("expected at least one integer")
    return result


def _csv_floats(value: str) -> tuple[float, ...]:
    try:
        result = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated numbers") from exc
    if not result:
        raise argparse.ArgumentTypeError("expected at least one number")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m shadowbane_lab.optimization.irekei_assassin",
        description=(
            "Run the first calculator/equipment-backed Irekei Assassin "
            "MAP-Elites experiment."
        ),
    )
    parser.add_argument("--iterations", type=int, default=24)
    parser.add_argument("--mutation-seed", type=int, default=7)
    parser.add_argument("--rollout-seeds", type=_csv_ints, default=(1, 2, 3))
    parser.add_argument(
        "--distances",
        type=_csv_floats,
        default=(6.0, 15.0, 40.0),
    )
    parser.add_argument("--max-ticks", type=int, default=600)
    parser.add_argument("--equipment-pool-size", type=int, default=12)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    report = run_irekei_assassin_search(
        IrekeiAssassinSearchConfig(
            iterations=arguments.iterations,
            mutation_seed=arguments.mutation_seed,
            rollout_seeds=arguments.rollout_seeds,
            starting_distances=arguments.distances,
            max_ticks=arguments.max_ticks,
            equipment_pool_size=arguments.equipment_pool_size,
        )
    )
    encoded = json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(encoded, end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8")
        print(
            f"Wrote {report.run.archive.cell_count} elites to "
            f"{arguments.output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
