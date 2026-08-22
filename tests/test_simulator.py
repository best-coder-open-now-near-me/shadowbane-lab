from __future__ import annotations

from banesim.catalog import default_action_catalog
from banesim.genome import compile_genome, reference_genomes
from banesim.simulator import CombatSimulator


def _snapshot(result):
    return (
        result.winner_team,
        round(result.duration, 6),
        tuple(
            (
                round(actor.health, 6),
                round(actor.mana, 6),
                round(actor.stamina, 6),
                round(actor.position.x, 6),
                round(actor.position.y, 6),
                round(actor.metrics.damage_dealt, 6),
                round(actor.metrics.healing_done, 6),
                actor.metrics.actions_started,
            )
            for actor in result.combatants
        ),
        tuple(result.events),
    )


def test_same_seed_produces_identical_duel() -> None:
    catalog = default_action_catalog()
    simulator = CombatSimulator(catalog, record_events=True)
    left, right = reference_genomes()[:2]

    first = simulator.run_duel(compile_genome(left), compile_genome(right), seed=1234)
    second = simulator.run_duel(compile_genome(left), compile_genome(right), seed=1234)

    assert _snapshot(first) == _snapshot(second)


def test_resources_and_health_stay_in_bounds() -> None:
    catalog = default_action_catalog()
    simulator = CombatSimulator(catalog)
    league = reference_genomes()

    for seed in range(10):
        result = simulator.run_duel(
            compile_genome(league[seed % len(league)]),
            compile_genome(league[(seed + 1) % len(league)]),
            seed=seed,
        )
        for actor in result.combatants:
            assert 0.0 <= actor.health <= actor.stats.max_health
            assert 0.0 <= actor.mana <= actor.stats.max_mana
            assert 0.0 <= actor.stamina <= actor.stats.max_stamina
            assert actor.metrics.invalid_actions == 0


def test_reference_matchup_resolves_or_reaches_clean_timeout() -> None:
    catalog = default_action_catalog()
    simulator = CombatSimulator(catalog, max_time_seconds=20.0)
    bruiser, kiter = reference_genomes()[:2]

    result = simulator.run_duel(compile_genome(bruiser), compile_genome(kiter), seed=9)

    assert 0.0 < result.duration <= 20.0
    assert result.winner_team in {None, 0, 1}
    assert any(actor.metrics.actions_started > 0 for actor in result.combatants)


def test_primitive_recipients_are_explicit() -> None:
    from banesim.model import CombatantState, StatusKind, Vec2

    catalog = default_action_catalog()
    left_genome, right_genome = reference_genomes()[:2]
    left_stats, left_tuning = compile_genome(left_genome)
    right_stats, right_tuning = compile_genome(right_genome)
    actor = CombatantState.from_build(
        index=0,
        team=0,
        stats=left_stats,
        tuning=left_tuning,
        position=Vec2(0.0, 0.0),
    )
    target = CombatantState.from_build(
        index=1,
        team=1,
        stats=right_stats,
        tuning=right_tuning,
        position=Vec2(2.0, 0.0),
    )
    simulator = CombatSimulator(catalog)

    simulator._resolve_action(actor, target, catalog["ward"], 0.0, [])
    assert StatusKind.WARD in actor.statuses
    assert StatusKind.WARD not in target.statuses

    actor.health -= 25.0
    before = actor.health
    simulator._resolve_action(actor, target, catalog["siphon"], 0.0, [])
    assert actor.health > before
