"""Command-line entry point for progression-bracket duel rollouts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from shadowbane_lab.rollouts import matched_progression_duels


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
    parser.add_argument("--levels", type=_integers, default=(10, 15, 22, 26, 40))
    parser.add_argument("--ranks", type=_integers, default=(0, 20, 40))
    parser.add_argument("--max-ticks", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
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
