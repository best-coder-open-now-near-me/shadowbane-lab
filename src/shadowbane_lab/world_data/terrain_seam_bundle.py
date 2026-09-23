"""Atomic JSON and deterministic heatmap publication for terrain seam evidence."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from shadowbane_lab.world_data.terrain_seam_report import (
    TerrainMapSeamAudit,
    TerrainSeamAuditBundle,
    TerrainSeamAuditReport,
)
from shadowbane_lab.world_data.terrain_seam_support import (
    TERRAIN_SEAM_AUDIT_REPORT_FILE_NAME,
    TERRAIN_SEAM_AUDIT_SCHEMA_VERSION,
    TerrainSeamAuditError,
    _byte,
    _encode_rgb_png,
    _sha256_file,
)


def write_terrain_seam_audit_bundle(
    report: TerrainSeamAuditReport,
    destination_directory: str | Path,
    *,
    heatmap_limit: int = 12,
    heatmap_scale: int = 16,
    pretty: bool = True,
) -> TerrainSeamAuditBundle:
    """Atomically publish a create-only JSON report and deterministic PNG heatmaps."""

    if not isinstance(report, TerrainSeamAuditReport):
        raise ValueError("report must be TerrainSeamAuditReport")
    if not isinstance(pretty, bool):
        raise ValueError("pretty must be a Boolean")
    if isinstance(heatmap_limit, bool) or not isinstance(heatmap_limit, int):
        raise ValueError("heatmap_limit must be an integer")
    if heatmap_limit < -1:
        raise ValueError("heatmap_limit must be -1, zero, or a positive integer")
    if (
        isinstance(heatmap_scale, bool)
        or not isinstance(heatmap_scale, int)
        or not 1 <= heatmap_scale <= 64
    ):
        raise ValueError("heatmap_scale must be between 1 and 64")
    destination = Path(destination_directory).resolve()
    if destination.exists():
        raise FileExistsError(f"terrain audit destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=destination.parent,
        )
    )
    published = False
    try:
        map_root = temporary / "maps"
        map_root.mkdir()
        map_artifacts: dict[tuple[int, int], dict[str, object]] = {}
        map_detail_paths: list[Path] = []
        for terrain_map in report.maps:
            relative_path = Path("maps") / (
                f"group-{terrain_map.group_id}-map-{terrain_map.map_id}.json"
            )
            target = temporary / relative_path
            detail_payload = {
                "schema_version": TERRAIN_SEAM_AUDIT_SCHEMA_VERSION,
                "analysis_sha256": terrain_map.analysis_sha256,
                "map": terrain_map.as_dict(),
            }
            target.write_text(
                json.dumps(
                    detail_payload,
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n",
                encoding="ascii",
                newline="\n",
            )
            map_detail_paths.append(relative_path)
            map_artifacts[(terrain_map.group_id, terrain_map.map_id)] = {
                "detail_relative_path": relative_path.as_posix(),
                "detail_file_sha256": _sha256_file(target),
            }
        candidates = tuple(
            sorted(
                (
                    item
                    for item in report.maps
                    if (item.tile_width is not None and item.tile_height is not None)
                    and (item.seams or item.corners)
                ),
                key=lambda item: (
                    -item.summary["diagnostic_score"],
                    item.group_id,
                    item.map_id,
                ),
            )
        )
        selected = candidates if heatmap_limit == -1 else candidates[:heatmap_limit]
        heatmap_records: list[dict[str, object]] = []
        heatmap_paths: list[Path] = []
        if selected:
            heatmap_root = temporary / "heatmaps"
            heatmap_root.mkdir()
            for terrain_map in selected:
                relative_path = Path("heatmaps") / (
                    f"group-{terrain_map.group_id}-map-{terrain_map.map_id}.png"
                )
                target = temporary / relative_path
                width, height = write_terrain_seam_heatmap(
                    terrain_map,
                    target,
                    scale=heatmap_scale,
                )
                heatmap_paths.append(relative_path)
                heatmap_records.append(
                    {
                        "map_group_id": terrain_map.group_id,
                        "map_id": terrain_map.map_id,
                        "relative_path": relative_path.as_posix(),
                        "sha256": _sha256_file(target),
                        "width": width,
                        "height": height,
                        "scale": heatmap_scale,
                        "encoding": {
                            "red": "border absolute p95",
                            "green": "gradient-discontinuity absolute p95",
                            "blue": "four-tile corner spread",
                        },
                    }
                )
        payload = report.as_dict(map_artifacts=map_artifacts)
        payload["artifacts"] = {"heatmaps": heatmap_records}
        report_target = temporary / TERRAIN_SEAM_AUDIT_REPORT_FILE_NAME
        report_target.write_text(
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=True,
                indent=2 if pretty else None,
                separators=None if pretty else (",", ":"),
                sort_keys=True,
            )
            + "\n",
            encoding="ascii",
            newline="\n",
        )
        expected_report_sha256 = _sha256_file(report_target)
        os.replace(temporary, destination)
        published = True
        published_report = destination / TERRAIN_SEAM_AUDIT_REPORT_FILE_NAME
        if _sha256_file(published_report) != expected_report_sha256:
            raise TerrainSeamAuditError("published terrain audit report failed verification")
        for artifact in map_artifacts.values():
            target = destination / str(artifact["detail_relative_path"])
            if _sha256_file(target) != artifact["detail_file_sha256"]:
                raise TerrainSeamAuditError(
                    f"published map detail failed verification: "
                    f"{artifact['detail_relative_path']}"
                )
        for record in heatmap_records:
            target = destination / str(record["relative_path"])
            if _sha256_file(target) != record["sha256"]:
                raise TerrainSeamAuditError(
                    f"published heatmap failed verification: {record['relative_path']}"
                )
        return TerrainSeamAuditBundle(
            destination_directory=destination,
            report_path=published_report,
            report_sha256=expected_report_sha256,
            map_detail_paths=tuple(destination / path for path in map_detail_paths),
            heatmap_paths=tuple(destination / path for path in heatmap_paths),
        )
    except Exception:
        if published:
            shutil.rmtree(destination, ignore_errors=True)
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def write_terrain_seam_heatmap(
    terrain_map: TerrainMapSeamAudit,
    destination: str | Path,
    *,
    scale: int = 16,
) -> tuple[int, int]:
    """Write a deterministic tile-grid RGB heatmap and return its pixel dimensions."""

    if not isinstance(terrain_map, TerrainMapSeamAudit):
        raise ValueError("terrain_map must be TerrainMapSeamAudit")
    if isinstance(scale, bool) or not isinstance(scale, int) or not 1 <= scale <= 64:
        raise ValueError("scale must be between 1 and 64")
    width_cells = max(1, terrain_map.width_tiles * 2 - 1)
    height_cells = max(1, terrain_map.height_tiles * 2 - 1)
    cells = [[(0, 0, 0) for _ in range(width_cells)] for _ in range(height_cells)]
    present_tiles = {(item.tile_x, item.tile_y) for item in terrain_map.tiles}
    for tile_x, tile_y in present_tiles:
        cells[tile_y * 2][tile_x * 2] = (20, 20, 20)
    for seam in terrain_map.seams:
        first_x, first_y = seam.first_tile
        if seam.axis == "x":
            cell_x, cell_y = first_x * 2 + 1, first_y * 2
        else:
            cell_x, cell_y = first_x * 2, first_y * 2 + 1
        cells[cell_y][cell_x] = (
            _byte(seam.border_delta.absolute_p95),
            _byte(seam.gradient_discontinuity.absolute_p95),
            0,
        )
    for corner in terrain_map.corners:
        cell_x = corner.junction_x * 2 - 1
        cell_y = corner.junction_y * 2 - 1
        red, green, _ = cells[cell_y][cell_x]
        cells[cell_y][cell_x] = (red, green, _byte(corner.spread))

    width = width_cells * scale
    height = height_cells * scale
    rows: list[bytes] = []
    for output_y in range(height):
        source_y = height_cells - 1 - output_y // scale
        row = bytearray()
        for red, green, blue in cells[source_y]:
            row.extend((red, green, blue) * scale)
        rows.append(bytes(row))
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(f"heatmap already exists: {target}")
    target.write_bytes(_encode_rgb_png(width, height, rows))
    return width, height




__all__ = ["write_terrain_seam_audit_bundle", "write_terrain_seam_heatmap"]
