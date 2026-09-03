# Terrain material snapshot

`python -m shadowbane_lab.diagnostics.terrain_material_snapshot` captures one
bounded visible terrain-shader sequence from the exact reviewed 1.6.13 client.
It connects a rendered terrain source to its base, color-layer, source-mask, and
generated GPU-mask texture objects without guessing ownership from context-local
OpenGL names.

The collector requires an exact PID and process-creation FILETIME, the reviewed
patched executable and extension hashes, the four installed terrain-refresh
bytes, the complete terrain draw-entry signature, and the expected
`ArcShaderCustomTexturedTerrain` and `ArcColorTexture` vtables. Unknown or drifted
targets fail before evidence is published.

The observer uses the supervised Windows debugger transport from the terrain
branch-hit tool. All four hardware breakpoint registers point at the single
reviewed shader entry. It retains each source object once and stops when that
sequence wraps, or after 64 sources / 128 hit events. The worker clears debug
registers and exits; the parent verifies the exact process lifetime, signatures,
and absence of a debugger before publishing the JSON.

The snapshot reads only fixed-size objects and bounded pointer vectors. It does
not scan memory, read texture pixels, invoke client code, submit rendering work,
write process memory, mutate caches, or inject game input. Reported archive
tokens follow the verified in-memory `(resource, group)` to archive
`(group, resource)` order. Zero tokens remain explicitly generated or
unattributed. GPU bindings remain context-local identifiers.

This is material-ownership evidence, not pixel attribution. A result can prove
which base and mask objects participate in the visible terrain frame and whether
the client marked their four neighbor directions complete; it cannot identify
which screen pixel belongs to a source or authorize archive mutation.
