from __future__ import annotations

from dataclasses import asdict, dataclass
from random import Random
from statistics import fmean

from .catalog import default_action_catalog
from .genome import (
    BuildGenome,
    compile_genome,
    mutate_genome,
    random_genome,
    reference_genomes,
)
from .simulator import CombatSimulator


@dataclass(frozen=True, slots=True)
class Evaluation:
    fitness: float
    win_rate: float
    mean_health_margin: float
    mean_duration: float
    mean_distance: float
    control_rate: float


@dataclass(frozen=True, slots=True)
class Elite:
    genome: BuildGenome
    evaluation: Evaluation
    distance_bin: int
    control_bin: int


class MapElitesArchive:
    def __init__(self, *, distance_bins: int = 8, control_bins: int = 8) -> None:
        self.distance_bins = distance_bins
        self.control_bins = control_bins
        self._cells: dict[tuple[int, int], Elite] = {}

    def descriptor_bins(self, evaluation: Evaluation) -> tuple[int, int]:
        distance_fraction = max(0.0, min(0.999999, evaluation.mean_distance / 18.0))
        control_fraction = max(0.0, min(0.999999, evaluation.control_rate))
        return (
            int(distance_fraction * self.distance_bins),
            int(control_fraction * self.control_bins),
        )

    def add(self, genome: BuildGenome, evaluation: Evaluation) -> bool:
        distance_bin, control_bin = self.descriptor_bins(evaluation)
        key = (distance_bin, control_bin)
        incumbent = self._cells.get(key)
        if incumbent is None or evaluation.fitness > incumbent.evaluation.fitness:
            self._cells[key] = Elite(genome, evaluation, distance_bin, control_bin)
            return True
        return False

    def random_elite(self, rng: Random) -> Elite:
        if not self._cells:
            raise LookupError("archive is empty")
        return rng.choice(tuple(self._cells.values()))

    @property
    def elites(self) -> tuple[Elite, ...]:
        return tuple(self._cells.values())

    def best(self, limit: int = 10) -> tuple[Elite, ...]:
        return tuple(
            sorted(self._cells.values(), key=lambda elite: elite.evaluation.fitness, reverse=True)[
                :limit
            ]
        )


def evaluate_genome(
    genome: BuildGenome,
    *,
    simulator: CombatSimulator,
    opponents: tuple[BuildGenome, ...] | None = None,
    seeds: tuple[int, ...] = (11, 29),
) -> Evaluation:
    opponents = opponents or reference_genomes()
    candidate = compile_genome(genome, name=genome.label)

    outcomes: list[float] = []
    margins: list[float] = []
    durations: list[float] = []
    distances: list[float] = []
    control_rates: list[float] = []

    for opponent_genome in opponents:
        opponent = compile_genome(opponent_genome, name=opponent_genome.label)
        for seed in seeds:
            for candidate_on_left in (True, False):
                left, right = (candidate, opponent) if candidate_on_left else (opponent, candidate)
                result = simulator.run_duel(left, right, seed=seed)
                candidate_index = 0 if candidate_on_left else 1
                enemy_index = 1 - candidate_index
                candidate_state = result.combatants[candidate_index]
                enemy_state = result.combatants[enemy_index]
                candidate_team = candidate_state.team

                if result.winner_team is None:
                    outcomes.append(0.5)
                elif result.winner_team == candidate_team:
                    outcomes.append(1.0)
                else:
                    outcomes.append(0.0)

                candidate_remaining = candidate_state.health / candidate_state.stats.max_health
                enemy_remaining = enemy_state.health / enemy_state.stats.max_health
                margins.append(candidate_remaining - enemy_remaining)
                durations.append(result.duration)
                distances.append(candidate_state.metrics.mean_distance)
                control_rates.append(candidate_state.metrics.control_action_rate)

    win_rate = fmean(outcomes)
    mean_margin = fmean(margins)
    mean_duration = fmean(durations)
    # Fitness rewards broad matchup strength and health advantage, while mildly
    # preferring decisive outcomes over endless sustain loops.
    fitness = win_rate + 0.22 * mean_margin - 0.04 * (mean_duration / simulator.max_time_seconds)
    return Evaluation(
        fitness=fitness,
        win_rate=win_rate,
        mean_health_margin=mean_margin,
        mean_duration=mean_duration,
        mean_distance=fmean(distances),
        control_rate=fmean(control_rates),
    )


def run_map_elites(
    *,
    evaluations: int = 800,
    seed: int = 7,
    initial_random: int = 96,
    distance_bins: int = 8,
    control_bins: int = 8,
) -> MapElitesArchive:
    if evaluations <= 0:
        raise ValueError("evaluations must be positive")
    rng = Random(seed)
    catalog = default_action_catalog()
    simulator = CombatSimulator(catalog, tick_seconds=0.20, max_time_seconds=45.0)
    archive = MapElitesArchive(distance_bins=distance_bins, control_bins=control_bins)

    for index in range(evaluations):
        if index < initial_random or not archive.elites:
            genome = random_genome(rng, label=f"random-{index:05d}")
        else:
            parent = archive.random_elite(rng).genome
            genome = mutate_genome(parent, rng)
        evaluation = evaluate_genome(genome, simulator=simulator)
        archive.add(genome, evaluation)
    return archive


def archive_to_dict(archive: MapElitesArchive, *, top: int = 20) -> dict:
    return {
        "distance_bins": archive.distance_bins,
        "control_bins": archive.control_bins,
        "occupied_cells": len(archive.elites),
        "top_elites": [
            {
                "distance_bin": elite.distance_bin,
                "control_bin": elite.control_bin,
                "evaluation": asdict(elite.evaluation),
                "genome": asdict(elite.genome),
            }
            for elite in archive.best(top)
        ],
        "cells": [
            {
                "distance_bin": elite.distance_bin,
                "control_bin": elite.control_bin,
                "evaluation": asdict(elite.evaluation),
                "genome": asdict(elite.genome),
            }
            for elite in sorted(
                archive.elites, key=lambda item: (item.distance_bin, item.control_bin)
            )
        ],
    }
