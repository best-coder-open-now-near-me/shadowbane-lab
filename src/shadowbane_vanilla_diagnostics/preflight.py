"""Guest-side preflight that proves the exact vanilla capture boundary without sampling."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .capture import (
    CaptureError,
    _assert_exact_identity,
    _write_json_create_new,
    assert_required_output_root,
    utc_timestamp,
)
from .package import verify_package
from .residue import build_vanilla_preflight
from .windows import WindowsModuleProbe, WindowsProcessProbe


@dataclass(frozen=True, slots=True)
class PreflightConfig:
    package_root: Path
    output_root: Path
    process_id: int
    client_executable: Path
    runtime_status_directory: Path | None = None

    def __post_init__(self) -> None:
        if isinstance(self.process_id, bool) or self.process_id <= 0:
            raise ValueError("process_id must be positive")


def run_preflight(config: PreflightConfig) -> Path:
    """Verify package, exact process, reviewed executable, modules, and residue only."""

    package = verify_package(config.package_root)
    assert_required_output_root(
        config.output_root,
        str(package["required_output_root"]),
        package_root=config.package_root,
    )
    config.output_root.mkdir(parents=True, exist_ok=True)
    process_probe = WindowsProcessProbe()
    first = process_probe.sample(config.process_id)
    modules = WindowsModuleProbe().list_modules(config.process_id)
    second = process_probe.sample(config.process_id)
    _assert_exact_identity(first.identity, second.identity)
    runtime_status_directory = config.runtime_status_directory
    if runtime_status_directory is None:
        local_app_data = os.environ.get("LOCALAPPDATA")
        runtime_status_directory = (
            Path(local_app_data) / "ShadowbaneLab" / "client-extension"
            if local_app_data
            else None
        )
    report = build_vanilla_preflight(
        requested_executable=config.client_executable,
        identity=second.identity,
        allowed_executable_sha256=package["allowed_executable_sha256"],
        modules=modules,
        runtime_status_directory=runtime_status_directory,
    )
    report.update(
        {
            "captured_at_utc": utc_timestamp(),
            "package_id": package["package_id"],
            "package_version": package["package_version"],
            "package_source_revision": package["source_revision"],
            "capture_started": False,
        }
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"shadowbane-vanilla-preflight-{timestamp}-{config.process_id}-{uuid.uuid4().hex[:8]}"
    output = config.output_root / run_id
    output.mkdir()
    _write_json_create_new(output / "preflight.json", report)
    _write_json_create_new(
        output / "preflight-complete.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "accepted": report["accepted"],
            "capture_started": False,
            "completed_at_utc": utc_timestamp(),
            "failures": report["failures"],
        },
    )
    if not report["accepted"]:
        raise CaptureError(
            "vanilla preflight rejected the target: " + "; ".join(report["failures"])
        )
    return output


__all__ = ["PreflightConfig", "run_preflight"]
