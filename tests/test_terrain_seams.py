import hashlib
import json
import struct
import zlib
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import jsonschema
import pytest

from shadowbane_lab.world_data.cache import CacheArchive
from shadowbane_lab.world_data.terrain import index_terrain_alpha_maps
from shadowbane_lab.world_data.terrain_seam_cli import main as terrain_audit_main
from shadowbane_lab.world_data.terrain_seams import (
    TERRAIN_SEAM_AUDIT_REPORT_FILE_NAME,
    audit_terrain_archive,
    audit_terrain_map,
    write_terrain_seam_audit_bundle,
    write_terrain_seam_heatmap,
)


def _write_cache(path: Path, resources: list[tuple[int, int, bytes, bool]]) -> None:
    data_offset = 16 + 20 * len(resources)
    directory = bytearray()
    payload = bytearray()
    for group_id, resource_id, raw, compress in resources:
        stored = zlib.compress(raw) if compress else raw
        directory.extend(
            struct.pack(
                "<IIIII",
                group_id,
                resource_id,
                data_offset + len(payload),
                len(raw),
                len(stored),
            )
        )
        payload.extend(stored)
    file_size = data_offset + len(payload)
    path.write_bytes(
        struct.pack("<IIII", len(resources), data_offset, file_size, 0xFFFF_FFFF)
        + directory
        + payload
    )


def _terrain_payload(samples: bytes, *, width: int, height: int) -> bytes:
    return struct.pack("<IIIII2BI", width, height, 1, 1, 0, 1, 1, len(samples)) + samples


def _terrain_resource_id(map_id: int, tile_x: int, tile_y: int) -> int:
    return (map_id << 24) | (tile_x * 1_000 + tile_y + 1)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_two_tile_gradient_cache(path: Path) -> None:
    left = bytes((0, 1, 2, 10, 11, 12, 20, 21, 22))
    right = bytes((2, 3, 4, 15, 16, 17, 20, 19, 18))
    _write_cache(
        path,
        [
            (12, _terrain_resource_id(7, 0, 0), _terrain_payload(left, width=3, height=3), True),
            (
                12,
                _terrain_resource_id(7, 1, 0),
                _terrain_payload(right, width=3, height=3),
                True,
            ),
        ],
    )


def test_audits_border_and_inward_gradient_without_losing_tile_identity() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "TerrainAlpha.cache"
        _write_two_tile_gradient_cache(path)
        with CacheArchive(path) as archive:
            terrain_map = index_terrain_alpha_maps(archive)[0]
            audit = audit_terrain_map(archive, terrain_map)

    assert audit.status == "complete"
    assert audit.roles == ("unclassified",)
    assert len(audit.tiles) == 2
    assert len(audit.seams) == 1
    seam = audit.seams[0]
    assert seam.axis == "x"
    assert seam.first_tile == (0, 0)
    assert seam.second_tile == (1, 0)
    assert seam.border_delta.minimum == -2
    assert seam.border_delta.maximum == 3
    assert seam.border_delta.mean == 0.333333
    assert seam.border_delta.absolute_p50 == 2
    assert seam.border_delta.absolute_p95 == 3
    assert seam.first_inward_gradient.mean == 1.0
    assert seam.second_inward_gradient.mean == -0.333333
    assert seam.gradient_discontinuity.absolute_p95 == 2
    assert seam.diagnostic_score == 3
    assert all(len(item.payload_sha256) == 64 for item in audit.tiles)


def test_y_axis_uses_lower_then_upper_and_equal_opposite_inward_gradients() -> None:
    lower = bytes((0, 10, 1, 11, 2, 12))
    upper = bytes((2, 12, 3, 13, 4, 14))
    resources = [
        (
            8,
            _terrain_resource_id(6, 0, 0),
            _terrain_payload(lower, width=2, height=3),
            False,
        ),
        (
            8,
            _terrain_resource_id(6, 0, 1),
            _terrain_payload(upper, width=2, height=3),
            False,
        ),
    ]
    with TemporaryDirectory() as directory:
        path = Path(directory) / "TerrainAlpha.cache"
        _write_cache(path, resources)
        with CacheArchive(path) as archive:
            audit = audit_terrain_map(archive, index_terrain_alpha_maps(archive)[0])

    assert len(audit.seams) == 1
    seam = audit.seams[0]
    assert seam.axis == "y"
    assert seam.first_tile == (0, 0)
    assert seam.second_tile == (0, 1)
    assert seam.border_delta.absolute_maximum == 0
    assert seam.first_inward_gradient.mean == 1.0
    assert seam.second_inward_gradient.mean == -1.0
    assert seam.gradient_discontinuity.absolute_maximum == 0


