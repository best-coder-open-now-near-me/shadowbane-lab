"""Pure byte-range comparison for structurally compatible PE images."""

from __future__ import annotations

from shadowbane_lab.client_alignment.model import ChangedRange, PeImage
from shadowbane_lab.client_alignment.pe import section_layout_key


def _contiguous_differences(
    reference: bytes,
    candidate: bytes,
    *,
    region: str,
    file_offset: int,
    rva_base: int | None,
) -> tuple[ChangedRange, ...]:
    limit = max(len(reference), len(candidate))
    ranges: list[ChangedRange] = []
    start: int | None = None
    changed_count = 0

    for index in range(limit):
        different = (
            index >= len(reference)
            or index >= len(candidate)
            or reference[index] != candidate[index]
        )
        if different:
            changed_count += 1
            if start is None:
                start = index
        elif start is not None:
            ranges.append(
                _changed_range(
                    reference,
                    candidate,
                    start=start,
                    end=index,
                    region=region,
                    file_offset=file_offset,
                    rva_base=rva_base,
                )
            )
            start = None

    if start is not None:
        ranges.append(
            _changed_range(
                reference,
                candidate,
                start=start,
                end=limit,
                region=region,
                file_offset=file_offset,
                rva_base=rva_base,
            )
        )

    if changed_count != sum(changed_range.changed_byte_count for changed_range in ranges):
        raise AssertionError("changed-range accounting is inconsistent")
    return tuple(ranges)


def _changed_range(
    reference: bytes,
    candidate: bytes,
    *,
    start: int,
    end: int,
    region: str,
    file_offset: int,
    rva_base: int | None,
) -> ChangedRange:
    changed_byte_count = sum(
        1
        for position in range(start, end)
        if position >= len(reference)
        or position >= len(candidate)
        or reference[position] != candidate[position]
    )
    return ChangedRange(
        region=region,
        file_offset_start=file_offset + start,
        file_offset_end_exclusive=file_offset + end,
        rva_start=None if rva_base is None else rva_base + start,
        rva_end_exclusive=None if rva_base is None else rva_base + end,
        changed_byte_count=changed_byte_count,
    )


def _covered_intervals(image: PeImage) -> tuple[tuple[int, int], ...]:
    intervals = [(0, image.size_of_headers)]
    intervals.extend(
        (section.raw_offset, section.raw_offset + section.raw_size)
        for section in image.sections
        if section.raw_size
    )
    return tuple(sorted(intervals))


def _unmapped_intervals(image: PeImage) -> tuple[tuple[int, int], ...]:
    cursor = 0
    intervals: list[tuple[int, int]] = []
    for start, end in _covered_intervals(image):
        if cursor < start:
            intervals.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < image.length:
        intervals.append((cursor, image.length))
    return tuple(intervals)


def changed_ranges(
    reference_data: bytes,
    candidate_data: bytes,
    reference: PeImage,
    candidate: PeImage,
) -> tuple[ChangedRange, ...]:
    """Return deterministic changed ranges and preserve RVAs only for equal layouts."""

    if section_layout_key(reference) != section_layout_key(candidate):
        return _contiguous_differences(
            reference_data,
            candidate_data,
            region="<file>",
            file_offset=0,
            rva_base=None,
        )

    ranges: list[ChangedRange] = []
    header_size = reference.size_of_headers
    if candidate.size_of_headers != header_size:
        raise AssertionError("equal section layout unexpectedly has different header size")
    ranges.extend(
        _contiguous_differences(
            reference_data[:header_size],
            candidate_data[:header_size],
            region="<headers>",
            file_offset=0,
            rva_base=None,
        )
    )

    for reference_section, candidate_section in zip(
        reference.sections, candidate.sections, strict=True
    ):
        start = reference_section.raw_offset
        end = start + reference_section.raw_size
        candidate_start = candidate_section.raw_offset
        candidate_end = candidate_start + candidate_section.raw_size
        ranges.extend(
            _contiguous_differences(
                reference_data[start:end],
                candidate_data[candidate_start:candidate_end],
                region=reference_section.name,
                file_offset=start,
                rva_base=reference_section.virtual_address,
            )
        )

    reference_unmapped = _unmapped_intervals(reference)
    candidate_unmapped = _unmapped_intervals(candidate)
    if reference_unmapped == candidate_unmapped:
        for start, end in reference_unmapped:
            ranges.extend(
                _contiguous_differences(
                    reference_data[start:end],
                    candidate_data[start:end],
                    region="<unmapped>",
                    file_offset=start,
                    rva_base=None,
                )
            )
    elif reference.length != candidate.length:
        covered_end = max(
            [reference.size_of_headers]
            + [section.raw_offset + section.raw_size for section in reference.sections]
        )
        ranges.extend(
            _contiguous_differences(
                reference_data[covered_end:],
                candidate_data[covered_end:],
                region="<overlay>",
                file_offset=covered_end,
                rva_base=None,
            )
        )

    return tuple(
        sorted(
            ranges,
            key=lambda changed_range: (
                changed_range.file_offset_start,
                changed_range.file_offset_end_exclusive,
                changed_range.region,
            ),
        )
    )


def section_status(
    reference: PeImage, candidate: PeImage
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return section names whose complete layouts and hashes are unchanged or changed."""

    unchanged: list[str] = []
    changed: list[str] = []
    maximum = max(len(reference.sections), len(candidate.sections))
    for index in range(maximum):
        left = reference.sections[index] if index < len(reference.sections) else None
        right = candidate.sections[index] if index < len(candidate.sections) else None
        display = left.name if left is not None else right.name if right is not None else str(index)
        if left is not None and right is not None and left == right:
            unchanged.append(display)
        else:
            changed.append(display)
    return tuple(unchanged), tuple(changed)


__all__ = ["changed_ranges", "section_status"]
