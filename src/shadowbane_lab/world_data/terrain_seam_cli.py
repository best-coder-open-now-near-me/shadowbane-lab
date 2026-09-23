"""Command-line entry point for the read-only TerrainAlpha seam audit."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from shadowbane_lab.world_data.terrain_seams import (
    TerrainSeamAuditError,
    audit_terrain_archive,
    write_terrain_seam_audit_bundle,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shadowbane-terrain-audit",
        description=(
            "Audit TerrainAlpha tile borders, inward gradients, and four-tile junctions "
            "without modifying client archives."
        ),
    )
    parser.add_argument("terrain_alpha_cache", type=Path)
    parser.add_argument("destination_directory", type=Path)
    parser.add_argument(
        "--zone-cache",
        type=Path,
        help="optional CZone.cache used only to label complete maps as height/material layers",
    )
    parser.add_argument(
        "--heatmap-limit",
        type=int,
        default=12,
        help="number of highest-scoring map heatmaps; -1 writes all and 0 writes none",
    )
    parser.add_argument(
        "--heatmap-scale",
        type=int,
        default=16,
        help="nearest-neighbour pixel scale for each tile-grid heatmap cell (1-64)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="write compact rather than indented JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        report = audit_terrain_archive(
            arguments.terrain_alpha_cache,
            zone_cache_path=arguments.zone_cache,
        )
        bundle = write_terrain_seam_audit_bundle(
            report,
            arguments.destination_directory,
            heatmap_limit=arguments.heatmap_limit,
            heatmap_scale=arguments.heatmap_scale,
            pretty=not arguments.compact,
        )
    except (OSError, TerrainSeamAuditError, ValueError) as exc:
        print(f"terrain seam audit failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "destination_directory": str(bundle.destination_directory),
                "report": str(bundle.report_path),
                "report_sha256": bundle.report_sha256,
                "map_count": len(report.maps),
                "seam_count": report.summary["seam_count"],
                "corner_count": report.summary["corner_count"],
                "map_detail_count": len(bundle.map_detail_paths),
                "heatmap_count": len(bundle.heatmap_paths),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