def test_mixed_tile_dimensions_are_reported_without_cross_tile_comparison() -> None:
    resources = [
        (
            4,
            _terrain_resource_id(3, 0, 0),
            _terrain_payload(bytes((1, 2, 3, 4)), width=2, height=2),
            False,
        ),
        (
            4,
            _terrain_resource_id(3, 1, 0),
            _terrain_payload(bytes((1, 2, 3, 4, 5, 6)), width=3, height=2),
            False,
        ),
    ]
    with TemporaryDirectory() as directory:
        path = Path(directory) / "TerrainAlpha.cache"
        _write_cache(path, resources)
        with CacheArchive(path) as archive:
            audit = audit_terrain_map(archive, index_terrain_alpha_maps(archive)[0])

    assert audit.status == "mixed-tile-dimensions"
    assert audit.tile_width is None
    assert audit.tile_height is None
    assert audit.seams == ()
    assert len(audit.tiles) == 2


def test_checks_four_tile_corner_junction_spread() -> None:
    resources = [
        (
            5,
            _terrain_resource_id(9, 0, 0),
            _terrain_payload(bytes((0, 0, 0, 10)), width=2, height=2),
            False,
        ),
        (
            5,
            _terrain_resource_id(9, 1, 0),
            _terrain_payload(bytes((0, 0, 12, 0)), width=2, height=2),
            False,
        ),
        (
            5,
            _terrain_resource_id(9, 0, 1),
            _terrain_payload(bytes((0, 20, 0, 0)), width=2, height=2),
            False,
        ),
        (
            5,
            _terrain_resource_id(9, 1, 1),
            _terrain_payload(bytes((14, 0, 0, 0)), width=2, height=2),
            False,
        ),
    ]
    with TemporaryDirectory() as directory:
        path = Path(directory) / "TerrainAlpha.cache"
        _write_cache(path, resources)
        with CacheArchive(path) as archive:
            audit = audit_terrain_map(archive, index_terrain_alpha_maps(archive)[0])

    assert len(audit.corners) == 1
    corner = audit.corners[0]
    assert (corner.junction_x, corner.junction_y) == (1, 1)
    assert corner.values == (10, 12, 20, 14)
    assert corner.spread == 10
    assert audit.summary["max_corner_spread"] == 10


def test_labels_complete_zone_layers_without_treating_partial_matches_as_valid() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        terrain_path = root / "TerrainAlpha.cache"
        zone_path = root / "CZone.cache"
        height_resources = [
            (
                12,
                _terrain_resource_id(1, tile_x, 0),
                _terrain_payload(bytes((1, 2, 3, 4)), width=2, height=2),
                True,
            )
            for tile_x in range(2)
        ]
        material_resource = (
            12,
            _terrain_resource_id(2, 0, 0),
            _terrain_payload(bytes((5, 6, 7, 8)), width=2, height=2),
            True,
        )
        _write_cache(terrain_path, [*height_resources, material_resource])
        complete_payload = b"prefix" + b"".join(
            struct.pack("<II", group_id, resource_id)
            for group_id, resource_id, _, _ in [*height_resources, material_resource]
        )
        partial_payload = struct.pack(
            "<II",
            height_resources[0][0],
            height_resources[0][1],
        )
        unsafe_mixed_payload = partial_payload + struct.pack(
            "<II",
            material_resource[0],
            material_resource[1],
        )
        _write_cache(
            zone_path,
            [
                (0, 524, complete_payload, True),
                (0, 525, partial_payload, False),
                (0, 526, unsafe_mixed_payload, False),
            ],
        )
        terrain_before = _sha256(terrain_path)
        zone_before = _sha256(zone_path)
        report = audit_terrain_archive(
            terrain_path,
            zone_cache_path=zone_path,
            created_at=datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        )

    by_map = {item.map_id: item for item in report.maps}
    assert by_map[1].roles == ("height",)
    assert by_map[1].zone_references[0].template_id == 524
    assert by_map[1].zone_references[0].layer_index == 0
    assert by_map[2].roles == ("material",)
    assert by_map[2].zone_references[0].layer_index == 1
    assert all(item.template_id != 526 for item in by_map[2].zone_references)
    assert report.valid_zone_map_references == 2
    assert report.zone_correlation_issues[0].template_id == 525
    assert report.zone_correlation_issues[0].kind == "partial-map-reference"
    assert any(item.template_id == 526 for item in report.zone_correlation_issues)
    assert report.terrain_source["sha256"] == terrain_before
    assert report.zone_source is not None
    assert report.zone_source["sha256"] == zone_before


