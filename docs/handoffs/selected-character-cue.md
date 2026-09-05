# Selected-character cue — active implementation

Base: `14d117e8c5194c6dff55dac608b2d3f683187d31` (owner-pinned).
Branch: `codex/selected-character-cue`; initial PR destination:
`codex/navigation-inspector`, dependent on PR #27. The native lifecycle/runtime
hardening developer owns combined integration. This branch must not deploy the
shared client/VM or merge main. Navigation acceptance is retained, not reopened.

## Current work

- [x] Isolate the pinned source in a separate worktree.
- [x] Implement verified selection/render ownership, depth-writing silhouette and direction cue.
- [x] Integrate settings, context-switch cleanup, regression tests and package wiring.
- [ ] Verify both native profiles and the committed package.
- [ ] Reconcile with the integration owner's candidate and verify combined source.
- [ ] Provide one consolidated live acceptance procedure and exact source/package IDs.

This is an implementation record, not a feature-completion claim.

## Ownership evidence

Inspected the existing private updated official client in place. SHA-256:
`feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff`.
No binary is committed. Addresses below are RVAs, preferred base `0x400000`.

- ArcCharacter's render interface is its `+0x44` subobject. Routine
  `0x78AE0` subtracts `0x44` to compare with the local ArcCharacter. It loads
  `[interface+0x7C]`, hence `[character+0xC0]`, into EDI and passes it as ECX
  to thunk `0x269E0` at `0x78C66`.
- That thunk enters `0x1CB100`. It assigns this render object to the pooled
  ArcCharacterRenderWrapper's `+0x1C` at `0x1CB16A`. It recursively queues
  render-object children from the pointer vector `[render+0x3C, render+0x40)`.
- RTTI identifies wrapper vtable `0x1149ED0`; virtual render slot `+4`
  is thunk `0x26D91`, entering `0x1C8A90`. This reads wrapper `+0x1C`
  and calls the existing renderer through thunk `0xFFB0`.
- Main scene queue drain `0x79C730` calls each queued wrapper's virtual `+4`.

This establishes a structural ownership path, unlike draw-class, texture,
distance or transformed-position matching. Runtime guards still need to verify
the exact executable, code and stable pointers. Same-address reuse must also
check the existing object type/UUID fields and selection lifetime.

## Intended presentation

Highlight visible character coverage only; obstacles hide it. Occlusion does not
make an in-view character off-screen. A separately projected direction indicator
chooses the shortest horizontal camera turn, retaining its side near the exactly
behind-camera tie. Appearance and enable settings belong in Graphics Lab.

Implemented depth-change silhouette capture around the owned render wrapper.
The original render function is called exactly once. GPU copies before/after the
owned draw accumulate a mask; exact comparison with final depth rejects later
occluders. The real OpenGL regression checks visible coverage, edge halo, later
occlusion, state restoration and resource recreation. This is a character mask,
not a ring, bounding box, geometry-distance guess or position marker.

Coverage of visible materials that do not write depth remains an explicit live
question. Such pixels cannot be attributed by this method. Do not describe that
coverage as verified, or call the complete requested feature delivered until the
integration owner resolves that requirement in the combined candidate.

Shared changes will be limited to renderer connections, startup/cleanup, Graphics
Lab tab connection and CMake. The particles developer is extracting the existing
navigation GL guard; coordinate reuse rather than introducing a second guard.


## Integration surface and resource behavior

- `cel_shading.cpp`: begin at the verified main clear, composite before navigation
  and UI, invalidate after a missing boundary, initialize/stop the optional cue.
- `selected_cue_runtime.cpp`: verified wrapper vtable slot; existing import-slot
  replacement utility for `wglMakeCurrent` (reviewed import RVA `0x16B08A8`).
  Releases GL resources before the owning context is unbound or switched. Disable
  releases resources on the next scene. Process teardown also destroys its context.
- Integration owner must call `ReleaseSelectedCueContext` on the render thread
  before any newly introduced independent shutdown/context-destruction path.
  Baseline startup has rollback and process teardown, not a general render-thread
  shutdown dispatcher. Do not invoke GL deletion from an unrelated worker context.
- Cue controls use an exact PID/creation-time mapping, leaving GraphicsControlV2
  unchanged. The mapping is absent in diagnostics-only packages.
- `effects.h`, `effects_attachment.cpp`, `scene_draw.h`, `scene_draw.cpp` are shared
  verbatim from particles checkpoint `5957bf9e033301bb31244e5b320378686809cfbb`.
  Do not compile a second copy when combining the branches.
- CMake and `build_navigation_inspector_package.py` include/verify the real DLL,
  source distribution, wheel, installed Graphics Lab Selection tab and both profiles.

Resource bounds: at most 128 owned render nodes, 3840x2160 pixels, three textures
(two depth24, one RGBA32F mask), one FBO and two programs. Multisample or non-default
framebuffers, unavailable GL facilities, invalid observations or unknown code
fail closed with Graphics Lab diagnostics. The scene camera is authoritative;
no synthetic camera is used. The depth-copy cost needs measurement in the
combined client; no performance acceptance is claimed from the test context.

## Use and consolidated acceptance

Use the integration owner's prepared full-profile client package; this branch
must not deploy the shared VM independently. Launch the installed
`shadowbane-graphics-lab` entry point, choose the exact connected client, open
**Selection**, enable the cue and press **Apply to selected client**. Color,
opacity, glow radius, arrow size and vertical placement are configurable. Saved
appearance is local; reconnecting requires explicit enable/apply. A cleared
selection or missing observation removes the cue.

One consolidated pass after combined-source/package verification:

1. Select two different visible characters, switch rapidly, clear selection,
   and revisit a despawned/replaced target. Only the current character may glow.
2. Turn the camera through front, viewport edges and directly behind. The arrow
   must choose the shortest horizontal turn and stay stable around the rear tie.
3. Put the selected character behind an obstacle while it remains in view.
   The obstacle hides the glow and does not itself trigger an off-screen arrow.
4. Check body, clothing, alpha-cutout edges and visible translucent equipment.
   Record any missing non-depth-writing silhouette coverage as unresolved.
5. Change settings, disable/re-enable, resize, change scenes and reconnect.
   Check cleanup/identity status and performance while preserving the already
   accepted navigation, obstacle traversal and rune-hunt behavior.

Next todo: exact committed package validation, then reconcile the lifecycle
owner's combined candidate and resolve the material-coverage/performance questions.
