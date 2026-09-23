"""Deterministic, evidence-aware MAP-Elites archive primitives.

The archive is deliberately agnostic about Shadowbane mechanics. A caller compiles and evaluates
candidates, then supplies only a quality value, behavior descriptors, and an admission grade.
Candidate-grade mechanics cannot enter an archive configured to require strict evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite, prod
from typing import Generic, TypeVar

from shadowbane_lab.sim import DeterministicRandom

_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")
T = TypeVar("T")


class MapElitesError(ValueError):
    """Raised when an archive or search contract is malformed."""


class ArchiveAdmission(StrEnum):
    """Evidence grade attached to one evaluated candidate."""

    CANDIDATE = "candidate"
    STRICT = "strict"


_ADMISSION_RANK = {
    ArchiveAdmission.CANDIDATE: 0,
    ArchiveAdmission.STRICT: 1,
}


class MapElitesInsertStatus(StrEnum):
    ADDED = "added"
    REPLACED = "replaced"
    REJECTED_ADMISSION = "rejected_admission"
    REJECTED_NOT_BETTER = "rejected_not_better"


@dataclass(frozen=True, slots=True)
class DescriptorAxis:
    """One numeric behavior descriptor split by strictly increasing boundaries."""

    name: str
    boundaries: tuple[float, ...]

    def __post_init__(self) -> None:
        _identifier(self.name, "descriptor axis name")
        normalized = tuple(_finite(value, f"{self.name} boundary") for value in self.boundaries)
        if any(right <= left for left, right in zip(normalized, normalized[1:], strict=False)):
            raise MapElitesError("descriptor boundaries must be strictly increasing")
        object.__setattr__(self, "boundaries", normalized)

    @property
    def bin_count(self) -> int:
        return len(self.boundaries) + 1

    def locate(self, value: float) -> int:
        return bisect_right(self.boundaries, _finite(value, self.name))

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "boundaries": list(self.boundaries),
            "bin_count": self.bin_count,
        }


@dataclass(frozen=True, slots=True)
class MapElitesEvaluation:
    """Evaluation result suitable for deterministic archive comparison."""

    candidate_digest: str
    quality: float
    admission: ArchiveAdmission
    features: tuple[tuple[str, float], ...]
    metrics: tuple[tuple[str, float], ...] = ()
    evidence_digest: str | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _digest(self.candidate_digest, "candidate_digest")
        object.__setattr__(self, "quality", _finite(self.quality, "quality"))
        if not isinstance(self.admission, ArchiveAdmission):
            raise MapElitesError("admission must be an ArchiveAdmission")
        _numeric_pairs(self.features, "features")
        _numeric_pairs(self.metrics, "metrics")
        if self.evidence_digest is not None:
            _digest(self.evidence_digest, "evidence_digest")
        _unique_text(self.notes, "notes")

    def feature(self, name: str) -> float:
        try:
            return dict(self.features)[name]
        except KeyError as exc:
            raise MapElitesError(f"evaluation is missing descriptor feature {name}") from exc

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_digest": self.candidate_digest,
            "quality": self.quality,
            "admission": self.admission.value,
            "features": dict(sorted(self.features)),
            "metrics": dict(sorted(self.metrics)),
            "evidence_digest": self.evidence_digest,
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class MapElitesCell(Generic[T]):
    coordinates: tuple[int, ...]
    candidate: T
    evaluation: MapElitesEvaluation

    def as_dict(
        self,
        candidate_encoder: Callable[[T], object] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "coordinates": list(self.coordinates),
            "evaluation": self.evaluation.as_dict(),
        }
        if candidate_encoder is not None:
            payload["candidate"] = candidate_encoder(self.candidate)
        return payload


class MapElitesArchive(Generic[T]):
    """Sparse quality-diversity archive with deterministic replacement semantics."""

    def __init__(
        self,
        axes: tuple[DescriptorAxis, ...],
        *,
        required_admission: ArchiveAdmission = ArchiveAdmission.CANDIDATE,
    ) -> None:
        if not axes or any(not isinstance(axis, DescriptorAxis) for axis in axes):
            raise MapElitesError("axes must contain at least one DescriptorAxis")
        names = tuple(axis.name for axis in axes)
        if len(names) != len(set(names)):
            raise MapElitesError("descriptor axis names must be unique")
        if not isinstance(required_admission, ArchiveAdmission):
            raise MapElitesError("required_admission must be an ArchiveAdmission")
        self._axes = axes
        self._required_admission = required_admission
        self._cells: dict[tuple[int, ...], MapElitesCell[T]] = {}

    @property
    def axes(self) -> tuple[DescriptorAxis, ...]:
        return self._axes

    @property
    def required_admission(self) -> ArchiveAdmission:
        return self._required_admission

    @property
    def cell_count(self) -> int:
        return len(self._cells)

    @property
    def capacity(self) -> int:
        return prod(axis.bin_count for axis in self._axes)

    @property
    def coverage_fraction(self) -> float:
        return self.cell_count / self.capacity

    @property
    def cells(self) -> tuple[MapElitesCell[T], ...]:
        return tuple(self._cells[key] for key in sorted(self._cells))

    @property
    def best(self) -> MapElitesCell[T] | None:
        if not self._cells:
            return None
        return min(
            self._cells.values(),
            key=lambda cell: (
                -cell.evaluation.quality,
                -_ADMISSION_RANK[cell.evaluation.admission],
                cell.evaluation.candidate_digest,
                cell.coordinates,
            ),
        )

    def coordinates_for(self, evaluation: MapElitesEvaluation) -> tuple[int, ...]:
        if not isinstance(evaluation, MapElitesEvaluation):
            raise MapElitesError("evaluation must be a MapElitesEvaluation")
        expected = {axis.name for axis in self._axes}
        supplied = {key for key, _ in evaluation.features}
        if supplied != expected:
            missing = expected - supplied
            extra = supplied - expected
            details: list[str] = []
            if missing:
                details.append("missing: " + ", ".join(sorted(missing)))
            if extra:
                details.append("extra: " + ", ".join(sorted(extra)))
            raise MapElitesError(
                "evaluation descriptor features do not match archive axes ("
                + "; ".join(details)
                + ")"
            )
        return tuple(axis.locate(evaluation.feature(axis.name)) for axis in self._axes)

    def insert(
        self,
        candidate: T,
        evaluation: MapElitesEvaluation,
        *,
        candidate_digest: str,
    ) -> MapElitesInsertStatus:
        expected_digest = _digest(candidate_digest, "candidate_digest")
        if evaluation.candidate_digest != expected_digest:
            raise MapElitesError("evaluation candidate digest does not match the candidate")
        if _ADMISSION_RANK[evaluation.admission] < _ADMISSION_RANK[self._required_admission]:
            return MapElitesInsertStatus.REJECTED_ADMISSION
        coordinates = self.coordinates_for(evaluation)
        current = self._cells.get(coordinates)
        proposed = MapElitesCell(coordinates, candidate, evaluation)
        if current is None:
            self._cells[coordinates] = proposed
            return MapElitesInsertStatus.ADDED
        if not self._better(proposed.evaluation, current.evaluation):
            return MapElitesInsertStatus.REJECTED_NOT_BETTER
        self._cells[coordinates] = proposed
        return MapElitesInsertStatus.REPLACED

    def as_dict(
        self,
        candidate_encoder: Callable[[T], object] | None = None,
    ) -> dict[str, object]:
        return {
            "required_admission": self.required_admission.value,
            "axes": [axis.as_dict() for axis in self.axes],
            "capacity": self.capacity,
            "cell_count": self.cell_count,
            "coverage_fraction": self.coverage_fraction,
            "best_candidate_digest": (
                None if self.best is None else self.best.evaluation.candidate_digest
            ),
            "cells": [cell.as_dict(candidate_encoder) for cell in self.cells],
            "archive_digest": self.archive_digest,
        }

    @property
    def archive_digest(self) -> str:
        return _canonical_digest(
            {
                "required_admission": self.required_admission.value,
                "axes": [axis.as_dict() for axis in self.axes],
                "cells": [
                    {
                        "coordinates": list(cell.coordinates),
                        "evaluation": cell.evaluation.as_dict(),
                    }
                    for cell in self.cells
                ],
            }
        )

    @staticmethod
    def _better(
        proposed: MapElitesEvaluation,
        current: MapElitesEvaluation,
    ) -> bool:
        if proposed.quality != current.quality:
            return proposed.quality > current.quality
        proposed_admission = _ADMISSION_RANK[proposed.admission]
        current_admission = _ADMISSION_RANK[current.admission]
        if proposed_admission != current_admission:
            return proposed_admission > current_admission
        if proposed.candidate_digest != current.candidate_digest:
            return proposed.candidate_digest < current.candidate_digest
        proposed_evidence = proposed.evidence_digest or "f" * 64
        current_evidence = current.evidence_digest or "f" * 64
        return proposed_evidence < current_evidence


@dataclass(frozen=True, slots=True)
class MapElitesRun(Generic[T]):
    archive: MapElitesArchive[T]
    seed: int
    iterations: int
    initial_candidate_count: int
    evaluated_candidate_count: int
    invalid_candidate_count: int
    duplicate_candidate_count: int
    insertion_counts: tuple[tuple[MapElitesInsertStatus, int], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.archive, MapElitesArchive):
            raise MapElitesError("archive must be a MapElitesArchive")
        for value, field_name in (
            (self.seed, "seed"),
            (self.iterations, "iterations"),
            (self.initial_candidate_count, "initial_candidate_count"),
            (self.evaluated_candidate_count, "evaluated_candidate_count"),
            (self.invalid_candidate_count, "invalid_candidate_count"),
            (self.duplicate_candidate_count, "duplicate_candidate_count"),
        ):
            _non_negative_integer(value, field_name)
        statuses = tuple(status for status, _ in self.insertion_counts)
        if len(statuses) != len(set(statuses)):
            raise MapElitesError("insertion_counts must not repeat statuses")
        for status, count in self.insertion_counts:
            if not isinstance(status, MapElitesInsertStatus):
                raise MapElitesError("insertion_counts keys must be insert statuses")
            _non_negative_integer(count, f"insertion count {status.value}")

    def as_dict(
        self,
        candidate_encoder: Callable[[T], object] | None = None,
    ) -> dict[str, object]:
        return {
            "seed": self.seed,
            "iterations": self.iterations,
            "initial_candidate_count": self.initial_candidate_count,
            "evaluated_candidate_count": self.evaluated_candidate_count,
            "invalid_candidate_count": self.invalid_candidate_count,
            "duplicate_candidate_count": self.duplicate_candidate_count,
            "insertion_counts": {
                status.value: count for status, count in self.insertion_counts
            },
            "archive": self.archive.as_dict(candidate_encoder),
        }


def run_map_elites(
    initial_candidates: tuple[T, ...],
    *,
    archive: MapElitesArchive[T],
    iterations: int,
    seed: int,
    candidate_digest: Callable[[T], str],
    evaluate: Callable[[T], MapElitesEvaluation | None],
    mutate: Callable[[T, DeterministicRandom], T | None],
) -> MapElitesRun[T]:
    """Run a deterministic archive search over caller-owned candidate mechanics."""

    if not initial_candidates:
        raise MapElitesError("initial_candidates must not be empty")
    if not isinstance(archive, MapElitesArchive):
        raise MapElitesError("archive must be a MapElitesArchive")
    _non_negative_integer(iterations, "iterations")
    _non_negative_integer(seed, "seed")
    for callback, field_name in (
        (candidate_digest, "candidate_digest"),
        (evaluate, "evaluate"),
        (mutate, "mutate"),
    ):
        if not callable(callback):
            raise MapElitesError(f"{field_name} must be callable")

    initial_by_digest: dict[str, T] = {}
    for candidate in initial_candidates:
        digest = _digest(candidate_digest(candidate), "candidate digest")
        if digest in initial_by_digest:
            raise MapElitesError("initial candidate digests must be unique")
        initial_by_digest[digest] = candidate

    insertion_counts = {status: 0 for status in MapElitesInsertStatus}
    evaluated_count = 0
    invalid_count = 0
    duplicate_count = 0
    seen: set[str] = set()

    def consider(candidate: T) -> None:
        nonlocal evaluated_count, invalid_count, duplicate_count
        digest = _digest(candidate_digest(candidate), "candidate digest")
        if digest in seen:
            duplicate_count += 1
            return
        seen.add(digest)
        evaluation = evaluate(candidate)
        if evaluation is None:
            invalid_count += 1
            return
        evaluated_count += 1
        result = archive.insert(candidate, evaluation, candidate_digest=digest)
        insertion_counts[result] += 1

    for digest in sorted(initial_by_digest):
        consider(initial_by_digest[digest])

    random = DeterministicRandom(seed)
    initial_pool = tuple(initial_by_digest[digest] for digest in sorted(initial_by_digest))
    for _ in range(iterations):
        archive_pool = tuple(cell.candidate for cell in archive.cells)
        pool = archive_pool or initial_pool
        parent = pool[random.randbelow(len(pool))]
        child = mutate(parent, random)
        if child is None:
            invalid_count += 1
            continue
        consider(child)

    return MapElitesRun(
        archive=archive,
        seed=seed,
        iterations=iterations,
        initial_candidate_count=len(initial_candidates),
        evaluated_candidate_count=evaluated_count,
        invalid_candidate_count=invalid_count,
        duplicate_candidate_count=duplicate_count,
        insertion_counts=tuple(
            (status, insertion_counts[status]) for status in MapElitesInsertStatus
        ),
    )


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MapElitesError(f"{field_name} must be a non-empty string")
    return value


def _digest(value: object, field_name: str) -> str:
    text = _identifier(value, field_name)
    if _DIGEST_PATTERN.fullmatch(text) is None:
        raise MapElitesError(f"{field_name} must be a lowercase SHA-256 digest")
    return text


def _finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise MapElitesError(f"{field_name} must be a finite number")
    return float(value)


def _non_negative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MapElitesError(f"{field_name} must be a non-negative integer")
    return value


def _numeric_pairs(values: tuple[tuple[str, float], ...], field_name: str) -> None:
    keys = tuple(key for key, _ in values)
    if len(keys) != len(set(keys)):
        raise MapElitesError(f"{field_name} keys must not contain duplicates")
    for key, value in values:
        _identifier(key, f"{field_name} key")
        _finite(value, f"{field_name}.{key}")


def _unique_text(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise MapElitesError(f"{field_name} must not contain duplicates")
    for value in values:
        _identifier(value, field_name)


__all__ = [
    "ArchiveAdmission",
    "DescriptorAxis",
    "MapElitesArchive",
    "MapElitesCell",
    "MapElitesError",
    "MapElitesEvaluation",
    "MapElitesInsertStatus",
    "MapElitesRun",
    "run_map_elites",
]
