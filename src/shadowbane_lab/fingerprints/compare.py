"""Deterministic complete fingerprint comparison."""

from __future__ import annotations

from .model import (
    FingerprintDiff,
    FingerprintEnvelope,
    ImpactState,
    SectionDifference,
)


def compare_fingerprints(
    reference: FingerprintEnvelope,
    candidate: FingerprintEnvelope,
) -> FingerprintDiff:
    differences: list[SectionDifference] = []
    for left, right in zip(reference.sections, candidate.sections, strict=True):
        left_values = dict(left.durable)
        right_values = dict(right.durable)
        changed = tuple(
            sorted(
                key
                for key in left_values.keys() | right_values.keys()
                if left_values.get(key) != right_values.get(key)
            )
        )
        if left.applicability != right.applicability:
            state = ImpactState.INVALIDATED
            changed = tuple(sorted({*changed, "applicability"}))
        elif left.source_artifact_ids != right.source_artifact_ids:
            state = ImpactState.REVIEW_REQUIRED
            changed = tuple(sorted({*changed, "source_artifact_ids"}))
        elif changed:
            state = ImpactState.REVIEW_REQUIRED
        else:
            state = ImpactState.UNAFFECTED
        differences.append(
            SectionDifference(
                section=left.name,
                state=state,
                changed_keys=changed,
                reference_applicability=left.applicability,
                candidate_applicability=right.applicability,
            )
        )
    return FingerprintDiff(
        reference_fingerprint_id=reference.fingerprint_id or "",
        candidate_fingerprint_id=candidate.fingerprint_id or "",
        differences=tuple(differences),
    )


__all__ = ["compare_fingerprints"]
