from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .catalog import default_action_catalog
from .genome import compile_genome, reference_genomes
from .search import archive_to_dict, run_map_elites
from .simulator import CombatSimulator


def _duel(args: argparse.Namespace) -> int:
    catalog = default_action_catalog()
    league = reference_genomes()
    left_index = args.left % len(league)
    right_index = args.right % len(league)
    left_genome = league[left_index]
    right_genome = league[right_index]
    simulator = CombatSimulator(catalog, record_events=args.events)
    result = simulator.run_duel(
        compile_genome(left_genome),
        compile_genome(right_genome),
        seed=args.seed,
    )
    payload = {
        "left": left_genome.label,
        "right": right_genome.label,
        "winner_team": result.winner_team,
        "duration": result.duration,
        "left_state": {
            "health": result.combatants[0].health,
            "mana": result.combatants[0].mana,
            "stamina": result.combatants[0].stamina,
            "metrics": asdict(result.combatants[0].metrics),
        },
        "right_state": {
            "health": result.combatants[1].health,
            "mana": result.combatants[1].mana,
            "stamina": result.combatants[1].stamina,
            "metrics": asdict(result.combatants[1].metrics),
        },
    }
    if args.events:
        payload["events"] = [asdict(event) for event in result.events]
    print(json.dumps(payload, indent=2))
    return 0


def _search(args: argparse.Namespace) -> int:
    archive = run_map_elites(
        evaluations=args.evaluations,
        seed=args.seed,
        initial_random=args.initial_random,
        distance_bins=args.distance_bins,
        control_bins=args.control_bins,
    )
    payload = archive_to_dict(archive, top=args.top)
    encoded = json.dumps(payload, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
        print(f"wrote {output} with {payload['occupied_cells']} occupied cells")
    else:
        print(encoded)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bane-lab",
        description="Run deterministic Shadowbane-style combat experiments.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    duel = subparsers.add_parser("duel", help="run a deterministic reference duel")
    duel.add_argument("--left", type=int, default=0, help="reference build index")
    duel.add_argument("--right", type=int, default=1, help="reference build index")
    duel.add_argument("--seed", type=int, default=7)
    duel.add_argument("--events", action="store_true", help="include the event trace")
    duel.set_defaults(func=_duel)

    search = subparsers.add_parser("search", help="run the initial MAP-Elites search")
    search.add_argument("--evaluations", type=int, default=400)
    search.add_argument("--initial-random", type=int, default=64)
    search.add_argument("--seed", type=int, default=7)
    search.add_argument("--distance-bins", type=int, default=8)
    search.add_argument("--control-bins", type=int, default=8)
    search.add_argument("--top", type=int, default=20)
    search.add_argument("--output", type=str)
    search.set_defaults(func=_search)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
