from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from random import Random

from .catalog import SEARCHABLE_ACTION_IDS
from .model import BuildStats, PolicyTuning


ALLOCATION_NAMES = ("vitality", "power", "control", "sustain", "mobility")


@dataclass(frozen=True, slots=True)
class BuildGenome:
    allocations: tuple[float, float, float, float, float]
    kit: tuple[str, str, str, str]
    aggression: float
    sustain_bias: float
    control_bias: float
    defense_bias: float
    resource_conservation: float
    preferred_range: float
    finisher_bias: float
    label: str = "candidate"

    def normalized(self) -> BuildGenome:
        clipped = tuple(max(0.001, value) for value in self.allocations)
        total = sum(clipped)
        ordered_kit = list(dict.fromkeys(self.kit))
        for action_id in SEARCHABLE_ACTION_IDS:
            if len(ordered_kit) >= 4:
                break
            if action_id not in ordered_kit:
                ordered_kit.append(action_id)

        return BuildGenome(
            allocations=tuple(value / total for value in clipped),  # type: ignore[arg-type]
            kit=tuple(ordered_kit[:4]),  # type: ignore[arg-type]
            aggression=max(0.2, min(2.5, self.aggression)),
            sustain_bias=max(0.2, min(2.5, self.sustain_bias)),
            control_bias=max(0.2, min(2.5, self.control_bias)),
            defense_bias=max(0.2, min(2.5, self.defense_bias)),
            resource_conservation=max(0.0, min(2.0, self.resource_conservation)),
            preferred_range=max(1.0, min(16.0, self.preferred_range)),
            finisher_bias=max(0.2, min(2.5, self.finisher_bias)),
            label=self.label,
        )


def _random_simplex(rng: Random, size: int) -> tuple[float, ...]:
    values = [-log(max(rng.random(), 1e-12)) for _ in range(size)]
    total = sum(values)
    return tuple(value / total for value in values)


def random_genome(rng: Random, *, label: str = "candidate") -> BuildGenome:
    kit = tuple(rng.sample(SEARCHABLE_ACTION_IDS, 4))
    return BuildGenome(
        allocations=_random_simplex(rng, 5),  # type: ignore[arg-type]
        kit=kit,  # type: ignore[arg-type]
        aggression=rng.uniform(0.55, 1.8),
        sustain_bias=rng.uniform(0.55, 1.8),
        control_bias=rng.uniform(0.55, 1.8),
        defense_bias=rng.uniform(0.55, 1.8),
        resource_conservation=rng.uniform(0.0, 1.2),
        preferred_range=rng.uniform(1.5, 14.0),
        finisher_bias=rng.uniform(0.55, 1.8),
        label=label,
    ).normalized()


def mutate_genome(parent: BuildGenome, rng: Random, *, sigma: float = 0.12) -> BuildGenome:
    allocations = tuple(value * exp(rng.gauss(0.0, sigma)) for value in parent.allocations)
    kit = list(parent.kit)
    if rng.random() < 0.35:
        slot = rng.randrange(len(kit))
        available = [action_id for action_id in SEARCHABLE_ACTION_IDS if action_id not in kit]
        if available:
            kit[slot] = rng.choice(available)
    if rng.random() < 0.10:
        rng.shuffle(kit)

    return BuildGenome(
        allocations=allocations,  # type: ignore[arg-type]
        kit=tuple(kit),  # type: ignore[arg-type]
        aggression=parent.aggression * exp(rng.gauss(0.0, sigma)),
        sustain_bias=parent.sustain_bias * exp(rng.gauss(0.0, sigma)),
        control_bias=parent.control_bias * exp(rng.gauss(0.0, sigma)),
        defense_bias=parent.defense_bias * exp(rng.gauss(0.0, sigma)),
        resource_conservation=max(
            0.0, parent.resource_conservation + rng.gauss(0.0, sigma * 0.8)
        ),
        preferred_range=parent.preferred_range + rng.gauss(0.0, sigma * 12.0),
        finisher_bias=parent.finisher_bias * exp(rng.gauss(0.0, sigma)),
        label="mutant",
    ).normalized()


