# Sustained depth-contour experiment

Extension 1.6.9 adds an optional screen-space filter for one-pixel depth cracks. It is an
experimental contour policy, not a terrain repair and not a replacement for the reviewed 1.6.8
world/UI composite boundary.

## Motivation

The existing fixed-pixel contour pass reconstructs inverse eye depth for the foreground pixel and
its four cardinal neighbours. A foreground curvature response above the configured edge threshold
produces a contour. That deliberately detects real silhouettes and contact seams, but it also treats
a one-pixel recessed strip as an edge when the depth returns to the foreground surface immediately
behind the strip.

The sustained mode asks a second question: does the foreground-to-background drop continue for one
more screen pixel in the same direction? A transient one-pixel return is rejected; a persistent
background remains eligible.

## Modes

The reviewed default remains `legacy`:

- five depth samples per foreground fragment: center plus the first cardinal ring;
- the original foreground-curvature test;
- no second-ring fetches in ordinary rendering.

The optional `sustained` mode adds the second cardinal ring. For each axis, the first-ring side with
the larger foreground-relative depth drop owns the support test. Support from the opposite side or
the perpendicular axis cannot rescue a transient crack. A contour is accepted only when both the
axis response and its same-direction support exceed their independently configured thresholds.

The shader exposes four diagnostic views in addition to ordinary rendering:

- `response`: heatmap of the original curvature response;
- `sustained-response`: curvature retained by same-direction support;
- `support`: heatmap of sustained same-direction support; and
- `rejected`: magenta pixels that pass the original response test but fail sustained support.

Diagnostics are intentionally visual and should be used only in a disposable graphics session.
They do not classify pixels as terrain.

## Live-control ABI

Graphics Control schema 2 retains the 256-byte mapping and all existing field offsets through
`feature_outline_width`. It consumes previously reserved bytes for:

- `sustained_edge_threshold`;
- `depth_contour_mode`; and
- `depth_contour_debug_mode`.

Schema-1 live mappings are rejected rather than misread. Saved schema-1 Graphics Lab presets remain
loadable and receive the legacy contour mode, no diagnostic view, and the reviewed `0.055` support
threshold. New schema-2 presets must state every contour field.

The graphics status producer records the active contour mode, diagnostic mode, ordinary threshold,
sustained threshold, parameter revision, and whether depth contours are enabled. This binds frame
and performance evidence to the exact experimental policy that produced it.

## Native evaluator and fixtures

The pure evaluator and shader use this neighbour order:

```text
0 right1   1 left1   2 up1   3 down1
4 right2   5 left2   6 up2   7 down2
```

Native fixtures cover:

- a continuous surface;
- infinite- and finite-depth one-pixel recessed cracks;
- persistent infinite and finite-depth backgrounds;
- a one-pixel-wide foreground feature;
- perpendicular-axis and opposite-side support rejection;
- a shallow continuous slope;
- an abrupt sustained slope;
- missing second-ring data;
- background-side rejection; and
- exact legacy-wrapper behavior.

The original depth and scene-color textures remain nearest-filtered. The experiment does not blur
depth or color, raise the global threshold, mutate terrain data, or introduce CPU readback.

## Performance comparison

Compare `legacy` and `sustained` under the same verified client, asset profile, renderer settings,
zone, camera pose, resolution, and software/hardware backend. Record at minimum:

- graphics status, including the live-control block and frame-timing ring;
- performance telemetry frame intervals and pipeline gaps;
- viewport and OpenGL/GLSL identity;
- a screenshot of ordinary output; and
- the `rejected` diagnostic view for the same camera pose.

The sustained path adds the second cardinal ring only when sustained mode or a support-dependent
diagnostic is active. Performance acceptance must be based on measured frame behavior, especially
under the reviewed LLVMpipe reference profile, rather than assuming the additional texture samples
are free.

## Deliberate boundary

This filter can suppress a narrow depth-buffer discontinuity. It cannot prove that a contour is a
terrain-tile seam, and it will retain any discontinuity that persists for two pixels. Terrain draw
provenance, depth-owner-aligned semantic metadata, normal reconciliation, material-alpha repair, and
render-only geometry stitching remain separate later stages selected from the terrain audit and
live evidence.

The existing 1.6.8 publication and launch scripts remain sealed to their reviewed DLL hashes. A
1.6.9 player-facing package requires a separately built, probed, live-reviewed, and hash-pinned
artifact after this experiment converges.
