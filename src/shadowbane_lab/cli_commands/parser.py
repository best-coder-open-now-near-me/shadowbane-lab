"""Command parser construction for the Shadowbane Lab CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from shadowbane_lab.evidence import ArtifactKind


def _integer_argument(value: str) -> int:
    try:
        parsed = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer or 0x-prefixed value") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must not be negative")
    return parsed


def _add_process_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pid", type=int, help="target one client when multiple are open")
    parser.add_argument(
        "--process",
        action="append",
        dest="process_names",
        help="allowed executable name; may be repeated (default: Shadowbane.exe)",
    )


def _add_scan_arguments(parser: argparse.ArgumentParser) -> None:
    _add_process_arguments(parser)
    parser.add_argument("--max-matches", type=int, default=50)
    parser.add_argument("--max-scan-mib", type=int, default=256)
    parser.add_argument("--context-bytes", type=int, default=32)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")


def _add_experiment_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("case", type=Path)
    parser.add_argument("experiment", type=Path)
    parser.add_argument("fingerprint", type=Path)
    parser.add_argument("store", type=Path)
    parser.add_argument("manifest_directory", type=Path)
    parser.add_argument("--execution-nonce", required=True)
    parser.add_argument(
        "--recorded",
        type=Path,
        help="finite recorded observations; omission is dry-run",
    )
    parser.add_argument("--json", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shadowbane-lab")
    commands = parser.add_subparsers(dest="command", required=True)

    evidence = commands.add_parser(
        "evidence", help="manage immutable content-addressed research evidence"
    )
    evidence_commands = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_init = evidence_commands.add_parser("init", help="initialize an empty evidence store")
    evidence_init.add_argument("store", type=Path)
    evidence_init.add_argument("--store-id")
    evidence_init.add_argument("--json", action="store_true")

    artifact_kinds = tuple(item.value for item in ArtifactKind)
    evidence_ingest = evidence_commands.add_parser(
        "ingest", help="ingest files and seal a create-only evidence manifest"
    )
    evidence_ingest.add_argument("store", type=Path)
    evidence_ingest.add_argument("output", type=Path)
    evidence_ingest.add_argument("files", type=Path, nargs="+")
    evidence_ingest.add_argument("--kind", choices=artifact_kinds, required=True)
    evidence_ingest.add_argument("--media-type", required=True)
    evidence_ingest.add_argument("--producer-id", default="shadowbane-lab.manual-ingest")
    evidence_ingest.add_argument("--producer-version", default="0.1.0")
    evidence_ingest.add_argument("--case-id")
    evidence_ingest.add_argument("--run-id")
    evidence_ingest.add_argument("--json", action="store_true")

    evidence_verify = evidence_commands.add_parser(
        "verify", help="verify every object referenced by an evidence manifest"
    )
    evidence_verify.add_argument("store", type=Path)
    evidence_verify.add_argument("manifest", type=Path)
    evidence_verify.add_argument("--output", type=Path)
    evidence_verify.add_argument("--json", action="store_true")

    evidence_bundle = evidence_commands.add_parser(
        "bundle", help="create a portable verified evidence bundle"
    )
    evidence_bundle.add_argument("store", type=Path)
    evidence_bundle.add_argument("manifest", type=Path)
    evidence_bundle.add_argument("output", type=Path)
    evidence_bundle.add_argument("--json", action="store_true")

    evidence_index = evidence_commands.add_parser(
        "rebuild-index", help="rebuild a disposable SQLite index from canonical manifests"
    )
    evidence_index.add_argument("manifest_directory", type=Path)
    evidence_index.add_argument("index", type=Path)
    evidence_index.add_argument("--json", action="store_true")

    evidence_query = evidence_commands.add_parser("query", help="query a rebuilt evidence index")
    evidence_query.add_argument("index", type=Path)
    evidence_query.add_argument("--kind", choices=artifact_kinds)
    evidence_query.add_argument("--case-id")
    evidence_query.add_argument("--run-id")
    evidence_query.add_argument("--limit", type=int, default=100)
    evidence_query.add_argument("--json", action="store_true")

    legacy = evidence_commands.add_parser(
        "import-legacy", help="non-destructively import existing evidence files"
    )
    legacy.add_argument("store", type=Path)
    legacy.add_argument("manifest_output", type=Path)
    legacy.add_argument("receipt_output", type=Path)
    legacy.add_argument("files", type=Path, nargs="+")
    legacy.add_argument("--kind", choices=artifact_kinds, required=True)
    legacy.add_argument("--media-type", required=True)
    legacy.add_argument("--importer-id", default="shadowbane-lab.legacy-import")
    legacy.add_argument("--importer-version", default="0.1.0")
    legacy.add_argument("--case-id")
    legacy.add_argument("--run-id")
    legacy.add_argument("--json", action="store_true")

    fingerprint = commands.add_parser(
        "fingerprint", help="capture, verify, and compare complete execution identity"
    )
    fingerprint_commands = fingerprint.add_subparsers(
        dest="fingerprint_command", required=True
    )
    fingerprint_capture = fingerprint_commands.add_parser(
        "capture", help="capture one complete fingerprint envelope"
    )
    fingerprint_capture.add_argument("output", type=Path)
    fingerprint_capture.add_argument("--client-directory", type=Path)
    fingerprint_capture.add_argument("--client-executable", type=Path)
    fingerprint_capture.add_argument("--runtime-executable", type=Path)
    fingerprint_capture.add_argument("--pid", type=int)
    fingerprint_capture.add_argument("--service-profile")
    fingerprint_capture.add_argument("--service-endpoint")
    fingerprint_capture.add_argument("--environment-id")
    fingerprint_capture.add_argument("--fixture", type=Path)
    fingerprint_capture.add_argument("--ruleset-id")
    fingerprint_capture.add_argument("--policy-id")
    fingerprint_capture.add_argument("--scenario-id")
    fingerprint_capture.add_argument("--experiment-id")
    fingerprint_capture.add_argument("--repository", type=Path)
    fingerprint_capture.add_argument(
        "--source-artifact",
        action="append",
        help="section-bound evidence using SECTION=sha256:<digest>",
    )
    fingerprint_capture.add_argument(
        "--identity-file",
        action="append",
        help="additional durable input using SECTION.LABEL=PATH",
    )
    fingerprint_capture.add_argument("--json", action="store_true")

    fingerprint_verify = fingerprint_commands.add_parser(
        "verify", help="strictly verify one fingerprint and its canonical IDs"
    )
    fingerprint_verify.add_argument("fingerprint", type=Path)
    fingerprint_verify.add_argument("--json", action="store_true")

    fingerprint_diff = fingerprint_commands.add_parser(
        "diff", help="compare two complete fingerprint envelopes"
    )
    fingerprint_diff.add_argument("reference", type=Path)
    fingerprint_diff.add_argument("candidate", type=Path)
    fingerprint_diff.add_argument("--output", type=Path)
    fingerprint_diff.add_argument("--json", action="store_true")

    diagnose = commands.add_parser(
        "diagnose",
        help="capture once, then analyze or compare sealed live diagnostics",
    )
    diagnose_commands = diagnose.add_subparsers(
        dest="diagnose_command",
        required=True,
    )
    diagnose_capture = diagnose_commands.add_parser(
        "capture",
        help="capture one bounded standard, full, or triggered session",
    )
    diagnose_capture.add_argument("output_directory", type=Path)
    diagnose_capture.add_argument("--pid", type=int, required=True)
    diagnose_capture.add_argument(
        "--profile",
        choices=("standard", "full", "triggered"),
        default="standard",
    )
    diagnose_capture.add_argument("--duration", type=float)
    diagnose_capture.add_argument("--interval", type=float)
    diagnose_capture.add_argument("--pre-trigger", type=float)
    diagnose_capture.add_argument("--post-trigger", type=float)
    diagnose_capture.add_argument("--client-executable", type=Path)
    diagnose_capture.add_argument("--client-directory", type=Path)
    diagnose_capture.add_argument("--reference-executable", type=Path)
    diagnose_capture.add_argument("--alignment-profile-directory", type=Path)
    diagnose_capture.add_argument("--repository", type=Path)
    diagnose_capture.add_argument(
        "--graphics-present",
        action="store_true",
        help="seal exact frame-present imports and optional identity-bound runtime status",
    )
    diagnose_capture.add_argument("--graphics-runtime-status", type=Path)
    diagnose_capture.add_argument(
        "--native-position",
        action="store_true",
        help="sample reviewed exact-process player LT, LG, and altitude",
    )
    diagnose_capture.add_argument(
        "--performance-telemetry",
        action="store_true",
        help="drain exact-process aggregate frame/read/upload telemetry",
    )
    diagnose_capture.add_argument(
        "--camera-state",
        action="store_true",
        help="require identity-bound renderer camera/view/projection telemetry",
    )
    diagnose_capture.add_argument("--log", type=Path, action="append", default=[])
    diagnose_capture.add_argument("--extension-events", type=Path)
    diagnose_capture.add_argument("--network-summary", type=Path)
    diagnose_capture.add_argument("--packet-capture", type=Path)
    diagnose_capture.add_argument("--etw-trace", type=Path)
    diagnose_capture.add_argument("--process-dump", type=Path)
    diagnose_capture.add_argument("--snapshot", type=Path, action="append", default=[])
    diagnose_capture.add_argument(
        "--channel-file",
        action="append",
        default=[],
        metavar="CHANNEL=KIND=MODE=MEDIA=PATH",
        help="attach or tail any additional named evidence channel",
    )
    diagnose_capture.add_argument(
        "--trigger",
        action="append",
        default=[],
        metavar="METRIC:OP:THRESHOLD[:COUNT[:delta]]",
    )
    diagnose_capture.add_argument("--manual-trigger-file", type=Path)
    diagnose_capture.add_argument(
        "--screenshot-region",
        metavar="LEFT,TOP,WIDTH,HEIGHT",
    )
    diagnose_capture.add_argument("--screenshot-interval", type=float, default=5.0)
    diagnose_capture.add_argument("--initial-log-mib", type=float, default=1.0)
    diagnose_capture.add_argument("--max-channel-mib", type=float, default=64.0)
    diagnose_capture.add_argument("--json", action="store_true")

    diagnose_mark = diagnose_commands.add_parser(
        "mark",
        help="submit a create-only observation marker to an active capture",
    )
    diagnose_mark.add_argument("output_directory", type=Path)
    diagnose_mark.add_argument("label")
    diagnose_mark.add_argument(
        "--phase",
        choices=(
            "cold-approach",
            "stationary",
            "warm-return",
            "complete",
        ),
    )
    diagnose_mark.add_argument("--finish", action="store_true")
    diagnose_mark.add_argument("--json", action="store_true")

    diagnose_stack_plan = diagnose_commands.add_parser(
        "stack-plan",
        help="verify sealed timeline evidence and plan an optional CPU-stack capture",
    )
    diagnose_stack_plan.add_argument("capture_directory", type=Path)
    diagnose_stack_plan.add_argument("--json", action="store_true")

    diagnose_analyze = diagnose_commands.add_parser(
        "analyze",
        help="reanalyze one sealed capture without recollecting",
    )
    diagnose_analyze.add_argument("store", type=Path)
    diagnose_analyze.add_argument("manifest", type=Path)
    diagnose_analyze.add_argument("--output", type=Path)
    diagnose_analyze.add_argument("--json", action="store_true")

    diagnose_compare = diagnose_commands.add_parser(
        "compare",
        help="compare raw metric samples from two sealed captures",
    )
    diagnose_compare.add_argument("baseline_store", type=Path)
    diagnose_compare.add_argument("baseline_manifest", type=Path)
    diagnose_compare.add_argument("candidate_store", type=Path)
    diagnose_compare.add_argument("candidate_manifest", type=Path)
    diagnose_compare.add_argument("--output", type=Path)
    diagnose_compare.add_argument("--json", action="store_true")

    case = commands.add_parser(
        "case", help="create, run, verify, and review research cases"
    )
    case_commands = case.add_subparsers(dest="case_command", required=True)
    case_create = case_commands.add_parser("create", help="create a draft research case")
    case_create.add_argument("output", type=Path)
    case_create.add_argument("--case-id", required=True)
    case_create.add_argument("--title", required=True)
    case_create.add_argument("--owner", required=True)
    case_create.add_argument("--target-profile", required=True)
    case_create.add_argument("--question", required=True)
    case_create.add_argument("--domain", action="append", required=True)
    case_create.add_argument(
        "--hypothesis",
        action="append",
        required=True,
        help="ID=STATEMENT; repeat for competing hypotheses",
    )
    case_create.add_argument("--experiment", action="append", default=[], help="ID@REVISION")
    case_create.add_argument("--fingerprint-section", action="append", default=[])
    case_create.add_argument("--capture-channel", action="append", default=[])
    case_create.add_argument("--json", action="store_true")
    case_validate = case_commands.add_parser(
        "validate", help="strictly validate a research case"
    )
    case_validate.add_argument("case", type=Path)
    case_validate.add_argument("--json", action="store_true")
    case_run = case_commands.add_parser(
        "run", help="run a case using dry-run or recorded evidence"
    )
    _add_experiment_run_arguments(case_run)
    case_verify = case_commands.add_parser(
        "verify", help="verify case references and artifacts"
    )
    case_verify.add_argument("case", type=Path)
    case_verify.add_argument("--experiment", type=Path, action="append")
    case_verify.add_argument("--manifest", type=Path, action="append")
    case_verify.add_argument("--store", type=Path)
    case_verify.add_argument("--json", action="store_true")
    case_review = case_commands.add_parser(
        "review", help="record a reviewed conclusion in a new revision"
    )
    case_review.add_argument("case", type=Path)
    case_review.add_argument("output", type=Path)
    case_review.add_argument("--reviewer", required=True)
    case_review.add_argument("--conclusion", required=True)
    case_review.add_argument("--limitation", action="append")
    case_review.add_argument("--invalidation-condition", action="append", required=True)
    case_review.add_argument("--close", action="store_true")
    case_review.add_argument("--json", action="store_true")

    experiment = commands.add_parser(
        "experiment", help="validate, expand, and run bounded experiments"
    )
    experiment_commands = experiment.add_subparsers(
        dest="experiment_command", required=True
    )
    experiment_validate = experiment_commands.add_parser(
        "validate", help="strictly validate an experiment definition"
    )
    experiment_validate.add_argument("experiment", type=Path)
    experiment_validate.add_argument("--json", action="store_true")
    experiment_expand = experiment_commands.add_parser(
        "expand", help="deterministically expand an experiment plan"
    )
    experiment_expand.add_argument("experiment", type=Path)
    experiment_expand.add_argument("--execution-nonce", required=True)
    experiment_expand.add_argument("--output", type=Path)
    experiment_expand.add_argument("--json", action="store_true")
    experiment_run = experiment_commands.add_parser(
        "run", help="run a bounded experiment for a research case"
    )
    _add_experiment_run_arguments(experiment_run)

    client = commands.add_parser("client", help="inspect and validate client integration")
    client_commands = client.add_subparsers(dest="client_command", required=True)

    character = commands.add_parser(
        "character",
        help="discover and capture read-only WonderBane character state",
    )
    character_commands = character.add_subparsers(dest="character_command", required=True)

    validate_layout = character_commands.add_parser(
        "validate-layout",
        help="strictly validate a process-memory character layout",
    )
    validate_layout.add_argument("layout", type=Path)
    validate_layout.add_argument("--json", action="store_true")

    inspect_process = character_commands.add_parser(
        "inspect-process",
        help="pin the running client PID, executable hash, pointer size, and modules",
    )
    _add_process_arguments(inspect_process)
    inspect_process.add_argument("--json", action="store_true")

    scan_text = character_commands.add_parser(
        "scan-text",
        help="scan readable pages for a character or item name without dumping memory",
    )
    scan_text.add_argument("text")
    scan_text.add_argument(
        "--encoding",
        action="append",
        dest="encodings",
        help="text encoding; may be repeated (defaults: cp1252, utf-8, utf-16le)",
    )
    _add_scan_arguments(scan_text)

    scan_pointer = character_commands.add_parser(
        "scan-pointer",
        help="find read-only pointer references to a candidate address",
    )
    scan_pointer.add_argument("address", type=_integer_argument)
    _add_scan_arguments(scan_pointer)

    snapshot = character_commands.add_parser(
        "snapshot",
        help="capture declared character fields from a hash-pinned layout",
    )
    snapshot.add_argument("layout", type=Path)
    snapshot.add_argument("--output", type=Path)
    snapshot.add_argument("--pid", type=int)
    snapshot.add_argument("--json", action="store_true")

    inspect = client_commands.add_parser(
        "inspect",
        help="read the current foreground Win32 client without sending input",
    )
    inspect.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    discover = client_commands.add_parser(
        "discover",
        help="find one visible client by its executable directory without changing focus",
    )
    discover.add_argument(
        "--process-directory",
        type=Path,
        required=True,
        help="directory containing the expected game process executable",
    )
    discover.add_argument(
        "--wait-seconds",
        type=float,
        default=0.0,
        help="maximum time to wait for exactly one matching visible window",
    )
    discover.add_argument(
        "--poll-seconds",
        type=float,
        default=0.5,
        help="delay between visible-window scans while waiting",
    )
    discover.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    validate = client_commands.add_parser(
        "validate-profile",
        help="strictly load a client calibration profile",
    )
    validate.add_argument("profile", type=Path)
    validate.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    inspect_hotkeys = client_commands.add_parser(
        "inspect-hotkeys",
        help="read native target-cycle bindings from ArcanePref.cfg without changing them",
    )
    inspect_hotkeys.add_argument("preferences", type=Path)
    inspect_hotkeys.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    inspect_hotbar = client_commands.add_parser(
        "inspect-hotbar",
        help="read F1-F12 power assignments from a character SCREEN_GAME config",
    )
    inspect_hotbar.add_argument("character_config", type=Path)
    inspect_hotbar.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    inspect_world_data = client_commands.add_parser(
        "inspect-world-data",
        help="inspect local world, terrain, mesh, and collision cache indexes",
    )
    inspect_world_data.add_argument(
        "cache_directory",
        type=Path,
        help="client cache directory containing TerrainAlpha.cache and related archives",
    )
    inspect_world_data.add_argument(
        "--world-def",
        type=Path,
        help="optional Config/WorldDef.cfg placement tree",
    )
    inspect_world_data.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_target = client_commands.add_parser(
        "observe-target",
        help="read target presence and health from the guarded foreground client",
    )
    observe_target.add_argument(
        "--client-profile",
        type=Path,
        required=True,
        help="validated client input/window profile",
    )
    observe_target.add_argument(
        "--observation-profile",
        type=Path,
        required=True,
        help="target-frame pixel calibration paired with the client profile",
    )
    observe_target.add_argument(
        "--wait-seconds",
        type=float,
        default=0.0,
        help="maximum time to wait for the calibrated client to become foreground",
    )
    observe_target.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    read_combat_log = client_commands.add_parser(
        "read-combat-log",
        help="read exact messages from a Shadowbane text HUD's native log file",
    )
    read_combat_log.add_argument("path", type=Path)
    read_combat_log.add_argument(
        "--limit",
        type=int,
        help="return only the newest N complete records",
    )
    read_combat_log.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    observe_native_target = client_commands.add_parser(
        "observe-native-target",
        help="read exact selected-target health from a calibrated Shadowbane build",
    )
    observe_native_target.add_argument(
        "--profile",
        type=Path,
        help="native health profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_target.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_target_position = client_commands.add_parser(
        "observe-native-target-position",
        help="read exact selected-target LT, LG, and altitude from a calibrated build",
    )
    observe_native_target_position.add_argument(
        "--profile",
        type=Path,
        help=("native target-position profile; defaults to the verified bundled WonderBane build"),
    )
    observe_native_target_position.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_target_identity = client_commands.add_parser(
        "observe-native-target-identity",
        help="read exact selected-target trainer and service-role flags",
    )
    observe_native_target_identity.add_argument(
        "--profile",
        type=Path,
        help=("native target-identity profile; defaults to the verified bundled WonderBane build"),
    )
    observe_native_target_identity.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_population = client_commands.add_parser(
        "observe-native-population",
        help="enumerate loaded characters without changing the selected target",
    )
    observe_native_population.add_argument(
        "--profile",
        type=Path,
        help=(
            "native character-population profile; defaults to the verified bundled WonderBane build"
        ),
    )
    observe_native_population.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_runegates = client_commands.add_parser(
        "observe-native-runegates",
        help="read the active server-supplied runegate registry from a calibrated build",
    )
    observe_native_runegates.add_argument(
        "--profile",
        type=Path,
        help="native runegate profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_runegates.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_world_map = client_commands.add_parser(
        "observe-native-world-map",
        help="read the live world-map bounds, visibility, zoom, and pan",
    )
    observe_native_world_map.add_argument(
        "--profile",
        type=Path,
        help="native world-map profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_world_map.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    test_world_map_click = client_commands.add_parser(
        "test-world-map-click",
        help="dispatch and natively verify one bounded world-map destination click",
    )
    test_world_map_click.add_argument("--client-profile", type=Path, required=True)
    test_world_map_click.add_argument(
        "--native-world-map-profile",
        type=Path,
        help="native world-map profile; defaults to the verified bundled WonderBane build",
    )
    test_world_map_click.add_argument(
        "--map-x-fraction",
        type=float,
        required=True,
        help="horizontal test point in the live map rectangle, from 0 through 1",
    )
    test_world_map_click.add_argument(
        "--map-y-fraction",
        type=float,
        required=True,
        help="vertical test point in the live map rectangle, from 0 through 1",
    )
    test_world_map_click.add_argument(
        "--wait-for-client-seconds",
        type=float,
        default=15.0,
        help="time allowed to foreground the exact client with its world map open",
    )
    test_world_map_click.add_argument(
        "--timeout-seconds",
        type=float,
        default=2.0,
        help="bounded wait for the matching native extension event",
    )
    test_world_map_click.add_argument(
        "--evidence-output",
        type=Path,
        help="write a new versioned action-lifecycle evidence artifact",
    )
    test_world_map_click.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    test_world_map_click.add_argument(
        "--json", action="store_true", help="emit machine-readable lifecycle evidence"
    )

    observe_native_snapshot = client_commands.add_parser(
        "observe-native-snapshot",
        help="read progression, training, and vitals from one exact client process",
    )
    observe_native_snapshot.add_argument(
        "--progression-profile",
        type=Path,
        help="native progression profile; defaults to the verified bundled build",
    )
    observe_native_snapshot.add_argument(
        "--training-profile",
        type=Path,
        help="native training profile; defaults to the verified bundled build",
    )
    observe_native_snapshot.add_argument(
        "--vitals-profile",
        type=Path,
        help="native vitals profile; defaults to the verified bundled build",
    )
    observe_native_snapshot.add_argument(
        "--process-id",
        type=int,
        help="specific sb.exe process id; defaults to the unique running process",
    )
    observe_native_snapshot.add_argument(
        "--json",
        action="store_true",
        help="emit the versioned exact-process snapshot as machine-readable JSON",
    )

    observe_native_player = client_commands.add_parser(
        "observe-native-player",
        help="read exact local-player health, mana, and stamina from a calibrated build",
    )
    observe_native_player.add_argument(
        "--profile",
        type=Path,
        help="native vitals profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_player.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_position = client_commands.add_parser(
        "observe-native-position",
        help="read exact local-player LT, LG, and altitude from a calibrated build",
    )
    observe_native_position.add_argument(
        "--profile",
        type=Path,
        help="native position profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_position.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_zone = client_commands.add_parser(
        "observe-native-zone",
        help="read the current zone already resolved by a calibrated Shadowbane build",
    )
    observe_native_zone.add_argument(
        "--profile",
        type=Path,
        help="native zone profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_zone.add_argument(
        "--cache-directory",
        type=Path,
        help="optionally join the active zone chain to CZone and TerrainAlpha caches",
    )
    observe_native_zone.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_group = client_commands.add_parser(
        "observe-native-group",
        help="read the current group roster, resources, positions, and follow state",
    )
    observe_native_group.add_argument(
        "--profile",
        type=Path,
        help="native group profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_group.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_progression = client_commands.add_parser(
        "observe-native-progression",
        help="read level, unspent points, attack ratings, and defense from a calibrated build",
    )
    observe_native_progression.add_argument(
        "--profile",
        type=Path,
        help="native progression profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_progression.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    observe_native_training = client_commands.add_parser(
        "observe-native-training",
        help="read exact local-player skill and power vectors from a calibrated build",
    )
    observe_native_training.add_argument(
        "--profile",
        type=Path,
        help="native training profile; defaults to the verified bundled WonderBane build",
    )
    observe_native_training.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    trace_native_vendor_dialog = client_commands.add_parser(
        "trace-native-vendor-dialog",
        help="capture decrypted ArcMerchantMessage traffic without patching client code",
    )
    trace_native_vendor_dialog.add_argument(
        "--profile",
        type=Path,
        help="native vendor-dialog profile; defaults to the verified WonderBane build",
    )
    trace_native_vendor_dialog.add_argument(
        "--process-id",
        type=int,
        help="specific sb.exe process id; defaults to the unique running process",
    )
    trace_native_vendor_dialog.add_argument("--output", type=Path, required=True)
    trace_native_vendor_dialog.add_argument("--label", required=True)
    trace_native_vendor_dialog.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="maximum time to wait for the first vendor message",
    )
    trace_native_vendor_dialog.add_argument(
        "--settle-seconds",
        type=float,
        default=2.0,
        help="stop after this quiet interval once vendor traffic begins",
    )
    trace_native_vendor_dialog.add_argument(
        "--json", action="store_true", help="emit a machine-readable session summary"
    )

    advise_irekei_proc = client_commands.add_parser(
        "advise-irekei-proc",
        help="compare the live character's exact ranks with the sourced proc-Assassin roadmap",
    )
    advise_irekei_proc.add_argument(
        "--progression-profile",
        type=Path,
        help="native scalar progression profile; defaults to the verified WonderBane build",
    )
    advise_irekei_proc.add_argument(
        "--training-profile",
        type=Path,
        help="native skill/power profile; defaults to the verified WonderBane build",
    )
    advise_irekei_proc.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )

    run_pve = client_commands.add_parser(
        "run-pve",
        help="run native-observation PvE against nearby mobiles",
    )
    run_pve.add_argument("--client-profile", type=Path, required=True)
    run_pve.add_argument(
        "--combat-source",
        choices=("state", "hud", "log"),
        help=(
            "combat evidence source; state uses exact health/action observations, HUD is "
            "the default unless --combat-log is supplied for legacy file logging"
        ),
    )
    run_pve.add_argument("--combat-log", type=Path)
    run_pve.add_argument(
        "--hotbar-config",
        type=Path,
        help="character SCREEN_GAME config; required by policies that activate hotbar powers",
    )
    run_pve.add_argument("--native-health-profile", type=Path)
    run_pve.add_argument("--native-message-hud-profile", type=Path)
    run_pve.add_argument("--native-vitals-profile", type=Path)
    run_pve.add_argument("--native-position-profile", type=Path)
    run_pve.add_argument("--native-target-position-profile", type=Path)
    run_pve.add_argument("--native-target-action-profile", type=Path)
    run_pve.add_argument("--native-target-identity-profile", type=Path)
    run_pve.add_argument("--native-character-population-profile", type=Path)
    run_pve.add_argument(
        "--navigation-cache-directory",
        type=Path,
        help=(
            "client cache directory used to seed the approach A* cost map from the "
            "active zone's height field"
        ),
    )
    run_pve.add_argument("--max-kills", type=int, default=1)
    run_pve.add_argument("--max-seconds", type=float, default=120.0)
    run_pve.add_argument("--max-encounter-seconds", type=float, default=120.0)
    run_pve.add_argument(
        "--continuous",
        action="store_true",
        help="run until explicitly stopped while remaining inside the starting camp",
    )
    run_pve.add_argument(
        "--camp-radius",
        type=float,
        default=120.0,
        help="continuous target-admission radius around the starting LT/LG",
    )
    run_pve.add_argument(
        "--retained-trace-steps",
        type=int,
        default=2_000,
        help="maximum continuous trace tail retained in memory",
    )
    run_pve.add_argument("--recovery-timeout-seconds", type=float, default=30.0)
    run_pve.add_argument("--recovery-health-fraction", type=float, default=0.75)
    run_pve.add_argument("--recovery-mana-fraction", type=float, default=0.15)
    run_pve.add_argument("--recovery-stamina-fraction", type=float, default=0.25)
    run_pve.add_argument("--wait-for-client-seconds", type=float, default=15.0)
    run_pve.add_argument("--poll-ms", type=int, default=100)
    run_pve.add_argument(
        "--evidence-output",
        type=Path,
        help="write final versioned evidence; continuous mode adds a JSONL journal",
    )
    run_pve.add_argument(
        "--policy",
        choices=("basic", "proc-assassin"),
        default="basic",
        help=(
            "control policy; proc-assassin accepts auto-targets and uses "
            "Shadow Touch to interrupt a native queued attack"
        ),
    )
    run_pve.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    run_pve.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    calibrate_pve = client_commands.add_parser(
        "calibrate-pve",
        help="compile one or more versioned live PvE traces into simulator evidence",
    )
    calibrate_pve.add_argument(
        "--evidence",
        type=Path,
        nargs="+",
        required=True,
        help="versioned PvE evidence artifacts produced by client run-pve",
    )
    calibrate_pve.add_argument("--output", type=Path, required=True)
    calibrate_pve.add_argument("--json", action="store_true", help="emit the compiled calibration")

    go = client_commands.add_parser(
        "go",
        help="travel to an LT/LG destination through bounded, feedback-checked minimap clicks",
    )
    go.add_argument("lt", type=float, nargs="?")
    go.add_argument("lg", type=float, nargs="?")
    go.add_argument(
        "--radius",
        type=float,
        help="arrival radius; bare go reuses the remembered radius when omitted",
    )
    go.add_argument(
        "--destination-state",
        type=Path,
        default=Path.home() / ".shadowbane-lab" / "last-travel-destination.json",
        help="local state file used to remember the last explicit destination",
    )
    go.add_argument("--client-profile", type=Path, required=True)
    go.add_argument("--native-position-profile", type=Path)
    go.add_argument("--native-vitals-profile", type=Path)
    go.add_argument(
        "--navigation-cache-directory",
        type=Path,
        help="client cache directory used for adaptive active-zone A* travel",
    )
    go.add_argument("--max-seconds", type=float, default=300.0)
    go.add_argument("--wait-for-client-seconds", type=float, default=30.0)
    go.add_argument("--poll-ms", type=int, default=200)
    go.add_argument("--click-interval-ms", type=int, default=2_000)
    go.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    go.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    listen_go = client_commands.add_parser(
        "listen-go",
        help="listen for foreground in-game /go, /zone, /pve, and /stop commands",
    )
    listen_go.add_argument(
        "--destination-state",
        type=Path,
        default=Path.home() / ".shadowbane-lab" / "last-travel-destination.json",
        help="local state file used to remember the last explicit destination",
    )
    listen_go.add_argument("--client-profile", type=Path, required=True)
    listen_go.add_argument("--native-position-profile", type=Path)
    listen_go.add_argument("--native-vitals-profile", type=Path)
    listen_go.add_argument("--native-runegate-profile", type=Path)
    listen_go.add_argument("--native-world-map-profile", type=Path)
    listen_go.add_argument(
        "--hotkey-config",
        type=Path,
        help="config containing BEGINHOTKEYS, used to close the world map",
    )
    listen_go.add_argument(
        "--world-def",
        type=Path,
        help="installed Config/WorldDef.cfg used to resolve named /go destinations",
    )
    listen_go.add_argument(
        "--named-destination-overrides",
        type=Path,
        help="emulator-confirmed named destinations layered over client WorldDef entries",
    )
    listen_go.add_argument(
        "--pve-client-profile",
        type=Path,
        help="live PvE input profile; enables the in-game /pve command",
    )
    listen_go.add_argument(
        "--pve-hotbar-config",
        type=Path,
        help="current character SCREEN_GAME config used to verify Shadow Touch",
    )
    listen_go.add_argument(
        "--pve-evidence-directory",
        type=Path,
        help="directory for one timestamped evidence artifact per /pve run",
    )
    listen_go.add_argument(
        "--navigation-cache-directory",
        "--pve-navigation-cache-directory",
        dest="navigation_cache_directory",
        type=Path,
        help="client cache directory used for adaptive /go and /pve A* routes",
    )
    listen_go.add_argument(
        "--learned-navigation-state",
        type=Path,
        help="durable exact obstacle cells learned from stalled /go and /pve movement",
    )
    listen_go.add_argument("--pve-max-kills", type=int, default=3)
    listen_go.add_argument("--pve-max-seconds", type=float, default=300.0)
    listen_go.add_argument("--pve-max-encounter-seconds", type=float, default=120.0)
    listen_go.add_argument(
        "--pve-continuous",
        action="store_true",
        help="make /pve run until stopped inside a camp anchored at startup",
    )
    listen_go.add_argument("--pve-camp-radius", type=float, default=120.0)
    listen_go.add_argument("--pve-retained-trace-steps", type=int, default=2_000)
    listen_go.add_argument("--pve-recovery-timeout-seconds", type=float, default=30.0)
    listen_go.add_argument("--pve-poll-ms", type=int, default=100)
    listen_go.add_argument("--max-seconds", type=float, default=300.0)
    listen_go.add_argument("--wait-for-client-seconds", type=float, default=30.0)
    listen_go.add_argument("--poll-ms", type=int, default=200)
    listen_go.add_argument("--click-interval-ms", type=int, default=2_000)
    listen_go.add_argument(
        "--manager-manifest",
        type=Path,
        help="manager manifest used to resolve the foreground client to its exact worker",
    )
    listen_go.add_argument(
        "--worker-state-directory",
        type=Path,
        help="node-local manager worker state containing permits and operation inboxes",
    )
    listen_go.add_argument(
        "--live",
        action="store_true",
        help="required in addition to a profile with live_input_enabled=true",
    )
    listen_go.add_argument("--json", action="store_true", help="emit JSON Lines events")

    manager = commands.add_parser(
        "manager",
        help="inspect local client instances without focusing them or sending input",
    )
    manager_commands = manager.add_subparsers(dest="manager_command", required=True)
    manager_inspect = manager_commands.add_parser(
        "inspect",
        help="emit a node-tagged inventory of matching visible clients",
    )
    manager_inspect.add_argument(
        "--node-id",
        required=True,
        help="stable identifier for this PC in manager evidence and client identities",
    )
    manager_inspect.add_argument(
        "--process-directory",
        type=Path,
        help="optional exact directory containing the expected game executable",
    )
    manager_inspect.add_argument(
        "--executable-name",
        dest="executable_names",
        action="append",
        metavar="NAME",
        help="allowed executable file name; repeatable and defaults to sb.exe",
    )
    manager_inspect.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    manager_preflight = manager_commands.add_parser(
        "preflight",
        help="validate a local lifecycle manifest and inventory its matching clients",
    )
    manager_preflight.add_argument(
        "manifest",
        type=Path,
        help="strict schema-v1 manager manifest JSON",
    )
    manager_preflight.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    manager_slots = manager_commands.add_parser(
        "configure-slots",
        help="expand and deterministically tile local manifest client slots",
    )
    manager_slots.add_argument("manifest", type=Path)
    manager_slots.add_argument("--count", type=int, required=True)
    manager_slots.add_argument("--display-width", type=int, default=1920)
    manager_slots.add_argument("--display-height", type=int, default=955)
    manager_slots.add_argument(
        "--apply",
        action="store_true",
        help="required because this atomically replaces the manifest after making a backup",
    )
    manager_slots.add_argument("--json", action="store_true")
    manager_build = manager_commands.add_parser(
        "configure-build",
        help="atomically retarget all slots to one reviewed client directory",
    )
    manager_build.add_argument("manifest", type=Path)
    manager_build.add_argument("game_directory")
    manager_build.add_argument("--executable-name", default="sb.exe")
    manager_build.add_argument(
        "--apply",
        action="store_true",
        help="required because this atomically replaces the manifest after making a backup",
    )
    manager_build.add_argument("--json", action="store_true")
    manager_runtimes = manager_commands.add_parser(
        "provision-runtimes",
        help="publish one verified guest-local client runtime per manager slot",
    )
    manager_runtimes.add_argument("manifest", type=Path)
    manager_runtimes.add_argument("frozen_directory", type=Path)
    manager_runtimes.add_argument("deployment_directory", type=Path)
    manager_runtimes.add_argument("patch_manifest", type=Path)
    manager_runtimes.add_argument("extension_artifact", type=Path)
    manager_runtimes.add_argument("--deployment-id", required=True)
    manager_runtimes.add_argument("--slot-count", type=int)
    manager_runtimes.add_argument("--executable-name", default="sb.exe")
    manager_runtimes.add_argument("--resolution-width", type=int, default=1920)
    manager_runtimes.add_argument("--resolution-height", type=int, default=955)
    manager_runtimes.add_argument(
        "--apply",
        action="store_true",
        help=(
            "required because this creates verified runtime trees and atomically "
            "replaces the manager manifest"
        ),
    )
    manager_runtimes.add_argument("--json", action="store_true")
    manager_app = manager_commands.add_parser(
        "app",
        help="run the authenticated localhost lifecycle dashboard",
    )
    manager_app.add_argument(
        "manifest",
        type=Path,
        help="strict schema-v1 manager manifest JSON",
    )
    manager_app.add_argument(
        "--port",
        type=int,
        default=0,
        help="loopback TCP port; defaults to an ephemeral available port",
    )
    manager_app.add_argument("--launch-timeout-seconds", type=float, default=30.0)
    manager_app.add_argument("--poll-ms", type=int, default=500)
    manager_app.add_argument(
        "--worker-state-directory",
        type=Path,
        help=("local worker heartbeat root; defaults beneath LOCALAPPDATA\\ShadowbaneLab\\workers"),
    )
    manager_app.add_argument(
        "--pid-file",
        type=Path,
        help="runtime-owned PID file written by the actual manager interpreter",
    )
    manager_app.add_argument(
        "--authorization-token-file",
        type=Path,
        help=(
            "local persistent dashboard token; defaults beside manager worker state"
        ),
    )
    manager_app.add_argument(
        "--no-browser",
        action="store_true",
        help="print the authenticated dashboard URL without opening a browser",
    )
    manager_app.add_argument(
        "--live",
        action="store_true",
        help="required because dashboard actions may launch, tile, or close clients",
    )
    manager_worker = manager_commands.add_parser(
        "worker",
        help="run one exact game-instance worker safety/runtime host",
    )
    manager_worker.add_argument(
        "manifest",
        type=Path,
        help="strict schema-v1 manager manifest JSON",
    )
    manager_worker.add_argument("--worker-state-directory", type=Path, required=True)
    manager_worker.add_argument("--client-id", required=True)
    manager_worker.add_argument("--instance-id", required=True)
    manager_worker.add_argument("--game-process-id", type=int, required=True)
    manager_worker.add_argument(
        "--game-process-started-at-100ns",
        type=int,
        required=True,
    )
    manager_worker.add_argument("--game-window-handle", type=int, required=True)
    manager_worker.add_argument("--heartbeat-ms", type=int, default=1_000)
    manager_worker.add_argument(
        "--destination-state",
        type=Path,
        default=Path(r"\\VBOXSVR\codexdiag\bounded-route-state.json"),
    )
    manager_worker.add_argument(
        "--client-profile",
        type=Path,
        default=Path(r"\\VBOXSVR\codexdiag\wonderbane-travel.local.json"),
    )
    manager_worker.add_argument("--native-position-profile", type=Path)
    manager_worker.add_argument("--native-vitals-profile", type=Path)
    manager_worker.add_argument(
        "--pve-client-profile",
        type=Path,
        default=Path(r"\\VBOXSVR\codexrepo\configs\wonderbane-pve.local.json"),
    )
    manager_worker.add_argument("--pve-hotbar-config", type=Path)
    manager_worker.add_argument(
        "--pve-evidence-directory",
        type=Path,
        default=Path(r"\\VBOXSVR\codexdiag"),
    )
    manager_worker.add_argument(
        "--navigation-cache-directory",
        type=Path,
        default=(Path.home() / "Downloads" / "WonderbaneClient" / "Wonderbane" / "cache"),
    )
    manager_worker.add_argument(
        "--learned-navigation-state",
        type=Path,
        default=Path(r"\\VBOXSVR\codexdiag\learned-navigation-state.json"),
    )
    manager_worker.add_argument("--pve-max-kills", type=int, default=3)
    manager_worker.add_argument("--pve-max-seconds", type=float, default=300.0)
    manager_worker.add_argument("--pve-max-encounter-seconds", type=float, default=120.0)
    manager_worker.add_argument("--pve-recovery-timeout-seconds", type=float, default=30.0)
    manager_worker.add_argument("--pve-poll-ms", type=int, default=100)
    manager_worker.add_argument("--pve-camp-radius", type=float, default=120.0)
    manager_worker.add_argument("--pve-retained-trace-steps", type=int, default=2_000)
    manager_worker.add_argument("--travel-max-seconds", type=float, default=300.0)
    manager_worker.add_argument("--travel-poll-ms", type=int, default=200)
    manager_worker.add_argument("--travel-click-interval-ms", type=int, default=2_000)
    manager_worker.add_argument(
        "--live",
        action="store_true",
        help="required because this worker is the live-input ownership boundary",
    )

    progression = commands.add_parser(
        "progression",
        help="import and inspect sourced character-progression data",
    )
    progression_commands = progression.add_subparsers(
        dest="progression_command",
        required=True,
    )
    import_calculator = progression_commands.add_parser(
        "import-wonderbane-calculator",
        help="snapshot and safely parse the public WonderBane calculator declarations",
    )
    calculator_source = import_calculator.add_mutually_exclusive_group(required=True)
    calculator_source.add_argument(
        "--snapshot",
        type=Path,
        help="existing WonderBane home-page HTML snapshot",
    )
    calculator_source.add_argument(
        "--download",
        action="store_true",
        help="download the bounded HTTPS home page without rendering or executing it",
    )
    import_calculator.add_argument(
        "--output",
        type=Path,
        required=True,
        help="directory for the timestamped HTML, manifest, and normalized catalog",
    )
    import_calculator.add_argument(
        "--retrieved-at",
        help="optional ISO-8601 retrieval timestamp; defaults to current UTC",
    )
    import_calculator.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable result metadata",
    )
    return parser
