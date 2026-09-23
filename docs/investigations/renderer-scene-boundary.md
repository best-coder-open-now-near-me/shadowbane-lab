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

Implemented: the main clear owns projection/viewport and invalidates preliminary
depth work. Only the exact reviewed pre-UI call can consume a scene. A second clear,
missing main scene, invalid projection, changed context, or unknown code/build
cannot trigger a guessed capture. Unknown builds keep original draw submission.
After the verified UI signal, later perspective draws remain unmodified and are
still counted, so diagnostics do not hide ordering failures. No extra framebuffer
copy, readback, draw-count threshold, or per-draw phase query was introduced.

`boundary_count` now records verified phase ownership, independently of GPU success.
`composite_succeeded` is the latest-frame result, not a lifetime counter. The journal
also reports `boundary_mapping_verified`, `main_scene_start_count`,
`main_scene_world_draw_count`, and `main_scene_invalidated`. Boundary ordinals refer
to the next draw because this signal is between draws (possibly draw_count + 1
when UI is hidden). Existing capture policies remain readable. Planar overlays
are subtracted from scene-world counts, matching the native producer.

Implementation validation: both native profiles built and passed 12/12 tests each;
the complete Python suite passed 1329 tests, with 6 skips and 211 subtests. Coverage
includes the long early-overlay regression, duplicate/missing/invalidated main
scenes, code drift, relocation, failed GPU composites, latest-frame success, and
late draws immediately after the between-draw boundary.

Release artifacts: native version 1.6.9.0, built with MSVC Win32 Release.
The graphics publish/launch scripts pin the full artifact; the diagnostics
publisher pins the separate diagnostics-only artifact. These pins are verified
against the built files, not copied from an earlier release.

- Full renderer: 281088 bytes, SHA-256
  `51fa86429fa65f1a1bbef7d384acd455bd06fcbad9b264bca453d504f01d9327`.
- Diagnostics only: 204288 bytes, SHA-256
  `0290a809e5a550af863d64348b144b677009b2f9ee60fea6f6866822887518d5`.
- Renderer implementation checkpoint: `37218ca`.

Release validation repeated both 12-test native profiles and the full Python
suite (1329 passed, 6 skipped, 211 subtests), plus lint and Python wheel packaging.
All three publication/launch scripts parse without execution and match their
built DLL hashes. Offline bootstrap authoring with the new DLL reproduces the
expected `a9a59004` executable and leaves the reviewed scene routine unchanged.

Next: publish 1.6.9 to the testing VM only when authorized, then visually verify
the affected scene (including a second launch and a revisit). Required journal:
`boundary_mapping_verified=true`, `main_scene_start_count=1`,
`main_scene_invalidated=false`, `boundary_count=1`,
`composite_succeeded=true`, `late_world_draw_count=0`, and
`last_world_draw_ordinal < accepted_boundary_draw_ordinal`.
Check character/prop outlines and ground seams, untouched text/UI, live baseline
reset, and frame timings. Success counters alone are not acceptance.
Live VM verification and visual acceptance remain required before calling the
renderer recovered. Neither VM has been changed by this work.

## 2026-09-04: navigation camera ownership

The exact frozen executable above was inspected again while diagnosing zero
accepted camera samples in the navigation inspector. The render queue routine
`[0x79C730, 0x79C7FD)` calls `glPushMatrix` at `0x79C738`, dispatches its entries,
and calls `glPopMatrix` at `0x79C7F1`. Per-draw sampling restricted to model-view
stack depth one therefore misses the nested world queue. Owner-authorized,
in-place analysis of two historical renderer traces found 40 and 54 attributed
terrain draws, each using one consistent model-view matrix; unrelated object
matrices are numerous and cannot establish camera ownership.

The full renderer now reads the outer model-view at the existing reviewed main
clear and requires the byte-identical restored view, projection, and viewport at
the existing reviewed pre-UI boundary in the same context. Both reads require
stack depth one and numeric camera validation. Only a nonempty, single, valid main
scene can publish the result. No new client detours, draw-count heuristic, matrix
address guesses, or relaxed stack rule are used. Historical captures support the
investigation only; world-trail alignment remains a current-client visual gate.
