"""Command-line entry points for legal build compilation and archive preparation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from shadowbane_lab.rollouts.ruleset import load_wonderbane_guide_duel_ruleset

from . import (
    LegalBuildCompileError,
    LegalBuildCompilePolicy,
    LegalBuildCompiler,
    load_legal_build_genome,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m shadowbane_lab.optimization",
        description="Compile calculator-legal build genomes without inventing mechanics.",
    )
    parser.add_argument("genome", type=Path)
    parser.add_argument(
        "--no-ruleset",
        action="store_true",
        help="Validate only the calculator chassis and equipment construction boundary.",
    )
    parser.add_argument(
        "--allow-ruleset-overrides",
        action="store_true",
        help="Admit compiled-with-override actions into a source-candidate build.",
    )
    parser.add_argument(
        "--apply-candidate-equipment-values",
        action="store_true",
        help="Apply historical-candidate base item values and record the acceptance explicitly.",
    )
    parser.add_argument(
        "--require-simulation-ready",
        action="store_true",
        help="Fail unless every selected mechanic is strict and fully resolved.",
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)

    try:
        genome = load_legal_build_genome(arguments.genome)
        ruleset = None
        if not arguments.no_ruleset:
            ruleset = load_wonderbane_guide_duel_ruleset(
                rank_overrides=dict(genome.power_ranks)
            )
        compiler = LegalBuildCompiler.bundled(
            ruleset=ruleset,
            policy=LegalBuildCompilePolicy(
                allow_ruleset_overrides=arguments.allow_ruleset_overrides,
                apply_candidate_equipment_values=(
                    arguments.apply_candidate_equipment_values
                ),
                require_simulation_ready=arguments.require_simulation_ready,
            ),
        )
        result = compiler.compile(genome)
    except (LegalBuildCompileError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": type(exc).__name__,
                    "detail": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    encoded = json.dumps(
        {"ok": True, "compiled_build": result.as_dict()},
        indent=2,
        sort_keys=True,
    ) + "\n"
    if arguments.output is None:
        print(encoded, end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8")
        print(arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
