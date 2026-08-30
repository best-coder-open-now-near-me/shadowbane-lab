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
from shadowbane_lab.client_extension.bootstrap_author import (
    BootstrapAuthoringError,
    author_reviewed_bootstrap_file,
)
from shadowbane_lab.client_extension.bootstrap_inspection import (
    BootstrapInspectionError,
    inspect_bootstrap_file,
)
from shadowbane_lab.client_extension.heartbeat import (
    ExtensionHeartbeatError,
    load_extension_heartbeat,
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
from shadowbane_lab.client_extension.texture_patch import (
    TexturePatchError,
    author_texture_patch_manifest,
    load_texture_patch_manifest,
)


def _texture_assignment(value: str) -> tuple[tuple[int, int], Path]:
    identifier, separator, filename = value.partition("=")
    if not separator or not identifier or not filename:
        raise argparse.ArgumentTypeError("texture replacement must be [GROUP:]RESOURCE=PNG")
    group_text, group_separator, resource_text = identifier.partition(":")
    try:
        if group_separator:
            key = int(group_text, 0), int(resource_text, 0)
        else:
            key = 0, int(group_text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("texture resource key must contain integers") from exc
    path = Path(filename)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"texture artifact does not exist: {path}")
    return key, path


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
    prepare.add_argument("--texture-patch-manifest", type=Path)
    prepare.add_argument("--texture-artifact-directory", type=Path)
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
    heartbeat = commands.add_parser(
        "verify-heartbeat",
        help="strictly parse native no-op initialization evidence",
    )
    heartbeat.add_argument("heartbeat", type=Path)
    heartbeat.add_argument("--pretty", action="store_true")
    inspect_bootstrap = commands.add_parser(
        "inspect-bootstrap",
        help="collect read-only client-specific loader evidence",
    )
    inspect_bootstrap.add_argument("executable", type=Path)
    inspect_bootstrap.add_argument("--output", type=Path)
    inspect_bootstrap.add_argument("--pretty", action="store_true")
    author_bootstrap = commands.add_parser(
        "author-bootstrap",
        help="author the exact reviewed WonderBane loader manifest",
    )
    author_bootstrap.add_argument("source_executable", type=Path)
    author_bootstrap.add_argument("extension_artifact", type=Path)
    author_bootstrap.add_argument("output_manifest", type=Path)
    author_bootstrap.add_argument("--extension-version", default="1.0.0")
    author_bootstrap.add_argument("--pretty", action="store_true")
    author_textures = commands.add_parser(
        "author-texture-patch",
        help="author a hash-pinned texture-cache overlay manifest",
    )
    author_textures.add_argument("source_cache", type=Path)
    author_textures.add_argument("output_manifest", type=Path)
    author_textures.add_argument("replacements", nargs="+", type=_texture_assignment)
    author_textures.add_argument("--patch-id", required=True)
    author_textures.add_argument(
        "--cache-relative-path",
        default="cache/Textures.cache",
    )
    author_textures.add_argument("--pretty", action="store_true")
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
            texture_manifest = (
                None
                if arguments.texture_patch_manifest is None
                else load_texture_patch_manifest(arguments.texture_patch_manifest)
            )
            payload = prepare_patched_client_copy(
                arguments.frozen_directory,
                arguments.destination_directory,
                manifest,
                arguments.extension_artifact,
                texture_patch_manifest=texture_manifest,
                texture_artifact_directory=arguments.texture_artifact_directory,
                dry_run=arguments.dry_run,
            ).as_dict()
        elif arguments.command == "verify-copy":
            payload = verify_patched_client_copy(arguments.directory).as_dict()
        elif arguments.command == "discard-copy":
            payload = discard_patched_client_copy(
                arguments.directory,
                arguments.receipt,
            ).as_dict()
        elif arguments.command == "verify-heartbeat":
            payload = load_extension_heartbeat(arguments.heartbeat).as_dict()
        elif arguments.command == "inspect-bootstrap":
            payload = inspect_bootstrap_file(
                arguments.executable,
                output_path=arguments.output,
            )
        elif arguments.command == "author-bootstrap":
            payload = author_reviewed_bootstrap_file(
                arguments.source_executable,
                arguments.extension_artifact,
                arguments.output_manifest,
                extension_version=arguments.extension_version,
            ).as_dict()
        elif arguments.command == "author-texture-patch":
            artifacts = dict(arguments.replacements)
            if len(artifacts) != len(arguments.replacements):
                raise ValueError("texture replacement resource keys must be unique")
            texture_manifest = author_texture_patch_manifest(
                arguments.source_cache,
                artifacts,
                patch_id=arguments.patch_id,
                cache_relative_path=arguments.cache_relative_path,
            )
            if arguments.output_manifest.exists():
                raise ValueError(
                    f"texture-patch manifest already exists: {arguments.output_manifest}"
                )
            arguments.output_manifest.parent.mkdir(parents=True, exist_ok=True)
            try:
                with arguments.output_manifest.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(
                        json.dumps(
                            texture_manifest.as_dict(),
                            sort_keys=True,
                            indent=2,
                            ensure_ascii=True,
                            allow_nan=False,
                        )
                        + "\n"
                    )
            except FileExistsError as exc:
                raise ValueError(
                    f"texture-patch manifest already exists: {arguments.output_manifest}"
                ) from exc
            payload = texture_manifest.as_dict()
        else:
            raise AssertionError(f"unhandled command: {arguments.command}")
    except (
        ClientBaselineError,
        ClientPatchPackageError,
        BootstrapInspectionError,
        BootstrapAuthoringError,
        ExtensionHeartbeatError,
        PatchManifestError,
        PatchResolutionError,
        TexturePatchError,
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
