"""Command-line interface for the published vanilla diagnostics package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .capture import (
    CaptureConfig,
    CaptureError,
    assert_required_output_root,
    mark_active_capture,
    run_capture,
)
from .package import PackageVerificationError, verify_package
from .preflight import PreflightConfig, run_preflight


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shadowbane-vanilla-diagnostics")
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify-package")
    verify.add_argument("--package-root", type=Path, required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--package-root", type=Path, required=True)
    capture.add_argument("--output-root", type=Path, required=True)
    capture.add_argument("--pid", type=int, required=True)
    capture.add_argument("--client-executable", type=Path, required=True)
    capture.add_argument("--duration", type=float, default=600.0)
    capture.add_argument("--interval", type=float, default=0.125)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--package-root", type=Path, required=True)
    preflight.add_argument("--output-root", type=Path, required=True)
    preflight.add_argument("--pid", type=int, required=True)
    preflight.add_argument("--client-executable", type=Path, required=True)
    marker = commands.add_parser("mark")
    marker.add_argument("--package-root", type=Path, required=True)
    marker.add_argument("--output-root", type=Path, required=True)
    marker.add_argument("--label", required=True)
    marker.add_argument("--note", default="")
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    try:
        if options.command == "verify-package":
            package = verify_package(options.package_root)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "package_id": package["package_id"],
                        "package_version": package["package_version"],
                        "source_revision": package["source_revision"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        if options.command == "preflight":
            result = run_preflight(
                PreflightConfig(
                    package_root=options.package_root,
                    output_root=options.output_root,
                    process_id=options.pid,
                    client_executable=options.client_executable,
                )
            )
            print(
                json.dumps(
                    {"ok": True, "preflight_directory": str(result)}, sort_keys=True
                )
            )
            return 0
        if options.command == "capture":
            result = run_capture(
                CaptureConfig(
                    package_root=options.package_root,
                    output_root=options.output_root,
                    process_id=options.pid,
                    client_executable=options.client_executable,
                    duration_seconds=options.duration,
                    interval_seconds=options.interval,
                )
            )
            print(json.dumps({"ok": True, "capture_directory": str(result)}, sort_keys=True))
            return 0
        package = verify_package(options.package_root)
        assert_required_output_root(options.output_root, str(package["required_output_root"]))
        marker_path = mark_active_capture(options.output_root, options.label, options.note)
        print(json.dumps({"ok": True, "marker": str(marker_path)}, sort_keys=True))
        return 0
    except (CaptureError, PackageVerificationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
