# Renderer scene-boundary recovery

## 2026-09-02: 1.6.8 ordering failure

The live aggregate journal accepted a composite at draw 11, but recorded the last
world draw at 3440 and 3417 late world draws out of 3426 classified world draws.
The controls sequence was acknowledged without an error. Successful lifetime
composite/capture counters do not prove that the latest frame contained the world.
These are classifier counts, not semantic character identifications.

The old rule allowed any orthographic or planar candidate to consume the frame
once a depth draw armed it. It did not establish completion of the main world pass.
Do not restore that rule, use draw-count/distance thresholds, add per-draw copies,
or move the composite to present (which would process UI).

## Reviewed native ownership

Offline source: exact executable SHA-256
`55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc`.
The sealed graphics bootstrap identity is
`a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8`;
it must independently pass the same mapped-code check before using this mapping.
The preferred PE image base is `0x400000`. Addresses below are RVAs.

- `ArcWindowGame::Display`: `[0x797AD0, 0x798445)`, 2421 bytes.
- Its complete normalized SHA-256 is
  `779b83ea15ec6892a332fc2d9cc8308e4c548918cba8091057ee049099dd5be4`.
- The 90 original PE HIGHLOW relocation offsets are enumerated in
  `reviewed_scene_boundary.h`; subtract the load delta before hashing.
- Main color/depth clear: `glClear` at `0x798109`, return `0x79810F`,
  through IAT `0x16B0990`. Mask is `0x4100` or `0x4500`.
- Sky and the collected world renderables follow that clear. The render queue is
  drained through `0x79C730`; the island stage through `0x203EB0` completes next.
- Client instrumentation labels these stages `ArcWindowGame:Display:clear`,
  `:sky`, `:island`, and `:done3D`. The last marker is submitted at `0x7981D1`.
- The dedicated UI projection setup calls `glMatrixMode(GL_PROJECTION)` at
  `0x7981F9`, return `0x7981FB`, through the register loaded from IAT `0x16B08EC`.
  This is after `done3D`, before matrix push/load/ortho and any subsequent UI draw.
- The UI projection is installed by `glOrtho` at `0x798239`. Screen overlays,
  character labels, child windows and console follow. A later projection restore
  is not a second boundary. Final routine work after UI is screenshot handling.

Preliminary scene/texture work occurs before the main clear, so "some world has
drawn" is explicitly not evidence that the final scene is ready. Hooking the
existing imported API call sites avoids overwriting instructions, private-client
detours, stack walks, and per-draw GL synchronization for phase detection.

## Validation and delivery status

The native verifier checks exact code, load deltas in both directions, and rejects
one-bit changes at every byte of the routine. The optional frozen-client probe
reads bytes only; it never loads or executes the client. No client executable or
machine-specific capture is committed.

Next: wire main-clear and verified pre-UI signals into the renderer, extend the
ordering/composite outcome journal and regression suite, then build both profiles.
Live VM verification and visual acceptance remain required before calling the
renderer recovered. Neither VM has been changed by this work.
