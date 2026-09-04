# Terrain trace analysis

`python -m shadowbane_lab.diagnostics.terrain_trace_analysis <local-trace.json>`
turns a saved 1.6.12 trace into a deterministic attribution report. It does not
request another capture or alter the input file.
The installed command is `shadowbane-terrain-trace-analysis <local-trace.json>`.
Exit status is 0 for attributed draws, 2 for a profile/evidence conflict, and 1
for an invalid trace or unsupported build. No game input or live attachment occurs.

The first reviewed profile is intentionally exact: patched executable SHA-256
`a9a59004...`, generic indexed-triangle submitter RVA `0x1a0765`, and return RVAs
`0x4f1772` / `0x4f1864` inside the statically identified
`ArcShaderCustomTexturedTerrain` draw method. The analyzer identifies base and
mask-blended terrain passes only when their submission and fixed-function states
agree with that profile. Unknown builds, missing roles and contradictory state
fail closed.
The saved trace identity is checked for internal consistency and against the
reviewed executable profile; offline analysis does not independently authenticate
the original running process.

The report groups index counts, render state, texture state and texture matrices.
It also answers whether every observed layer mask used edge clamping and linear
magnification. Reported bindings remain context-local OpenGL names, not cache or
archive resource IDs. Therefore the report never authorizes a repair by itself;
the remaining boundary is binding-to-cache attribution and inspection of the
neighboring mask data.

The first live capture attributed 54 terrain draws: 25 base passes and 29 masked
layers. All 29 observed masks used edge clamp. The capture interval was complete,
but one otherwise unsafe submission was not queried and texture units 4-7 were
outside the bounded observer. A single visually disturbed water frame occurred
during collection and immediately cleared. Live-control sequences were unchanged;
the transient visual disturbance remains a known observer concern, not proof that
every GL state was preserved. Do not use trace timings as a frame-performance benchmark.
