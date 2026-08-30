"""Command-line entry point for the offline client-build alignment utility."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from shadowbane_lab.client_alignment.compare import ClientAlignmentError, compare_client_builds
from shadowbane_lab.client_alignment.pe import PeInspectionError, inspect_pe
from shadowbane_lab.client_alignment.profiles import ProfileInventoryError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m shadowbane_lab.client_alignment",
        description=(
            "Inspect and compare WonderBane client executables offline. "
            "The utility never launches or modifies either input file."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    inspect = commands.add_parser("inspect", help="fingerprint one PE executable")
    inspect.add_argument("executable", type=Path)
    _add_output_options(inspect)

    compare = commands.add_parser(
        "compare",
        help="compare a reviewed reference executable with a candidate update",
    )
    compare.add_argument("reference", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument(
        "--profiles",
        type=Path,
        help="alternate directory containing hash-pinned native profile JSON files",
    )
    _add_output_options(compare)
    return parser


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", type=Path, help="write JSON to a new file")
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")


def _encode(payload: dict[str, Any], *, pretty: bool) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        allow_nan=False,
    ) + "\n"


def _write(text: str, output: Path | None) -> None:
    if output is None:
        sys.stdout.write(text)
        return
    try:
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise ClientAlignmentError(f"output already exists: {output}") from exc
    except OSError as exc:
        raise ClientAlignmentError(f"could not write output: {output}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "inspect":
            payload = {"schema_version": 1, "image": inspect_pe(arguments.executable).as_dict()}
        else:
            payload = compare_client_builds(
                arguments.reference,
                arguments.candidate,
                profile_directory=arguments.profiles,
            ).as_dict()
        _write(_encode(payload, pretty=arguments.pretty), arguments.output)
    except (ClientAlignmentError, PeInspectionError, ProfileInventoryError) as exc:
        print(f"client alignment failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