def compile_genome(genome: BuildGenome, *, name: str | None = None) -> tuple[BuildStats, PolicyTuning]:
    genome = genome.normalized()
    vitality, power, control, sustain, mobility = genome.allocations

    stats = BuildStats(
        name=name or genome.label,
        max_health=82.0 + 155.0 * vitality,
        max_mana=35.0 + 95.0 * (0.45 * power + 0.30 * control + 0.25 * sustain),
        max_stamina=48.0 + 80.0 * (0.55 * mobility + 0.45 * vitality),
        health_regen=0.10 + 1.35 * sustain,
        mana_regen=0.55 + 2.10 * (0.40 * sustain + 0.35 * control + 0.25 * power),
        stamina_regen=1.6 + 3.5 * (0.55 * mobility + 0.45 * vitality),
        move_speed=3.0 + 5.0 * mobility,
        accuracy=62.0 + 70.0 * (0.62 * power + 0.38 * control),
        evasion=45.0 + 95.0 * mobility,
        physical_resistance=min(0.48, 0.03 + 0.43 * vitality),
        arcane_resistance=min(0.40, 0.02 + 0.22 * vitality + 0.13 * control),
        fire_resistance=min(0.40, 0.02 + 0.20 * vitality + 0.14 * sustain),
        power=8.0 + 57.0 * power,
        control=8.0 + 57.0 * control,
        sustain=8.0 + 57.0 * sustain,
        mobility=8.0 + 57.0 * mobility,
        vitality=8.0 + 57.0 * vitality,
        action_ids=("basic_strike", *genome.kit),
    )
    tuning = PolicyTuning(
        aggression=genome.aggression,
        sustain_bias=genome.sustain_bias,
        control_bias=genome.control_bias,
        defense_bias=genome.defense_bias,
        resource_conservation=genome.resource_conservation,
        preferred_range=genome.preferred_range,
        finisher_bias=genome.finisher_bias,
    )
    return stats, tuning


def _g(
    allocations: tuple[float, float, float, float, float],
    kit: tuple[str, str, str, str],
    *,
    label: str,
    aggression: float,
    sustain: float,
    control: float,
    defense: float,
    conservation: float,
    preferred_range: float,
    finisher: float,
) -> BuildGenome:
    return BuildGenome(
        allocations=allocations,
        kit=kit,
        aggression=aggression,
        sustain_bias=sustain,
        control_bias=control,
        defense_bias=defense,
        resource_conservation=conservation,
        preferred_range=preferred_range,
        finisher_bias=finisher,
        label=label,
    ).normalized()


def reference_genomes() -> tuple[BuildGenome, ...]:
    """A small opponent league for initial fitness evaluation."""

    return (
        _g(
            (0.37, 0.30, 0.13, 0.10, 0.10),
            ("quick_jab", "stun_bash", "ward", "siphon"),
            label="bruiser",
            aggression=1.35,
            sustain=0.9,
            control=1.0,
            defense=1.1,
            conservation=0.3,
            preferred_range=2.2,
            finisher=1.25,
        ),
        _g(
            (0.10, 0.30, 0.20, 0.08, 0.32),
            ("arc_bolt", "cripple", "blink_back", "ember"),
            label="kiter",
            aggression=1.15,
            sustain=0.6,
            control=1.25,
            defense=1.0,
            conservation=0.45,
            preferred_range=11.5,
            finisher=1.1,
        ),
        _g(
            (0.25, 0.10, 0.10, 0.42, 0.13),
            ("mend", "siphon", "ward", "wither"),
            label="sustain",
            aggression=0.8,
            sustain=1.8,
            control=0.8,
            defense=1.5,
            conservation=0.65,
            preferred_range=6.0,
            finisher=0.75,
        ),
        _g(
            (0.15, 0.10, 0.48, 0.12, 0.15),
            ("silence", "cripple", "stun_bash", "mana_burn"),
            label="controller",
            aggression=0.75,
            sustain=0.8,
            control=1.9,
            defense=1.0,
            conservation=0.6,
            preferred_range=7.5,
            finisher=0.8,
        ),
        _g(
            (0.07, 0.52, 0.10, 0.05, 0.26),
            ("arc_bolt", "ember", "silence", "shadow_step"),
            label="glass_cannon",
            aggression=1.9,
            sustain=0.35,
            control=0.8,
            defense=0.4,
            conservation=0.1,
            preferred_range=10.0,
            finisher=1.9,
        ),
    )
