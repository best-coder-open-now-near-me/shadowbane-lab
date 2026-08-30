"""Typed records for offline WonderBane client-build alignment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PeSection:
    """One Portable Executable section and its immutable fingerprint."""

    index: int
    name: str
    virtual_address: int
    virtual_size: int
    raw_offset: int
    raw_size: int
    characteristics: int
    sha256: str

    @property
    def virtual_end(self) -> int:
        return self.virtual_address + max(self.virtual_size, self.raw_size)

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "virtual_address": self.virtual_address,
            "virtual_size": self.virtual_size,
            "raw_offset": self.raw_offset,
            "raw_size": self.raw_size,
            "characteristics": self.characteristics,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class PeImage:
    """Reviewed PE metadata needed by the alignment foundation."""

    path: str
    sha256: str
    length: int
    machine: int
    pointer_size: int
    image_base: int
    entry_point_rva: int
    section_alignment: int
    file_alignment: int
    size_of_image: int
    size_of_headers: int
    characteristics: int
    optional_header_magic: int
    sections: tuple[PeSection, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "length": self.length,
            "machine": self.machine,
            "pointer_size": self.pointer_size,
            "image_base": self.image_base,
            "entry_point_rva": self.entry_point_rva,
            "section_alignment": self.section_alignment,
            "file_alignment": self.file_alignment,
            "size_of_image": self.size_of_image,
            "size_of_headers": self.size_of_headers,
            "characteristics": self.characteristics,
            "optional_header_magic": self.optional_header_magic,
            "sections": [section.as_dict() for section in self.sections],
        }


@dataclass(frozen=True, slots=True)
class CalibratedAnchor:
    """One profile-declared client RVA and any exact byte signature attached to it."""

    profile_id: str
    profile_file: str
    executable_sha256: str
    field_path: str
    rva_start: int
    length: int
    signature_hex: str | None

    @property
    def rva_end(self) -> int:
        return self.rva_start + self.length

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_file": self.profile_file,
            "executable_sha256": self.executable_sha256,
            "field_path": self.field_path,
            "rva_start": self.rva_start,
            "rva_end_exclusive": self.rva_end,
            "length": self.length,
            "signature_hex": self.signature_hex,
        }


@dataclass(frozen=True, slots=True)
class ProfileInventory:
    """Profiles and calibrated anchors applicable to one reference build."""

    profile_files_scanned: int
    native_profile_count: int
    applicable_profile_count: int
    anchors: tuple[CalibratedAnchor, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_files_scanned": self.profile_files_scanned,
            "native_profile_count": self.native_profile_count,
            "applicable_profile_count": self.applicable_profile_count,
            "calibrated_anchor_count": len(self.anchors),
            "anchors": [anchor.as_dict() for anchor in self.anchors],
        }


@dataclass(frozen=True, slots=True)
class ChangedRange:
    """One contiguous changed range in a comparable PE region."""

    region: str
    file_offset_start: int
    file_offset_end_exclusive: int
    rva_start: int | None
    rva_end_exclusive: int | None
    changed_byte_count: int

    def overlaps(self, anchor: CalibratedAnchor) -> bool:
        if self.rva_start is None or self.rva_end_exclusive is None:
            return False
        return self.rva_start < anchor.rva_end and anchor.rva_start < self.rva_end_exclusive

    def as_dict(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "file_offset_start": self.file_offset_start,
            "file_offset_end_exclusive": self.file_offset_end_exclusive,
            "rva_start": self.rva_start,
            "rva_end_exclusive": self.rva_end_exclusive,
            "changed_byte_count": self.changed_byte_count,
        }


@dataclass(frozen=True, slots=True)
class AnchorIntersection:
    """Evidence that a changed range touches one calibrated anchor."""

    anchor: CalibratedAnchor
    changed_range: ChangedRange

    def as_dict(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor.as_dict(),
            "changed_range": self.changed_range.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ClientAlignmentReport:
    """Deterministic offline comparison between two client executable files."""

    schema_version: int
    reference: PeImage
    candidate: PeImage
    exact_file_match: bool
    pe_header_layout_equal: bool
    section_layouts_equal: bool
    unchanged_sections: tuple[str, ...]
    changed_sections: tuple[str, ...]
    changed_byte_count: int
    changed_ranges: tuple[ChangedRange, ...]
    profile_inventory: ProfileInventory
    anchor_intersections: tuple[AnchorIntersection, ...]
    recommendation: str
    proposed_compatibility_evidence: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "reference": self.reference.as_dict(),
            "candidate": self.candidate.as_dict(),
            "comparison": {
                "exact_file_match": self.exact_file_match,
                "pe_header_layout_equal": self.pe_header_layout_equal,
                "section_layouts_equal": self.section_layouts_equal,
                "unchanged_sections": list(self.unchanged_sections),
                "changed_sections": list(self.changed_sections),
                "changed_byte_count": self.changed_byte_count,
                "changed_range_count": len(self.changed_ranges),
                "changed_ranges": [
                    changed_range.as_dict() for changed_range in self.changed_ranges
                ],
            },
            "profiles": self.profile_inventory.as_dict(),
            "calibrated_anchor_intersection_count": len(self.anchor_intersections),
            "calibrated_anchor_intersections": [
                intersection.as_dict() for intersection in self.anchor_intersections
            ],
            "recommendation": self.recommendation,
            "proposed_compatibility_evidence": self.proposed_compatibility_evidence,
        }


__all__ = [
    "AnchorIntersection",
    "CalibratedAnchor",
    "ChangedRange",
    "ClientAlignmentReport",
    "PeImage",
    "PeSection",
    "ProfileInventory",
]
