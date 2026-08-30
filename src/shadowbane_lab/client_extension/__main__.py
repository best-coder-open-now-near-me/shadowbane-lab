"""Command-line entry point for safe WonderBane extension preparation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from shadowbane_lab.client_extension.baseline import (
    ClientBaselineError,
    freeze_client_baseline,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m shadowbane_lab.client_extension",
        description=(
            "Prepare immutable WonderBane client evidence and disposable extension packages."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser(
        "freeze-baseline",
        help="copy and verify a pristine client tree without modifying its source",
    )
    freeze.add_argument("source_directory", type=Path)
    freeze.add_argument("frozen_directory", type=Path)
    freeze.add_argument("--executable", default="sb.exe")
    freeze.add_argument("--repository-revision", required=True)
    freeze.add_argument("--pretty", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        baseline = freeze_client_baseline(
            arguments.source_directory,
            arguments.frozen_directory,
            executable_relative_path=arguments.executable,
            repository_revision=arguments.repository_revision,
        )
    except (ClientBaselineError, OSError, ValueError) as exc:
        print(f"client extension preparation failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            baseline.as_dict(),
            sort_keys=True,
            indent=2 if arguments.pretty else None,
            separators=None if arguments.pretty else (",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
