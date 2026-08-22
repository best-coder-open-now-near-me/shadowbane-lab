from __future__ import annotations

from random import Random

from banesim.catalog import default_action_catalog
from banesim.genome import mutate_genome, random_genome
from banesim.search import archive_to_dict, run_map_elites


def test_random_and_mutated_genomes_are_valid() -> None:
    rng = Random(42)
    catalog = default_action_catalog()
    genome = random_genome(rng)

    for _ in range(100):
        genome = mutate_genome(genome, rng)
        assert abs(sum(genome.allocations) - 1.0) < 1e-9
        assert len(genome.kit) == 4
        assert len(set(genome.kit)) == 4
        assert all(action_id in catalog for action_id in genome.kit)
        assert 1.0 <= genome.preferred_range <= 16.0


def test_small_map_elites_run_is_reproducible() -> None:
    first = run_map_elites(evaluations=12, initial_random=12, seed=3, distance_bins=4, control_bins=4)
    second = run_map_elites(evaluations=12, initial_random=12, seed=3, distance_bins=4, control_bins=4)

    assert archive_to_dict(first, top=5) == archive_to_dict(second, top=5)
    assert len(first.elites) > 0
