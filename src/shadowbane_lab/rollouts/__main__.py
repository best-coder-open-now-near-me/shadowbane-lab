"""Command-line entry point for progression-bracket duel rollouts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from shadowbane_lab.rollouts import (
    frost_walker_observed_config,
    matched_progression_duels,
    run_nearby_mob_simulation,
    run_pure_pve_batch,
)


def _integers(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc
    if not result:
        raise argparse.ArgumentTypeError("expected at least one integer")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m shadowbane_lab.rollouts")
    parser.add_argument(
        "--scenario",
        choices=("duels", "frost-walker", "pure-frost-walker"),
        default="duels",
    )
    parser.add_argument("--levels", type=_integers, default=(10, 15, 22, 26, 40))
    parser.add_argument("--ranks", type=_integers, default=(0, 20, 40))
    parser.add_argument("--max-ticks", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--episodes", type=int, default=1_000)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.scenario == "pure-frost-walker":
        result = run_pure_pve_batch(
            frost_walker_observed_config(max_ticks=arguments.max_ticks),
            episodes=arguments.episodes,
            seed_start=arguments.seed,
        )
        if arguments.json:
            print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        else:
            mean_ttk = (
                "n/a"
                if result.mean_kill_time_ms is None
                else f"{result.mean_kill_time_ms:.1f}ms"
            )
            mean_attacks = (
                "n/a"
                if result.mean_attacks_to_kill is None
                else f"{result.mean_attacks_to_kill:.3f}"
            )
            print(
                f"{result.profile_id}: {result.kills}/{result.episodes} kills; "
                f"mean TTK={mean_ttk}; mean attacks={mean_attacks}"
            )
            print(f"Attacks-to-kill: {[item.as_dict() for item in result.attacks_to_kill]}")
            print(f"Damage rolls: {[item.as_dict() for item in result.damage_rolls]}")
        return 0

    if arguments.scenario == "frost-walker":
        result = run_nearby_mob_simulation(
            frost_walker_observed_config(
                seed=arguments.seed,
                max_ticks=arguments.max_ticks,
            )
        )
        if arguments.json:
            print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        else:
            print(
                f"{result.profile_id}: {result.terminal_reason}; "
                f"kills={result.kills}, attacks={list(result.attack_rolls)}, "
                f"time={result.sim_time_ms}ms"
            )
            print("Assumptions:")
            for assumption in result.assumptions:
                print(f"- {assumption}")
        return 0

    results = matched_progression_duels(
        levels=arguments.levels,
        power_ranks=arguments.ranks,
        max_ticks=arguments.max_ticks,
        seed=arguments.seed,
    )
    if arguments.json:
        print(
            json.dumps(
                [
                    {"level": level, "power_rank": rank, **result.as_dict()}
                    for level, rank, result in results
                ],
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    print("Focus prerequisites are assumed satisfied; power rank is an explicit bracket.")
    print("level  rank  winner     ticks  assassin_hp  warlock_hp")
    for level, rank, result in results:
        winner = result.winner_entity_id or "draw"
        assassin, warlock = result.combatants
        print(
            f"{level:>5}  {rank:>4}  {winner:<9}  {result.ticks:>5}  "
            f"{assassin.final_health:>11.1f}  {warlock.final_health:>10.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
