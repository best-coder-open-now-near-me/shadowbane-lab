"""Fail-closed patch-site alignment and exact-source patch planning."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from shadowbane_lab.client_alignment.model import PeImage, PeSection
from shadowbane_lab.client_alignment.pe import PeInspectionError, inspect_pe_bytes
from shadowbane_lab.client_extension.manifest import PatchManifest, PatchSite


class PatchResolutionError(ValueError):
    """Raised when a reviewed patch cannot be resolved without ambiguity."""


class PatchSiteStatus(StrEnum):
    EXACT = "exact"
    RELOCATED = "relocated"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    SECTION_MISSING = "section_missing"
    ARCHITECTURE_MISMATCH = "architecture_mismatch"


@dataclass(frozen=True, slots=True)
class PatchSiteResolution:
    site_id: str
    status: PatchSiteStatus
    reviewed_rva: int
    resolved_rva: int | None
    file_offset: int | None
    candidate_rvas: tuple[int, ...]

    @property
    def resolved(self) -> bool:
        return self.status in {PatchSiteStatus.EXACT, PatchSiteStatus.RELOCATED}

    def as_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "status": self.status.value,
            "reviewed_rva": self.reviewed_rva,
            "resolved_rva": self.resolved_rva,
            "file_offset": self.file_offset,
            "candidate_rvas": list(self.candidate_rvas),
        }


@dataclass(frozen=True, slots=True)
class PatchAlignmentReport:
    candidate_sha256: str
    candidate_length: int
    machine: int
    pointer_size: int
    exact_source_match: bool
    architecture_matches: bool
    sites: tuple[PatchSiteResolution, ...]

    @property
    def all_sites_resolved(self) -> bool:
        return self.architecture_matches and all(site.resolved for site in self.sites)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_sha256": self.candidate_sha256,
            "candidate_length": self.candidate_length,
            "machine": self.machine,
            "pointer_size": self.pointer_size,
            "exact_source_match": self.exact_source_match,
            "architecture_matches": self.architecture_matches,
            "all_sites_resolved": self.all_sites_resolved,
            "sites": [site.as_dict() for site in self.sites],
        }


@dataclass(frozen=True, slots=True)
class PatchWrite:
    site_id: str
    rva: int
    file_offset: int
    expected_original: bytes
    replacement: bytes

    @property
    def end_offset(self) -> int:
        return self.file_offset + len(self.replacement)

    def as_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "rva": self.rva,
            "file_offset": self.file_offset,
            "length": len(self.replacement),
            "expected_original_hex": self.expected_original.hex(),
            "replacement_hex": self.replacement.hex(),
        }


@dataclass(frozen=True, slots=True)
class PatchPlan:
    patch_id: str
    source_sha256: str
    result_sha256: str
    already_patched: bool
    writes: tuple[PatchWrite, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "source_sha256": self.source_sha256,
            "result_sha256": self.result_sha256,
            "already_patched": self.already_patched,
            "writes": [write.as_dict() for write in self.writes],
        }


def align_patch_sites(candidate: bytes, manifest: PatchManifest) -> PatchAlignmentReport:
    """Align sites for evidence only; this function never authorizes patching."""

    try:
        image = inspect_pe_bytes(candidate, path=manifest.source.file_name)
    except PeInspectionError as exc:
        raise PatchResolutionError(f"candidate is not a supported PE image: {exc}") from exc
    architecture_matches = (
        image.machine == manifest.source.machine
        and image.pointer_size == manifest.source.pointer_size
    )
    if not architecture_matches:
        resolutions = tuple(
            PatchSiteResolution(
                site_id=site.site_id,
                status=PatchSiteStatus.ARCHITECTURE_MISMATCH,
                reviewed_rva=site.reviewed_rva,
                resolved_rva=None,
                file_offset=None,
                candidate_rvas=(),
            )
            for site in manifest.sites
        )
    else:
        resolutions = tuple(
            _resolve_site(candidate, image, site, expected_bytes=site.expected_original)
            for site in manifest.sites
        )
    return PatchAlignmentReport(
        candidate_sha256=image.sha256,
        candidate_length=image.length,
        machine=image.machine,
        pointer_size=image.pointer_size,
        exact_source_match=image.sha256 == manifest.source.sha256,
        architecture_matches=architecture_matches,
        sites=resolutions,
    )


def build_patch_plan(source: bytes, manifest: PatchManifest) -> PatchPlan:
    """Build a verified plan for only the exact reviewed source or patched output."""

    try:
        image = inspect_pe_bytes(source, path=manifest.source.file_name)
    except PeInspectionError as exc:
        raise PatchResolutionError(f"source is not a supported PE image: {exc}") from exc
    _require_architecture(image, manifest)

    if image.sha256 == manifest.patched_executable_sha256:
        _verify_already_patched(source, image, manifest)
        return PatchPlan(
            patch_id=manifest.patch_id,
            source_sha256=image.sha256,
            result_sha256=image.sha256,
            already_patched=True,
            writes=(),
        )

    if image.sha256 != manifest.source.sha256:
        raise PatchResolutionError(
            "source SHA-256 is neither the reviewed source nor the predicted patched output"
        )
    if image.length != manifest.source.length:
        raise PatchResolutionError("source length does not match the reviewed manifest")

    report = align_patch_sites(source, manifest)
    unresolved = tuple(site for site in report.sites if not site.resolved)
    if unresolved:
        detail = ", ".join(f"{site.site_id}={site.status.value}" for site in unresolved)
        raise PatchResolutionError(f"one or more patch sites did not resolve uniquely: {detail}")

    writes = tuple(
        PatchWrite(
            site_id=site.site_id,
            rva=resolution.resolved_rva,
            file_offset=resolution.file_offset,
            expected_original=site.expected_original,
            replacement=site.replacement,
        )
        for site, resolution in zip(manifest.sites, report.sites, strict=True)
        if resolution.resolved_rva is not None and resolution.file_offset is not None
    )
    if len(writes) != len(manifest.sites):
        raise PatchResolutionError("internal resolution invariant failed")
    _reject_overlapping_writes(writes)

    patched = apply_patch_plan(source, writes)
    result_sha256 = hashlib.sha256(patched).hexdigest()
    if result_sha256 != manifest.patched_executable_sha256:
        raise PatchResolutionError("predicted patched executable SHA-256 does not match the plan")
    return PatchPlan(
        patch_id=manifest.patch_id,
        source_sha256=image.sha256,
        result_sha256=result_sha256,
        already_patched=False,
        writes=writes,
    )


def apply_patch_plan(source: bytes, writes: tuple[PatchWrite, ...]) -> bytes:
    """Apply an already-reviewed in-memory plan after rechecking original bytes."""

    _reject_overlapping_writes(writes)
    output = bytearray(source)
    for write in writes:
        end = write.file_offset + len(write.expected_original)
        if write.file_offset < 0 or end > len(output):
            raise PatchResolutionError(f"patch write is outside the file: {write.site_id}")
        if bytes(output[write.file_offset:end]) != write.expected_original:
            raise PatchResolutionError(f"patch write precondition changed: {write.site_id}")
        output[write.file_offset:end] = write.replacement
    return bytes(output)


def _resolve_site(
    candidate: bytes,
    image: PeImage,
    site: PatchSite,
    *,
    expected_bytes: bytes,
) -> PatchSiteResolution:
    section = _named_section(image, site.section)
    if section is None:
        return PatchSiteResolution(
            site_id=site.site_id,
            status=PatchSiteStatus.SECTION_MISSING,
            reviewed_rva=site.reviewed_rva,
            resolved_rva=None,
            file_offset=None,
            candidate_rvas=(),
        )

    exact_offset = _rva_to_file_offset(
        image,
        site.reviewed_rva,
        len(expected_bytes),
        section=section,
    )
    if exact_offset is not None:
        exact_end = exact_offset + len(expected_bytes)
        if candidate[exact_offset:exact_end] == expected_bytes:
            return PatchSiteResolution(
                site_id=site.site_id,
                status=PatchSiteStatus.EXACT,
                reviewed_rva=site.reviewed_rva,
                resolved_rva=site.reviewed_rva,
                file_offset=exact_offset,
                candidate_rvas=(site.reviewed_rva,),
            )

    candidate_rvas = _signature_candidate_site_rvas(
        candidate,
        section,
        site,
        expected_bytes=expected_bytes,
    )
    if len(candidate_rvas) == 1:
        resolved_rva = candidate_rvas[0]
        file_offset = _rva_to_file_offset(image, resolved_rva, site.length, section=section)
        if file_offset is None:
            raise PatchResolutionError("internal signature resolution invariant failed")
        return PatchSiteResolution(
            site_id=site.site_id,
            status=PatchSiteStatus.RELOCATED,
            reviewed_rva=site.reviewed_rva,
            resolved_rva=resolved_rva,
            file_offset=file_offset,
            candidate_rvas=candidate_rvas,
        )
    status = PatchSiteStatus.AMBIGUOUS if candidate_rvas else PatchSiteStatus.MISSING
    return PatchSiteResolution(
        site_id=site.site_id,
        status=status,
        reviewed_rva=site.reviewed_rva,
        resolved_rva=None,
        file_offset=None,
        candidate_rvas=candidate_rvas,
    )


def _signature_candidate_site_rvas(
    candidate: bytes,
    section: PeSection,
    site: PatchSite,
    *,
    expected_bytes: bytes,
) -> tuple[int, ...]:
    section_start_rva = section.virtual_address
    section_end_rva = section.virtual_address + section.raw_size
    reviewed_signature_rva = site.reviewed_rva - site.signature_site_offset
    first_signature_rva = max(
        section_start_rva,
        reviewed_signature_rva - site.search_radius,
    )
    last_signature_rva = min(
        section_end_rva - site.signature.length,
        reviewed_signature_rva + site.search_radius,
    )
    if last_signature_rva < first_signature_rva:
        return ()
    search_start_offset = section.raw_offset + (first_signature_rva - section_start_rva)
    search_end_rva = last_signature_rva + site.signature.length
    search_end_offset = section.raw_offset + (search_end_rva - section_start_rva)
    region = candidate[search_start_offset:search_end_offset]
    resolved: set[int] = set()
    last_start = len(region) - site.signature.length
    for relative in range(last_start + 1):
        if not site.signature.matches(region[relative : relative + site.signature.length]):
            continue
        signature_rva = first_signature_rva + relative
        candidate_site_rva = signature_rva + site.signature_site_offset
        if candidate_site_rva < section_start_rva:
            continue
        site_relative = candidate_site_rva - section_start_rva
        if site_relative + len(expected_bytes) > section.raw_size:
            continue
        site_offset = section.raw_offset + site_relative
        if candidate[site_offset : site_offset + len(expected_bytes)] == expected_bytes:
            resolved.add(candidate_site_rva)
    return tuple(sorted(resolved))


def _verify_already_patched(source: bytes, image: PeImage, manifest: PatchManifest) -> None:
    if image.length != manifest.source.length:
        raise PatchResolutionError("patched executable length differs from the reviewed source")
    for site in manifest.sites:
        resolution = _resolve_site(
            source,
            image,
            site,
            expected_bytes=site.replacement,
        )
        if not resolution.resolved:
            raise PatchResolutionError(
                f"patched output hash matched but replacement bytes failed for {site.site_id}"
            )


def _require_architecture(image: PeImage, manifest: PatchManifest) -> None:
    if image.machine != manifest.source.machine:
        raise PatchResolutionError("source machine does not match the reviewed manifest")
    if image.pointer_size != manifest.source.pointer_size:
        raise PatchResolutionError("source pointer size does not match the reviewed manifest")


def _named_section(image: PeImage, name: str) -> PeSection | None:
    matches = tuple(section for section in image.sections if section.name == name)
    if len(matches) > 1:
        raise PatchResolutionError(f"PE contains duplicate section name: {name}")
    return matches[0] if matches else None


def _rva_to_file_offset(
    image: PeImage,
    rva: int,
    length: int,
    *,
    section: PeSection | None = None,
) -> int | None:
    sections = (section,) if section is not None else image.sections
    for current in sections:
        relative = rva - current.virtual_address
        if relative < 0 or relative + length > current.raw_size:
            continue
        return current.raw_offset + relative
    return None


def _reject_overlapping_writes(writes: tuple[PatchWrite, ...]) -> None:
    ordered = sorted(writes, key=lambda write: (write.file_offset, write.end_offset))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous.end_offset > current.file_offset:
            raise PatchResolutionError(
                f"patch writes overlap: {previous.site_id} and {current.site_id}"
            )


__all__ = [
    "PatchAlignmentReport",
    "PatchPlan",
    "PatchResolutionError",
    "PatchSiteResolution",
    "PatchSiteStatus",
    "PatchWrite",
    "align_patch_sites",
    "apply_patch_plan",
    "build_patch_plan",
]
