"""Bounded contracts for repeatable live diagnostic capture."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import ceil, isfinite
from pathlib import Path
from typing import Mapping

from shadowbane_lab.evidence import ArtifactKind
from shadowbane_lab.integrity import validate_identifier


class DiagnosticError(RuntimeError):
    """Raised when a diagnostic run cannot be captured or trusted."""


class DiagnosticProfile(StrEnum):
    STANDARD = "standard"
    FULL = "full"
    TRIGGERED = "triggered"


class FileCaptureMode(StrEnum):
    TAIL = "tail"
    SNAPSHOT = "snapshot"


class TriggerOperator(StrEnum):
    GE = "ge"
    GT = "gt"
    LE = "le"
    LT = "lt"


@dataclass(frozen=True, slots=True)
class TriggerRule:
    metric: str
    operator: TriggerOperator
    threshold: float
    consecutive_samples: int = 1
    compare_to_baseline: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.metric, "trigger metric")
        if not isinstance(self.operator, TriggerOperator):
            raise ValueError("trigger operator is invalid")
        if (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, int | float)
            or not isfinite(self.threshold)
        ):
            raise ValueError("trigger threshold must be finite")
        if (
            isinstance(self.consecutive_samples, bool)
            or not isinstance(self.consecutive_samples, int)
            or not 1 <= self.consecutive_samples <= 1_000_000
        ):
            raise ValueError("trigger consecutive_samples must be in 1-1000000")

    def matches(
        self,
        metrics: Mapping[str, float],
        baseline: Mapping[str, float],
    ) -> bool:
        if self.metric not in metrics:
            return False
        actual = float(metrics[self.metric])
        if self.compare_to_baseline:
            if self.metric not in baseline:
                return False
            actual -= float(baseline[self.metric])
        if self.operator is TriggerOperator.GE:
            return actual >= self.threshold
        if self.operator is TriggerOperator.GT:
            return actual > self.threshold
        if self.operator is TriggerOperator.LE:
            return actual <= self.threshold
        return actual < self.threshold

    def as_dict(self) -> dict[str, object]:
        return {
            "metric": self.metric,
            "operator": self.operator.value,
            "threshold": float(self.threshold),
            "consecutive_samples": self.consecutive_samples,
            "compare_to_baseline": self.compare_to_baseline,
        }


@dataclass(frozen=True, slots=True)
class FileChannel:
    channel_id: str
    path: Path
    mode: FileCaptureMode
    artifact_kind: ArtifactKind
    media_type: str
    initial_tail_bytes: int = 1_048_576
    maximum_bytes: int = 67_108_864

    def __post_init__(self) -> None:
        validate_identifier(self.channel_id, "file channel ID")
        if not isinstance(self.path, Path):
            raise ValueError("file channel path must be Path")
        if not isinstance(self.mode, FileCaptureMode):
            raise ValueError("file channel mode is invalid")
        if not isinstance(self.artifact_kind, ArtifactKind):
            raise ValueError("file channel artifact kind is invalid")
        if (
            not isinstance(self.media_type, str)
            or not self.media_type
            or len(self.media_type) > 256
        ):
            raise ValueError("file channel media type must be bounded non-empty text")
        for value, name in (
            (self.initial_tail_bytes, "initial_tail_bytes"),
            (self.maximum_bytes, "maximum_bytes"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= 16 * 1024 * 1024 * 1024
            ):
                raise ValueError(f"{name} must be a bounded non-negative integer")
        if self.maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be positive")


@dataclass(frozen=True, slots=True)
class DiagnosticRequest:
    output_directory: Path
    process_id: int
    profile: DiagnosticProfile = DiagnosticProfile.STANDARD
    duration_seconds: float | None = None
    sample_interval_seconds: float | None = None
    pre_trigger_seconds: float | None = None
    post_trigger_seconds: float | None = None
    client_executable: Path | None = None
    client_directory: Path | None = None
    reference_executable: Path | None = None
    alignment_profile_directory: Path | None = None
    repository_directory: Path | None = None
    file_channels: tuple[FileChannel, ...] = ()
    trigger_rules: tuple[TriggerRule, ...] = ()
    manual_trigger_file: Path | None = None
    screenshot_region: tuple[int, int, int, int] | None = None
    screenshot_interval_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not isinstance(self.output_directory, Path):
            raise ValueError("output_directory must be Path")
        if (
            isinstance(self.process_id, bool)
            or not isinstance(self.process_id, int)
            or self.process_id <= 0
        ):
            raise ValueError("process_id must be positive")
        if not isinstance(self.profile, DiagnosticProfile):
            raise ValueError("profile must be DiagnosticProfile")
        for value, name, maximum in (
            (self.effective_duration_seconds, "duration_seconds", 86_400.0),
            (self.effective_sample_interval_seconds, "sample_interval_seconds", 60.0),
            (self.effective_pre_trigger_seconds, "pre_trigger_seconds", 3_600.0),
            (self.effective_post_trigger_seconds, "post_trigger_seconds", 3_600.0),
            (self.screenshot_interval_seconds, "screenshot_interval_seconds", 3_600.0),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not isfinite(value)
                or value < 0
                or value > maximum
            ):
                raise ValueError(f"{name} must be finite and in range")
        if self.effective_duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if self.effective_sample_interval_seconds <= 0:
            raise ValueError("sample_interval_seconds must be positive")
        if (
            ceil(
                self.effective_duration_seconds
                / self.effective_sample_interval_seconds
            )
            + 1
            > 1_000_000
        ):
            raise ValueError("diagnostic request exceeds one million process samples")
        if self.screenshot_interval_seconds <= 0:
            raise ValueError("screenshot_interval_seconds must be positive")
        channel_ids = tuple(item.channel_id for item in self.file_channels)
        if channel_ids != tuple(sorted(channel_ids)) or len(channel_ids) != len(set(channel_ids)):
            raise ValueError("file channels must use unique canonical channel IDs")
        if self.profile is DiagnosticProfile.TRIGGERED and not (
            self.trigger_rules or self.manual_trigger_file is not None
        ):
            raise ValueError("triggered profile requires a trigger rule or manual trigger file")
        if self.screenshot_region is not None:
            if (
                len(self.screenshot_region) != 4
                or any(
                    isinstance(item, bool) or not isinstance(item, int)
                    for item in self.screenshot_region
                )
                or self.screenshot_region[0] < 0
                or self.screenshot_region[1] < 0
                or self.screenshot_region[2] <= 0
                or self.screenshot_region[3] <= 0
            ):
                raise ValueError("screenshot_region must be left,top,width,height")

    @property
    def effective_duration_seconds(self) -> float:
        if self.duration_seconds is not None:
            return float(self.duration_seconds)
        return 1_800.0 if self.profile is DiagnosticProfile.TRIGGERED else 300.0

    @property
    def effective_sample_interval_seconds(self) -> float:
        if self.sample_interval_seconds is not None:
            return float(self.sample_interval_seconds)
        return 0.25 if self.profile is not DiagnosticProfile.STANDARD else 1.0

    @property
    def effective_pre_trigger_seconds(self) -> float:
        if self.pre_trigger_seconds is not None:
            return float(self.pre_trigger_seconds)
        return 60.0 if self.profile is DiagnosticProfile.TRIGGERED else 0.0

    @property
    def effective_post_trigger_seconds(self) -> float:
        if self.post_trigger_seconds is not None:
            return float(self.post_trigger_seconds)
        return 30.0 if self.profile is DiagnosticProfile.TRIGGERED else 0.0


__all__ = [
    "DiagnosticError",
    "DiagnosticProfile",
    "DiagnosticRequest",
    "FileCaptureMode",
    "FileChannel",
    "TriggerOperator",
    "TriggerRule",
]
