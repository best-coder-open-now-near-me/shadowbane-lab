"""Offline PE comparison and calibrated-anchor intersection reporting."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from shadowbane_lab.client_alignment.diff import changed_ranges, section_status
from shadowbane_lab.client_alignment.model import (
    AnchorIntersection,
    CalibratedAnchor,
    ChangedRange,
    ClientAlignmentReport,
    PeImage,
)
from shadowbane_lab.client_alignment.pe import (
    PeInspectionError,
    inspect_pe_bytes,
    pe_header_layout_key,
    section_layout_key,
)
from shadowbane_lab.client_alignment.profiles import inventory_native_profiles

_ALIGNMENT_SCHEMA_VERSION = 1


class ClientAlignmentError(ValueError):
    """Raised when two client files cannot be compared safely."""


def _read(path: str | Path) -> tuple[Path, bytes]:
    resolved = Path(path)
    try:
        return resolved, resolved.read_bytes()
    except OSError as exc:
        raise ClientAlignmentError(f"could not read executable: {resolved}") from exc


def _intersections(
    ranges: Iterable[ChangedRange],
    anchors: Iterable[CalibratedAnchor],
) -> tuple[AnchorIntersection, ...]:
    results = [
        AnchorIntersection(anchor=anchor, changed_range=changed_range)
        for anchor in anchors
        for changed_range in ranges
        if changed_range.overlaps(anchor)
    ]
    results.sort(
        key=lambda result: (
            result.anchor.rva_start,
            result.anchor.profile_id.casefold(),
            result.changed_range.file_offset_start,
        )
    )
    return tuple(results)


def _recommendation(
    reference: PeImage,
    candidate: PeImage,
    *,
    header_layout_equal: bool,
    section_layouts_equal: bool,
    intersections: tuple[AnchorIntersection, ...],
    applicable_profile_count: int,
    calibrated_anchor_count: int,
) -> str:
    if reference.sha256 == candidate.sha256:
        return "exact_build"
    if reference.machine != candidate.machine or reference.pointer_size != candidate.pointer_size:
        return "incompatible_architecture"
    if not section_layouts_equal:
        return "structural_review_required"
    if applicable_profile_count == 0:
        return "no_applicable_profiles"
    if calibrated_anchor_count == 0:
        return "no_calibrated_anchors"
    if intersections:
        return "calibrated_anchor_review_required"
    if not header_layout_equal:
        return "pe_header_review_required"
    return "candidate_for_reviewed_compatibility"


def _proposal(
    reference: PeImage,
    candidate: PeImage,
    ranges: tuple[ChangedRange, ...],
    unchanged_sections: tuple[str, ...],
    changed_sections: tuple[str, ...],
    *,
    applicable_profile_count: int,
    calibrated_anchor_count: int,
) -> dict[str, object]:
    rva_ranges = [
        changed_range
        for changed_range in ranges
        if changed_range.rva_start is not None and changed_range.rva_end_exclusive is not None
    ]
    return {
        "baseline_executable_sha256": reference.sha256,
        "candidate_executable_sha256": candidate.sha256,
        "reference_length": reference.length,
        "candidate_length": candidate.length,
        "pe_header_layout_equal": True,
        "section_layouts_equal": True,
        "unchanged_sections": list(unchanged_sections),
        "changed_sections": list(changed_sections),
        "changed_byte_count": sum(item.changed_byte_count for item in ranges),
        "changed_range_count": len(ranges),
        "changed_rva_start": (
            min(item.rva_start for item in rva_ranges) if rva_ranges else None
        ),
        "changed_rva_end_exclusive": (
            max(item.rva_end_exclusive for item in rva_ranges) if rva_ranges else None
        ),
        "calibrated_rva_references_in_changed_range": 0,
        "applicable_profile_count": applicable_profile_count,
        "calibrated_anchor_count": calibrated_anchor_count,
        "review_required": True,
    }


def compare_client_builds(
    reference_path: str | Path,
    candidate_path: str | Path,
    *,
    profile_directory: str | Path | None = None,
) -> ClientAlignmentReport:
    """Compare two executable files without modifying or launching either file."""

    reference_file, reference_data = _read(reference_path)
    candidate_file, candidate_data = _read(candidate_path)
    try:
        reference = inspect_pe_bytes(reference_data, path=str(reference_file))
        candidate = inspect_pe_bytes(candidate_data, path=str(candidate_file))
    except PeInspectionError as exc:
        raise ClientAlignmentError(str(exc)) from exc

    header_layout_equal = pe_header_layout_key(reference) == pe_header_layout_key(candidate)
    section_layouts_equal = section_layout_key(reference) == section_layout_key(candidate)
    ranges = changed_ranges(reference_data, candidate_data, reference, candidate)
    unchanged_sections, changed_sections = section_status(reference, candidate)
    inventory = inventory_native_profiles(reference.sha256, directory=profile_directory)
    intersections = _intersections(ranges, inventory.anchors)
    recommendation = _recommendation(
        reference,
        candidate,
        header_layout_equal=header_layout_equal,
        section_layouts_equal=section_layouts_equal,
        intersections=intersections,
        applicable_profile_count=inventory.applicable_profile_count,
        calibrated_anchor_count=len(inventory.anchors),
    )
    proposal = None
    if recommendation == "candidate_for_reviewed_compatibility":
        proposal = _proposal(
            reference,
            candidate,
            ranges,
            unchanged_sections,
            changed_sections,
            applicable_profile_count=inventory.applicable_profile_count,
            calibrated_anchor_count=len(inventory.anchors),
        )

    return ClientAlignmentReport(
        schema_version=_ALIGNMENT_SCHEMA_VERSION,
        reference=reference,
        candidate=candidate,
        exact_file_match=reference.sha256 == candidate.sha256,
        pe_header_layout_equal=header_layout_equal,
        section_layouts_equal=section_layouts_equal,
        unchanged_sections=unchanged_sections,
        changed_sections=changed_sections,
        changed_byte_count=sum(item.changed_byte_count for item in ranges),
        changed_ranges=ranges,
        profile_inventory=inventory,
        anchor_intersections=intersections,
        recommendation=recommendation,
        proposed_compatibility_evidence=proposal,
    )


__all__ = ["ClientAlignmentError", "compare_client_builds"]
