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
- [x] Verify both native profiles and the committed package (checkpoint below).
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
feature developer resolves that requirement and verifies the combined candidate.

Shared changes cover renderer connections, startup/cleanup, Graphics Lab tab,
CMake and package wiring. The shared navigation GL guard is reused.
Agreed combined ordering: composite -> selected cue -> particles -> navigation -> UI.


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

Resource bounds: at most 128 owned render nodes, 3840x2160 pixels, four textures
(three depth24, one RGBA32F mask), two FBOs and two programs. Multisample or non-default
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

## Verified package checkpoint

Source `7cc91b30ea4b9de57a43fd7d9f51db3c8d227519` was built from a clean committed
archive by the existing package pipeline. Local package:
`E:/Projects/shadowbane/artifacts/cue-packages/1ced2961/navigation-inspector-acceptance.zip`
SHA-256 `5fdf65c211a05ab9842ff0d854db2d3dc5292c9fd337cec1728dc84738986338`.
Receipt and logs are beside it. Both native profiles: 21 CTests passed, the private
binding test skipped in general CTest and then passed explicitly against the
reviewed client in each profile. Full Python suite, Ruff, sdist/wheel build,
installed entry point and both installed UI panels passed. No VM deployment.

A subsequent focused fix preserves capture-failure diagnostics across successful
indicator drawing and discards masks on the 128-draw budget overflow. Native
checks pass; the checkpoint package above predates that fix and must be rebuilt
as part of the owner's combined package.

Integration owner task: `01a070ce-f816-7b32-8673-904c6f406c7a`, branch
`codex/native-lifecycle-hardening`. Owner has the exact checkpoint, cleanup
contract and ordering. Combined verification is still pending.

Next active todo: resolve material coverage. Remaining: reconcile lifecycle,
verify combined source/package, and consolidate live material/performance checks.

## Material investigation and targeted observation

Static shader dispatch confirms the coverage limitation is a real possible code
path, not only a generic OpenGL concern. The selected render object's `+0xEC`
shader is configured at RVA `0x1CC549` (virtual `+0x14`) and drawn at `0x1CC554`
(virtual `+0x0C`). RTTI identifies ArcShaderGeneric draw RVA `0x4F1E70`, which
conditionally disables depth writes at `0x4F201F`; ArcShaderStaticWithAlpha draw
`0x4F63D0` and ArcShaderStaticNoAlpha draw `0x4F6990` also have conditional depth
write changes (`0x4F6773`, `0x4F6D13`). These are exact-code observations from the
reviewed private executable above.

The missing runtime fact is which shader/material state the selected body's and
clothing's meshes actually use, especially while fading or translucent. Static
code cannot supply those live object values. The integration owner has been sent
this precise evidence request for the combined capture; no intermediate demo
acceptance or repeated navigation proof is requested. The feature developer
retains responsibility for resolving any resulting coverage gap.

Draft review: https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/29

## Latest verified checkpoint and read-only guest evidence

Package source: `4be561f63d8e327df3b3ee4e853ab4bb8fef0e6d` (includes failure and
viewport fixes). Package:
`E:/Projects/shadowbane/artifacts/cue-packages/30e40ddd/navigation-inspector-acceptance.zip`
SHA-256 `63c647fb0c91207e778d7b4432d3303c41e52e3367a2997f58cedc8bc05bb489`.
Full pipeline passed: 1,703 Python tests, 211 subtests, 7 Python skips; Ruff;
both native profile builds with 21 general CTests passing and private binding
verification separately passing in each; sdist/wheel and installed UI checks.
This supersedes the earlier package checkpoint. Documentation-only changes after
this source do not alter the packaged binaries. Combined-owner source is not yet
verified and the material requirement remains open.

The existing navigation guest invocation wrapper was located and used for bounded
read-only process memory inspection. No client deployment, injection, selection
change or movement was performed. Guest PID 5212 ran reviewed official hash
`feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff`.
Current selection vtable RVA `0x1142748` resolves by exact RTTI to `ArcItem`;
the ArcCharacter guard correctly rejects it. A separate local-player reference
snapshot contained 46 render nodes, all opacity 1, with shader vtable RVAs
`0x1149BF4` (Generic), `0x1149C18` (StaticClipMap), `0x1149C3C` (mirrored clip map)
and `0x1149C84` (StaticWithAlpha). This is reference evidence only, not substitute
selected-character binding or proof of translucent/fading coverage.

