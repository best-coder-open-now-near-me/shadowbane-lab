"""Reviewed policy for files the launched client is allowed to rewrite."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from shadowbane_lab.integrity import validate_relative_path

_RUNTIME_MUTABLE_EXACT_PATHS = frozenset(
    {
        "config/arcanepref.cfg",
        "doublefusion/cache/cache.dat",
        "doublefusion/dftm.dat",
        "doublefusion/dfts.dat",
        "doublefusion/engine.log",
        "doublefusion/user.var",
        "logs/debug.txt",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeDriftPolicyAssessment:
    """Unreviewed paths grouped by the kind of package drift observed."""

    unexpected_added: tuple[str, ...]
    unexpected_missing: tuple[str, ...]
    unexpected_changed: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return not (
            self.unexpected_added
            or self.unexpected_missing
            or self.unexpected_changed
        )

    @property
    def unexpected_paths(self) -> tuple[str, ...]:
        return self.unexpected_added + self.unexpected_missing + self.unexpected_changed

    def labeled_paths(self) -> tuple[str, ...]:
        return (
            tuple(f"added:{path}" for path in self.unexpected_added)
            + tuple(f"missing:{path}" for path in self.unexpected_missing)
            + tuple(f"changed:{path}" for path in self.unexpected_changed)
        )


def is_reviewed_runtime_mutable_path(relative_path: str) -> bool:
    """Return whether one canonical path is intentionally client-written."""

    normalized = validate_relative_path(relative_path).casefold()
    if normalized in _RUNTIME_MUTABLE_EXACT_PATHS:
        return True
    return (
        normalized.startswith("config/screen_game_")
        and normalized.endswith("_wonderbane.cfg")
        and normalized.count("/") == 1
    )


def assess_runtime_drift_paths(
    *,
    added: Iterable[str] = (),
    missing: Iterable[str] = (),
    changed: Iterable[str] = (),
) -> RuntimeDriftPolicyAssessment:
    """Apply the reviewed runtime-mutation policy to an inventory delta."""

    return RuntimeDriftPolicyAssessment(
        unexpected_added=_unexpected(added),
        unexpected_missing=_unexpected(missing),
        unexpected_changed=_unexpected(changed),
    )


def _unexpected(paths: Iterable[str]) -> tuple[str, ...]:
    canonical = tuple(validate_relative_path(path) for path in paths)
    if len({path.casefold() for path in canonical}) != len(canonical):
        raise ValueError("runtime drift paths must be case-insensitively unique")
    return tuple(
        path
        for path in sorted(canonical, key=str.casefold)
        if not is_reviewed_runtime_mutable_path(path)
    )


__all__ = [
    "RuntimeDriftPolicyAssessment",
    "assess_runtime_drift_paths",
    "is_reviewed_runtime_mutable_path",
]
