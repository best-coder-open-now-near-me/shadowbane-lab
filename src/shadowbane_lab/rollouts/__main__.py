"""Command-line entry point for progression-bracket duel rollouts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from shadowbane_lab.rollouts import matched_progression_duels, progression_duel_matrix


def _integers(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc
    if not result:
        raise argparse.ArgumentTypeError("expected at least one integer")
    return result


def _numbers(value: str) -> tuple[float, ...]:
    try:
        result = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated numbers") from exc
    if not result:
        raise argparse.ArgumentTypeError("expected at least one number")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m shadowbane_lab.rollouts")
    parser.add_argument("--levels", type=_integers, default=(10, 15, 18, 19, 22, 26, 28, 75))
    parser.add_argument("--ranks", type=_integers, default=(0, 10, 20, 40))
    parser.add_argument("--distance", type=float, default=15.0)
    parser.add_argument("--max-ticks", type=int, default=1_200)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--distances", type=_numbers, default=(15.0, 60.0, 110.0))
    parser.add_argument("--seeds", type=_integers)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)

    if arguments.matrix:
        cells = progression_duel_matrix(
            levels=arguments.levels,
            power_ranks=arguments.ranks,
            starting_distances=arguments.distances,
            seeds=arguments.seeds or (arguments.seed,),
            max_ticks=arguments.max_ticks,
        )
        if arguments.json:
            print(
                json.dumps(
                    [cell.as_dict() for cell in cells],
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        print("Focus prerequisites are assumed satisfied; each rank is an explicit bracket.")
        print("level  rank  range  A-wins  W-wins  draws  limits  mean_ticks  traces")
        for cell in cells:
            print(
                f"{cell.level:>5}  {cell.power_rank:>4}  {cell.starting_distance:>5.1f}  "
                f"{cell.assassin_wins:>6}  {cell.warlock_wins:>6}  {cell.draws:>5}  "
                f"{cell.time_limits:>6}  {cell.mean_ticks:>10.1f}  "
                f"{cell.unique_trace_count:>6}"
            )
        return 0

    results = matched_progression_duels(
        levels=arguments.levels,
        power_ranks=arguments.ranks,
        starting_distance=arguments.distance,
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
    print("level  rank  winner     ticks  assassin_hp  warlock_hp  cancelled")
    for level, rank, result in results:
        winner = result.winner_entity_id or "draw"
        assassin, warlock = result.combatants
        print(
            f"{level:>5}  {rank:>4}  {winner:<9}  {result.ticks:>5}  "
            f"{assassin.final_health:>11.1f}  {warlock.final_health:>10.1f}  "
            f"{result.cancelled_scheduled_items:>9}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
