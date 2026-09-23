# Terrain seam audit

The terrain seam audit is a read-only evidence pass over `TerrainAlpha.cache`. It compares the
stored byte samples on both sides of every available tile border and at every complete four-tile
junction. It does not alter a cache, normalize a material layer, classify a rendering defect, or
change the native renderer.

The audit is deliberately separate from terrain-aware contour suppression and terrain repair. Its
job is to determine whether a visible line correlates with source height/material bytes before a
renderer or asset developer chooses a remedy.

## Run the audit

Install the project with its normal test or editable environment, then run:

```powershell
shadowbane-terrain-audit `
  'C:\Wonderbane\cache\TerrainAlpha.cache' `
  'C:\ShadowbaneLab\audits\terrain-2026-09-02' `
  --zone-cache 'C:\Wonderbane\cache\CZone.cache'
```

The destination is create-only. The command stages the complete bundle in a temporary sibling and
publishes it with one directory rename. Existing destinations are refused.

Useful options:

```text
--heatmap-limit 12   highest-scoring maps (default)
--heatmap-limit -1   every analysable map
--heatmap-limit 0    no heatmaps
--heatmap-scale 16   pixels per tile-grid cell, from 1 through 64
--compact            compact the small top-level index
```

`CZone.cache` is optional. Without it, every map remains `unclassified`. With it, only a template
that contains each resource of every referenced map exactly once is trusted. The first complete map
in that validated template is labelled `height`; later complete maps are labelled `material`.
A partial map, duplicate resource key, or incomplete source map invalidates role assignment for the
entire template and is recorded as a correlation issue. This prevents an uncertain earlier layer
from shifting a later map into the wrong role.

## Bundle layout

```text
terrain-2026-09-02/
├── terrain-seam-audit.json
├── maps/
│   ├── group-12-map-1.json
│   ├── group-12-map-2.json
│   └── ...
└── heatmaps/
    ├── group-12-map-1.png
    └── ...
```

`terrain-seam-audit.json` is a compact discovery index. It contains:

- exact source archive paths, sizes, directory metadata, and SHA-256 identities;
- a timestamp-independent `analysis_sha256`;
- map status, dimensions, roles, validated zone references, and summaries;
- the 25 highest-scoring seams and four-tile junctions;
- relative paths plus SHA-256 identities for every map-detail JSON and generated heatmap; and
- bounded CZone correlation issues.

Each file under `maps/` contains the detailed evidence for one `(group_id, map_id)`:

- exact tile coordinates and cache entry identity;
- source payload SHA-256 for every decoded tile;
- every available x- and y-axis neighbour comparison;
- inward-gradient summaries from each side;
- four-tile corner values and edge deltas; and
- missing-tile or structural issues.

The top-level schema is `schemas/terrain-seam-audit-v1.schema.json`. Per-map detail files use
`schemas/terrain-seam-map-v1.schema.json`.

## Metric definitions

For an x-axis seam, the first tile is left and the second tile is right. For a y-axis seam, the
first tile is lower and the second tile is upper. Coordinates remain in the stored TerrainAlpha
map convention.

For each position along the shared border:

```text
border_delta = second_edge - first_edge

first_inward_gradient = first_edge - first_interior_neighbour
second_inward_gradient = second_edge - second_interior_neighbour

gradient_discontinuity =
    first_inward_gradient + second_inward_gradient
```

The two inward gradients point toward the seam from opposite sides. Equal-and-opposite inward
values therefore produce a zero gradient discontinuity, which is compatible with a continuing
linear slope. This is a byte-space diagnostic only; it does not prove how the client constructs or
samples terrain geometry.

Each difference series reports:

```text
sample count
non-zero count
signed minimum / maximum / mean
absolute maximum / mean / RMS
absolute p50 / p95 (nearest-rank)
```

A seam's `diagnostic_score` is the larger of border absolute p95 and gradient-discontinuity absolute
p95. A map's score also considers four-tile corner spread. The score ranks evidence for review; it
is not a claim that a seam is erroneous.

At a four-tile junction, the audit reads the four touching corner samples and reports their values,
maximum-minus-minimum spread, mean, and the signed lower/upper x and left/right y pair deltas.

## Heatmaps

Heatmaps use a compact tile-grid representation instead of reproducing every 128-by-128 source
sample. Tile centers occupy even grid cells, seams occupy the cells between them, and four-tile
junctions occupy the diagonal cells. Stored y coordinates are flipped only for PNG presentation so
higher tile y appears toward the top.

The deterministic RGB encoding is:

```text
red   = seam border absolute p95
green = seam gradient-discontinuity absolute p95
blue  = four-tile corner spread
```

Values are clamped to the byte range. PNGs are written by a small standard-library encoder with no
image-library dependency or embedded timestamps.

## Safety and interpretation

The audit opens both archives read-only, hashes them before use, hashes them again after all mapped
reads finish, and fails if either identity changed. Source links and Windows reparse points are
rejected.

Do not treat the report as permission to mutate terrain data. In particular:

- a height-border delta can represent a real source discontinuity, an expected sampling interval,
  or a client-side stitching convention not yet recovered;
- a gradient mismatch does not prove a normal discontinuity because normals may be generated by a
  different neighbourhood or stored elsewhere;
- material maps are reported independently and are never normalized or assumed to sum to one;
- matching source borders do not rule out UV filtering, mip, precision, LOD, or draw-boundary
  defects; and
- height data may overlap local movement/collision ownership, so visual repair must not begin from
  this report alone.

The intended convergence path is:

```text
read-only terrain audit
    + live sustained-contour evidence
    + reviewed terrain draw provenance
        -> evidence-selected renderer or asset repair
```
