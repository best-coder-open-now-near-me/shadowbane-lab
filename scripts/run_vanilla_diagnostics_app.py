"""Entry point for the self-contained Windows diagnostics application."""

from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path

from shadowbane_vanilla_diagnostics.app import (
    launch_portable_app,
    run_portable_self_test,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--self-test-result", type=Path)
    return parser


def _package_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve(strict=True)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve(strict=True).parent
    return Path(__file__).resolve(strict=True).parents[1]


def _fatal_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
        0,
        message,
        "Shadowbane Vanilla Diagnostics",
        0x10,
    )


def main(arguments: list[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    try:
        package_root = _package_root(options.package_root)
        if options.self_test:
            if options.self_test_result is None:
                raise ValueError("--self-test requires --self-test-result")
            return run_portable_self_test(package_root, options.self_test_result)
        launch_portable_app(package_root)
        return 0
    except Exception as exc:
        _fatal_error(f"The diagnostics app could not start.\n\n{type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
