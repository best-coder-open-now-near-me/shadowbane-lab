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
from shadowbane_lab.client_extension.manifest import PatchManifestError, load_patch_manifest
from shadowbane_lab.client_extension.package import (
    ClientPatchPackageError,
    discard_patched_client_copy,
    prepare_patched_client_copy,
    verify_patched_client_copy,
)
from shadowbane_lab.client_extension.resolver import (
    PatchResolutionError,
    align_patch_sites,
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
    align = commands.add_parser(
        "align",
        help="produce non-authorizing patch-site alignment evidence for one PE",
    )
    align.add_argument("candidate_executable", type=Path)
    align.add_argument("manifest", type=Path)
    align.add_argument("--pretty", action="store_true")
    prepare = commands.add_parser(
        "prepare-copy",
        help="atomically create a new disposable patched client copy",
    )
    prepare.add_argument("frozen_directory", type=Path)
    prepare.add_argument("destination_directory", type=Path)
    prepare.add_argument("manifest", type=Path)
    prepare.add_argument("extension_artifact", type=Path)
    prepare.add_argument("--dry-run", action="store_true")
    prepare.add_argument("--pretty", action="store_true")
    verify = commands.add_parser(
        "verify-copy",
        help="reread a disposable patched client copy and its package evidence",
    )
    verify.add_argument("directory", type=Path)
    verify.add_argument("--pretty", action="store_true")
    discard = commands.add_parser(
        "discard-copy",
        help="discard an exactly verified disposable copy and write a rollback receipt",
    )
    discard.add_argument("directory", type=Path)
    discard.add_argument("receipt", type=Path)
    discard.add_argument("--pretty", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "freeze-baseline":
            payload = freeze_client_baseline(
                arguments.source_directory,
                arguments.frozen_directory,
                executable_relative_path=arguments.executable,
                repository_revision=arguments.repository_revision,
            ).as_dict()
        elif arguments.command == "align":
            manifest = load_patch_manifest(arguments.manifest)
            payload = align_patch_sites(
                arguments.candidate_executable.read_bytes(),
                manifest,
            ).as_dict()
        elif arguments.command == "prepare-copy":
            manifest = load_patch_manifest(arguments.manifest)
            payload = prepare_patched_client_copy(
                arguments.frozen_directory,
                arguments.destination_directory,
                manifest,
                arguments.extension_artifact,
                dry_run=arguments.dry_run,
            ).as_dict()
        elif arguments.command == "verify-copy":
            payload = verify_patched_client_copy(arguments.directory).as_dict()
        elif arguments.command == "discard-copy":
            payload = discard_patched_client_copy(
                arguments.directory,
                arguments.receipt,
            ).as_dict()
        else:
            raise AssertionError(f"unhandled command: {arguments.command}")
    except (
        ClientBaselineError,
        ClientPatchPackageError,
        PatchManifestError,
        PatchResolutionError,
        OSError,
        ValueError,
    ) as exc:
        print(f"client extension preparation failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            payload,
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