Task-owned local read-only scripts remain at
`artifacts/selected-character-cue/read-selected-material.ps1` and
`artifacts/selected-character-cue/read-player-material.ps1`. Private analysis tools
remain in that ignored artifact directory; build output remains in ignored
`build/cue-full`. Package receipts preserve their original source and log paths.
The normal main checkout and navigation checkout are not modified by this lane.
The feature worktree is retained for the pending combined-source verification.

## Combined dependency verification and cue lifecycle follow-up

Verified owner source `50ad9e1dd83a67de3bc814a098dc4230b0393299` in an isolated
read-only checkout at `E:/Projects/shadowbane/.worktrees/cue-combined-verification`.
Full package passed: 1,715 Python tests, 223 subtests, 8 skips; Ruff; both native
profiles (23 passing CTests and the private binding check separately passing);
sdist/wheel, entry point, inspector, effects and selection installed UI checks.
Package `E:/Projects/shadowbane/artifacts/cue-combined-packages/5ecad118/navigation-inspector-acceptance.zip`,
SHA-256 `649f670036d427a8854346c24cd5f86b531598a425560b385aa74dc979cc9721`.
Shared source lists, panel disconnects, boundary camera checks and pass ordering
were reviewed. This dependency checkpoint predates the owner's final lifecycle
repairs and does not resolve material coverage.

The subsequent cue lifecycle fix consumes `render_lifetime.h` verbatim from owner
`8961fad07ff00c40b511f5b8f9562669069aad39`. All cue callbacks and public scene
entries lease that same recursive admission domain; Start/Stop use its mutation
lock. Stop drains admitted wrappers and retains original call-through. It advances
a generation so old render-thread selection, direction and mask state cannot be
reused after restart. Each thread releases its old mask on its next cue entry,
before creating new-generation resources.

The cleanup-only `wglMakeCurrent` import hook deliberately remains installed while
the process-pinned extension lives, including while the feature is stopped. It
releases resources on the owning thread before unbind/switch; restart recognizes
and reuses the installed hook without chaining to itself. A stopping worker never
deletes another context's objects. If a render thread makes no subsequent cue or
context call, its bounded GL objects remain with that context until the normal
context/process destruction. Hot unload is not supported or requested. Any new
owner context path bypassing that game import must call `ReleaseSelectedCueContext`
on the owning thread before unbind/destruction. The held-wrapper regression checks
drain, concurrent stop/restart serialization, retained cleanup hook, and owning-thread
release before new-generation reuse. Final combined-source verification must
include this lifecycle follow-up.

## Non-depth-writing mesh coverage follow-up

The current implementation supplements wrapper depth deltas with a narrowly
scoped raw mesh capture in the existing `StrongDrawArrays`/`StrongDrawElements`
hooks. Only the verified selected wrapper admits this capture. When native depth
writes are off, it draws that same driver submission into a private depth target,
retaining native vertex arrays, transforms, textures, programs and alpha testing.
The game character/animation render function is still called exactly once. The
capture cannot modify the client's depth or color attachments. Native GL state is
restored before the original submission proceeds normally.

Nearest owned depth accumulates across material passes. Comparison against final
scene depth permits the owned translucent mesh in front of farther background,
and rejects nearer opaque foreground. Standard source-over and alpha-weighted
additive draws with zero source alpha are excluded; RGB-additive drawing correctly
ignores alpha when the native blend factors do. Native textured alpha-test holes
are preserved. Real GL pixel/state tests cover these cases, including exactly
owned wrapper admission and resource/lifecycle regressions.

This closes the tested array/element mesh coverage gap, but does not claim all
native transparency is solved. The particles developer's real GL probe confirms
that pre-UI composition cannot reconstruct transmission through a native
translucent foreground surface from final depth, regardless of that surface's
depth-write mode. Native sorting/interleaving remains shared integration work.
The supplemental capture also rejects active native sample queries, stencil-test
paths and nonzero viewport origins to avoid altering their semantics; display-list
or immediate-only non-depth-writing meshes are not covered by this seam. These
are explicit unresolved coverage cases for the final candidate, not substitutes
for the requested character silhouette. The current scene guard still rejects
unreviewed active ARB program paths. No live acceptance or deployment is claimed.

The integration owner approved focused work in the two existing draw hooks; the
particles developer confirmed no hook conflict. Shared admission and pass order
remain unchanged. Next active todo: resolve native foreground transparency with
the shared queue work, then verify the owner-pinned combined candidate/package.