def test_incomplete_source_map_never_receives_a_zone_layer_role() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        terrain_path = root / "TerrainAlpha.cache"
        zone_path = root / "CZone.cache"
        resources = [
            (
                3,
                _terrain_resource_id(4, 0, 0),
                _terrain_payload(bytes((0, 1, 2, 3)), width=2, height=2),
                False,
            ),
            (
                3,
                _terrain_resource_id(4, 2, 0),
                _terrain_payload(bytes((4, 5, 6, 7)), width=2, height=2),
                False,
            ),
        ]
        _write_cache(terrain_path, resources)
        zone_payload = b"".join(
            struct.pack("<II", group_id, resource_id)
            for group_id, resource_id, _, _ in resources
        )
        _write_cache(zone_path, [(0, 700, zone_payload, False)])
        report = audit_terrain_archive(terrain_path, zone_cache_path=zone_path)

    assert report.maps[0].status == "incomplete"
    assert report.maps[0].roles == ("unclassified",)
    assert report.valid_zone_map_references == 0
    assert report.zone_correlation_issues[0].kind == "incomplete-source-map"
    assert report.zone_correlation_issues[0].expected_tile_count == 3


def test_reports_incomplete_map_and_only_audits_available_neighbours() -> None:
    resources = [
        (
            3,
            _terrain_resource_id(4, 0, 0),
            _terrain_payload(bytes((0, 1, 2, 3)), width=2, height=2),
            False,
        ),
        (
            3,
            _terrain_resource_id(4, 2, 0),
            _terrain_payload(bytes((4, 5, 6, 7)), width=2, height=2),
            False,
        ),
    ]
    with TemporaryDirectory() as directory:
        path = Path(directory) / "TerrainAlpha.cache"
        _write_cache(path, resources)
        with CacheArchive(path) as archive:
            audit = audit_terrain_map(archive, index_terrain_alpha_maps(archive)[0])

    assert audit.status == "incomplete"
    assert audit.missing_tiles == ((1, 0),)
    assert audit.seams == ()
    assert audit.issues == ("map is missing 1 tile positions",)


def test_writes_deterministic_standard_library_png_heatmap() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        terrain_path = root / "TerrainAlpha.cache"
        target = root / "heatmap.png"
        _write_two_tile_gradient_cache(terrain_path)
        with CacheArchive(terrain_path) as archive:
            audit = audit_terrain_map(archive, index_terrain_alpha_maps(archive)[0])
        dimensions = write_terrain_seam_heatmap(audit, target, scale=2)
        first = target.read_bytes()

    assert dimensions == (6, 2)
    assert first.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", first[16:24])
    assert (width, height) == dimensions


def test_bundle_and_cli_publish_create_only_schema_valid_results() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        terrain_path = root / "TerrainAlpha.cache"
        bundle_path = root / "bundle"
        cli_bundle_path = root / "cli-bundle"
        _write_two_tile_gradient_cache(terrain_path)
        source_before = _sha256(terrain_path)
        report = audit_terrain_archive(
            terrain_path,
            created_at=datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        )
        bundle = write_terrain_seam_audit_bundle(
            report,
            bundle_path,
            heatmap_limit=1,
            heatmap_scale=2,
            pretty=False,
        )
        payload = json.loads(bundle.report_path.read_text(encoding="ascii"))
        with pytest.raises(FileExistsError):
            write_terrain_seam_audit_bundle(report, bundle_path)
        schema = json.loads(
            (Path(__file__).parents[1] / "schemas" / "terrain-seam-audit-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.validate(payload, schema)
        detail_schema = json.loads(
            (Path(__file__).parents[1] / "schemas" / "terrain-seam-map-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        for detail_path in bundle.map_detail_paths:
            jsonschema.validate(
                json.loads(detail_path.read_text(encoding="ascii")),
                detail_schema,
            )
        result = terrain_audit_main(
            (
                str(terrain_path),
                str(cli_bundle_path),
                "--heatmap-limit",
                "0",
                "--compact",
            )
        )
        source_after = _sha256(terrain_path)
        detail_file_sha256 = _sha256(bundle.map_detail_paths[0])

    assert result == 0
    assert bundle.report_path.name == TERRAIN_SEAM_AUDIT_REPORT_FILE_NAME
    assert len(bundle.map_detail_paths) == 1
    assert len(bundle.heatmap_paths) == 1
    assert payload["maps"][0]["detail_file_sha256"] == detail_file_sha256
    assert payload["schema_version"] == 1
    assert len(payload["analysis_sha256"]) == 64
    assert payload["summary"]["seam_count"] == 1
    assert len(payload["artifacts"]["heatmaps"]) == 1
    assert source_after == source_before


def test_analysis_digest_excludes_generation_timestamp_and_source_path() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        first_path = root / "first" / "TerrainAlpha.cache"
        second_path = root / "second" / "TerrainAlpha.cache"
        first_path.parent.mkdir()
        second_path.parent.mkdir()
        _write_two_tile_gradient_cache(first_path)
        second_path.write_bytes(first_path.read_bytes())
        first = audit_terrain_archive(
            first_path,
            created_at=datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        ).as_dict()
        second = audit_terrain_archive(
            second_path,
            created_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        ).as_dict()

    assert first["created_at_utc"] != second["created_at_utc"]
    assert first["sources"]["terrain_alpha"]["path"] != (
        second["sources"]["terrain_alpha"]["path"]
    )
    assert first["analysis_sha256"] == second["analysis_sha256"]
