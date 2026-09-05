# Selected-character cue â€” active implementation

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

## Resource-cost and query/stencil checks

`wonderbane_extension_selected_cue_gpu_test.exe --cost` runs the actual production
mask functions with 46 native array submissions per frame, matching the observed
player node count. Four-frame host-context measurements (including initialization
and native mesh submission) averaged 6.338 ms at 640x480 and 9.566 ms at 1920x1080.
These are bounded developer measurements, not VM/live-game performance acceptance.
The exact primitive geometry is a test fixture; no offline viewer is delivered.
GPU regressions also verify stencil state remains unchanged and an active native
samples query receives zero samples from rejected supplemental capture.

## Cost-reduced whole-character capture

The current raw array/element path accumulates nearest owned geometry into one
frame-long private depth target. Its whole-character glow reads that target once
at composition; it no longer performs a full-frame copy and mask pass per normal
wrapper. Immediate/display-list geometry retains the original depth-delta coverage
through a lazy baseline at the existing `StrongBegin`, `StrongCallList` and
`StrongCallLists` hooks. Mixed raw/legacy nodes are tested in both orders and still
form one whole-character mask. Depth prepass plus equal-depth material passes are
also covered; native stencil/query/logic operations are never blindly replayed.

Normal mesh storage is two depth textures (8 nominal bytes/pixel), 15.820 MiB at
1080p. Legacy baseline and accumulated-mask textures are allocated only when used;
R32F is used where supported, with the original RGBA32F compatibility allocation
otherwise. Maximum fallback storage remains bounded at 28 nominal bytes/pixel.
Allocation/release/recreation assertions verify the normal path does not retain
fallback allocations after cleanup.

Same 46-node/four-frame host cost check now averages 2.052 ms at 640x480 and
2.653 ms at 1080p, including initialization. Compared with the earlier 9.566 ms
1080p result, this reduces measured normal-mesh cost by about 72%. This is still
host test-context evidence, not live VM performance certification. Full native
build and all 21 general CTests pass; private binding code remains unchanged.

Owner shared-context source `44d926166220a0e5254ec90e6c21914d273270b0` was separately
built in the isolated verification checkout. Its cue GPU/runtime/math and shared
context tests pass, and the explicit reviewed-client binding verifier passes.
The shared context hook is now owned by `scene_context.cpp`, independent of cue
startup, and correctly retains owning-thread release before unbind. The new cost
changes still need inclusion and verification in the owner's next exact source.
The required native-transparency gate is red; no final package or completed
feature is claimed from this checkpoint.

## Required cue foreground-transparency gate

`wonderbane_extension_selected_cue_native_transparency` now runs the production
GPU path as a required CTest. Its reference renders the same cue before a native
50%-red foreground draw, and compares the current pre-UI candidate against it.
Measured reference RGB is `(131,16,19)`; current late composition yields
`(116,31,37)` with native depth writes off and `(127,0,0)` with them on. Both cases
fail. This independently prevents a cue package from being certified merely
because the particles transparency test is fixed. It is not disabled or marked
expected-success. The existing package pipeline will stop on this regression.

The cost-reduced capture and lifecycle work are published, but correct native
foreground transmission remains unfinished shared renderer integration. The
feature is not ready for manual acceptance or a completion claim.

## Combined source verification and steady-frame cost

The lane independently built exact owner source
`c2f9c997870760bb1a347bd3a6006199038265b8` in its own clean detached verification
worktree. The 30-test native suite had 27 passes, two no-argument binding skips,
and the required effects native-transparency failure in both depth modes. The
cue private-client binding test was then supplied the reviewed executable and
passed. Cue GPU, runtime, identity/math, shared context, sky and navigation checks
passed. This source includes cue `8967438`, but predates the additional required
cue-transparency test at `0613b97`; its ordinary cue GPU pass is not evidence of
correct native transparency. No certifiable package was produced at this pin.

The original four-frame cost sample on that combined source measured 2.747 ms at
640x480 and 4.362 ms at 1080p, illustrating host-load variance relative to earlier
samples. The cost mode now reports cold initialization separately, warms three
paired frames, then measures 16 native-only and cue-enabled frames in alternating
order. It reports median, range and nominal texture storage; `glFinish` includes
CPU/GPU synchronization. These are synthetic 46-submission host tests, not live
client frame-time certification or a representative mesh-complexity benchmark.

The updated feature test measured 640x480 enabled median 1.897 ms (1.646â€“2.316 ms),
native-only median 0.069 ms, and cold setup frame 2.654 ms. At 1080p it measured
2.646 ms (2.428â€“2.985 ms), native-only 0.095 ms, and cold frame 3.528 ms. Normal
mask storage remains 15.820 MiB at 1080p. General GPU assertions passed during
this run. Unknown command-line modes now exit 2 instead of silently running the
default test. The native-transparency mode still exits 1 with both documented
pixel mismatches; the harness check of this known failure does not make it pass.

Next active todo is the shared foreground-transmission correction, followed by
verification at the owner's next exact combined source and actual package build.
No certified complete translucent stage was found in the queue investigation;
per-wrapper composition would not preserve the whole-character silhouette.
Both feature and lane-owned verification worktrees are retained for this work.


The required transmission probe now also places native glass behind the selected
character and samples the halo outside the mesh's native depth coverage. Both
background depth modes produce expected/current RGB `(84,122,143)`. Moving all
cue composition before glass instead produces `(142,61,72)` in both modes. The
probe asserts this counterexample is distinct, preventing the foreground-only
fixture from suggesting a wholesale earlier pass is sufficient. Existing two
foreground mismatches remain required failures; the ordinary GPU suite passes.


## Bounded material investigation and optimized multi-draw repair

The integration owner requested continued material/queue investigation and
explicitly authorized this focused coverage repair. No competing present,
context, scene or procedure-resolution hook was introduced.

On the reviewed updated official executable, character draw `1CB700` writes a
cached matrix at `1CBAA5` before shader configuration/draw at `1CC549`/`1CC554`.
Common shader configuration `4EFFE0` updates mesh references and writes its
caller-local draw-description pointer into shader `+10` at `4F003A`. Retaining a
shader pointer for later replay would retain a reference to expired stack data.
Category helper `1C3380` tests opacity against 0.995 and material flags; it does
not provide a spatial depth key. These facts rule out treating game-render or
shader calls as a harmless prepass. They do not prove every possible retained
geometry strategy impossible.

Bounded read-only player-reference observations (not selected-target substitution)
resolved 32 drawable nodes among the 46-node subtree through `ArcSinglePolyMesh`
vtable `11498A0`, `ArcMesh` vtable `114965C`, and active
`CacheCompiledVertexArrays` vtable `11496B4`. Fourteen terminal submitters were
`RenderNormal` (`11495A8`); eighteen were `RenderOptimizedMultiDraw` (`11495C8`).
The latter builds count/index arrays on its stack at `1A07F0`, then calls thunk
`13868`, wrapper `5655C0`, and dynamic procedure slot `16AA038`. That path bypasses
the ordinary `glDrawElements` import. The native initializer at `5645B3` resolves
`glMultiDrawElements` first, then `glMultiDrawElementsEXT` if unavailable.

The existing cue runtime now registers this slot after reviewed binding succeeds,
validates/adopts it on the GL thread at BeginScene, and captures multi-draw
synchronously into the same whole-character mask. It calls the current-context
native procedure with the original stack arrays while they remain valid; nothing
is retained for later replay. Raw mask submission is supplemental; native color
submission remains once. Exact initializer, producer and dispatch code spans are
covered by relocation-normalized seals and every-byte mutation rejection.

Late initialization is retried at the next scene boundary. A foreign pointer is
never replaced. Any pointer drift during a scene discards the whole mask,
including prior nodes. A short metadata lock serializes adoption only; it is not
held over native drawing and does not create a second callback admission domain.
An installation epoch also detects drift/re-adoption while an older callback is
held. That callback retains its locally captured native procedure through return.
Stop uses the shared lifecycle mutation, drains admitted callbacks and restores
by compare/exchange; foreign replacements survive. Call-through remains pinned
for previously loaded hook addresses. Context procedure resolution is strict and
failed observation prevents a partial mask from being presented.

Validation: full extension build succeeds; runtime and GPU cue suites pass.
Runtime cases cover delayed initialization, EXT fallback, unavailable context,
foreign replacement, prior-mask discard, held callback plus concurrent driver
refresh, retained call-through, and Stop/restart while multi-draw is in flight.
Actual WGL multi-draw tests cover both depth-write modes, both primitive halves,
client-array/GL-state restoration and one native color-buffer submission. The
explicit private-client binding test passes with both relocation directions and
every-byte drift rejection on the new spans. The required foreground transmission
regression still fails both foreground depth modes; this repair does not resolve
transmission and is not final package certification.

The lane's ignored read-only scripts `read-player-backend.ps1`,
`read-player-submission.ps1`, `read-player-driver.ps1` and
`read-player-primitive.ps1` remain under `artifacts/selected-character-cue/`.
No client binaries, credentials or raw geometry were exported. The remaining
transmission contract needs either a verified depth-aware integration preserving
native pass ordering, or owned per-fragment transmission/geometry/material data
for all contributing native draws. The inspected shader pointer is not that
contract. Next: owner inclusion and exact combined verification of this repair,
then continue the shared transmission investigation; the package gate stays red.


## Multi-draw combined verification

The lane independently verified exact owner pin
`b713dbf0c5cecf743c441c38472db8568cdbeaf9`, containing feature repair
`d741f04ff0eadd9e2d94901e5d2dd366e3a72a35`, in its own clean detached verification
worktree. GPU/binding sources are identical to the repair; runtime differences
only retain the owner's shared `scene_context` extraction. That reconciliation
was reviewed, including release before context unbind and shared admission.

The full-profile DLL and all native test targets build. The 36-test suite reports
32 passes, two argument-only binding skips, and the two required cue/effects
foreground-transparency failures. Both cue and sky binding tests were then run
with the explicit reviewed private client and passed. Cue held-multi-draw runtime,
actual GPU, shared context, and all sixteen render combinations passed. The
Python cue control/configuration suite passed all 17 tests. Machine-readable
results are retained locally at
`E:/Projects/shadowbane/artifacts/cue-combined-native/b713dbf/lane-verification.xml`.

The multi-draw repair is therefore verified in the combined source. Transmission
and final package certification remain unfinished. The verification checkout is
retained at this exact pin, feature checkout is clean/published, and normal main
checkout remains untouched. Next active todo remains the shared transmission
correction, followed by the final combined package and consolidated acceptance.


## Native multi-draw contributor diagnostics

The owner authorized reusing the existing bounded TerrainTrace for native
optimized submissions, coordinated with particles' transmission-state fields.
The existing hook now reports one `multi_elements` observation before supplemental
mask replay. `count_unit` is explicitly `subdraws`; count is neither summed
indices nor fragment coverage. Private replay never produces another observation.

A read-only helper exposes the renderer's existing thread-local begin/list guard.
Unsafe calls still reach the original native procedure once, but neither query
state nor perform supplemental mask submission; any partial owned mask is
invalidated. A read-only trace-phase predicate allows the same verified dynamic
slot to be adopted for an opt-in frame even with cue disabled or no selected
target. Disabled cue with no active trace does not adopt the slot. Existing
context, epoch, original-call and Stop restoration rules remain in force.
This adds no new hook/lifecycle authority, and is diagnostic submission coverage,
not a retained fragment/transmission implementation. Unavailable/unhooked paths,
query/capacity limits and list-internal state remain outside a completeness claim.

The actual full DLL builds. Four affected native tests pass (cue runtime, trace
full/disabled and shared cel guard), including disabled/no-target capture and
no-opt-in/no-adoption. The 46 existing Python trace-reader/terrain-analysis tests
pass. The root owns inclusion with the enriched trace fields; no shared client
or VM was changed by this lane. The PR is to be reconciled to the owner's current
`codex/native-lifecycle-hardening` destination for this new unintegrated delta.

## Immediate contributor evidence across client versions

The archived PID960 trace identifies executable SHA256
`a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8`.
It is not the updated `feb351...` client. The retained private
`before-current-game-update/sb.exe` matches that archive hash. Comparing its
producer spans to `updated-official-sb.exe` establishes byte identity:

- `538EC0`, 136 bytes, SHA256
  `222be1f940e4cc1849a3d3b51ac09e8bbc49139e16631711b4e85f8331e5fb54`.
  Trace caller `538ED0` is the return from `glBegin(GL_QUADS)`. The routine emits
  four `glTexCoord2f`/`glVertex3f` pairs and then `glEnd`, with no internal color or
  texture-binding change. UVs come from its object; positions from six arguments.
- `D8EC0`, 193 bytes, SHA256
  `d992624a435278c1552c0616a684de657889887bd191d4a7e15111dd3689092c`.
  Before its quad it calls material virtual `+58` and enables blending. Trace
  caller `D8F13` follows `glBegin`. Four constant UV pairs and computed vertices
  are emitted before `glEnd`.

This validates the specific producer mapping across those two private builds,
not every material/state observation on the current client. It confirms that a
position-only collector omits required UV information, while these two local
emitters have a bounded four-vertex contract. Full native transmission still
needs verified source color/alpha and depth per contributing fragment, including
other immediate/list paths and all relevant blend/program/stencil classes. No
replay or S(z),T(z) representation is certified by this evidence alone.


## Combined trace verification and bounded next contract

The lane independently built full-profile exact combined source
`5519a8e4026136d04231c9c66cfe71fc23fdac97`, containing cue `98bcd21` and the
owner-reconciled enriched trace state. All seven targeted native tests passed
with zero skips (cue runtime, shared context, navigation draw, sixteen-combination
render test, trace full/disabled, and cel guard). All 48 Python trace tests passed.
The shared context extraction and both serialization assertions were retained.
Evidence: `E:/Projects/shadowbane/artifacts/cue-combined-native/5519a8e/lane-targeted.xml`.
This is the tested build source, not a later documentation commit. Required
foreground transparency remains unresolved; no final package was certified.

Further static evidence: quad caller `538600`, 391 bytes, is byte-identical
between the archived `a9a590...` and updated `feb351...` private clients; SHA256
`579559a61a8dd456b269789739bce3cd76a87b5d2259be2e6679422dcd0d8a7b`.
It binds material virtual `+58` at `53864B`. Its shadow branch saves renderer
RGBA, sets RGB to zero with preserved alpha at `5386C7`, calls the quad at
`538703`, restores RGBA at `53871E`, and draws again at `538769`. Constant color
is therefore branch-dependent even though it does not vary within this quad.
The inspected local code does not establish the complete inherited GLSL/ARB,
texture-combine, fog/light or stencil state; absence of a local program write is
not evidence that no program is active.

The integration owner rejected the large fragment-ledger proposal; this lane
has not implemented it. The proposed next feasibility contract is limited to
the two sealed quad emitters under the existing cel capture owner. It requires
four positions/UVs plus supported entry state, synchronous native material use,
and reusable scratch source RGBA, depth and explicit coverage for one primitive.
It is not an approved frame representation or an implementation split. A
conservative pre-Begin projected region could reduce scratch/copy cost only if
its caller ABI and clipping bounds are first verified.

Pre-native depth/stencil must be retained if native tests are to be reproduced:
copying after a depth-writing draw changes LESS/EQUAL results. Coverage cannot be
inferred from nonzero color or changed depth. Proposed production regressions
must exercise textured alpha and shadow color, LESS/LEQUAL/EQUAL, both depth-write
modes, stencil outcomes, overlapping/equal-depth primitives, unchanged native
buffers/state, synchronous input lifetime, cleanup and measured scratch cost.
Inherited program/texture state and an exact coverage marker are still missing
facts. No UV collector, replacement material shader, fixed layer count or new
renderer was added. Next active todo is to establish those supported native
source/coverage semantics with the owner before choosing a shared representation.


## Bounded feasibility: missing facts and conditional observation

Examined exact combined source `5519a8e4026136d04231c9c66cfe71fc23fdac97`.
A no-ignore inventory of the project artifacts and testing-VM diagnostics found
only the two retained terrain traces (PID 960 and 6420) already cited above.
They precede the enriched observer and use the older executable. Byte-identical
emitters establish geometry provenance, not the current inherited material state.

| Requirement | Existing evidence | Still required |
| --- | --- | --- |
| Inherited programs/material | The enriched observer records GL_CURRENT_PROGRAM on GL 2+, separate blend factors/equations, front/back stencil, color mask, framebuffer, and up to four 2D units including combine sources/operands/scales and matrices. Unsupported fields are -1. | Current emitter-entry records. Program zero does not exclude ARB vertex/fragment programs: their enable/binding is not recorded. Neither are texture environment constant color, texgen, non-2D targets, detailed fog/light state or all current attributes. Active GLSL IDs do not establish output equivalence on a scratch target. The owner must resolve these support gates before replay; an unchanged-observer capture alone cannot do so. |
| Pre-native depth/stencil | Existing cel Begin boundary queries before immediate geometry, and cue legacy capture can copy pre-draw depth for an owned actor. | No general contributor pre-draw depth/stencil snapshot exists. Current cue scratch rejects stencil in its direct path and its legacy depth delta is not fragment coverage. Establish framebuffer attachment format/sample compatibility and preserve pre-draw contents before native execution; test LESS/LEQUAL/EQUAL and stencil outcomes. Trace framebuffer ID/stencil settings do not provide buffer contents. |
| Explicit coverage | Sealed emitters give four positions/UVs and no within-quad color changes. | No exact coverage marker is implemented. Zero source RGBA and unchanged depth cannot distinguish rejection from an accepted fragment. Marker production must preserve material alpha test/discard, depth/stencil tests and source RGBA, including equal-depth and zero-alpha additive/multiplicative cases. A replacement shader or stencil overwrite is not automatically equivalent. Prove a supported strategy with developer-controlled GPU tests first. |
| Conservative ROI and ABI | Static analysis identifies arguments/object UVs in the two private executable versions. | These producer/caller spans are not installed runtime ABI authority for reading a pre-Begin ROI. Verify calling convention, argument offsets and object lifetime, seal the executable/code and reject drift. Clipping, perspective division, viewport/scissor bounds and degeneracy need tests. A bounded trace stack is evidence only; do not read guessed stack arguments. |

No collector, UV hook, frame ledger or renderer implementation is authorized by
this feasibility record. A one-quad scratch result still leaves ordered native
transmission and all contributing submission classes unresolved.

### One conditional existing-tool observation

The integration owner decides whether to request this, and owns package/launch
preparation. It is a diagnostic observation, not acceptance or authorization to
deploy. Use a separately verified **full-renderer** package built from exactly
`5519a8e4026136d04231c9c66cfe71fc23fdac97` (or replace that pin explicitly with a
new owner-verified source). Record package/DLL hashes and source receipt; trace
JSON carries executable/version/lifetime, not a Git SHA. A docs-only head is not
a replacement build source.

Launch with child environment `WONDERBANE_TERRAIN_TRACE=1`. The existing baseline
launcher exposes `-EnableTerrainTrace`, but at this pin it hardcodes the old
1.6.13 DLL and a9a590 executable hashes. **It cannot launch/certify the enriched
5519a8e package merely by changing PackageDirectory.** The owner's reviewed
current launch path/receipt is a prerequisite; do not bypass the hash checks or
present the historical command as ready for this source.

In the ordinary world scene, have visible character/name-label quads from the
two identified producers; retain normal material settings. No navigation rerun,
selection demonstration or gameplay input automation is required. Once that
scene is active, run the existing collector once inside the VM:

```powershell
& "$reviewedFrozenSource/scripts/capture-wonderbane-terrain-trace.ps1" `
  -RepositoryShare $reviewedFrozenSource -TimeoutSeconds 30
```

`$reviewedFrozenSource` must name the frozen exact source above. With more than
one verified client, add its actual `-ProcessId` and
`-ProcessCreationFiletimeUtc`; never reuse an archived PID. The collector checks
process executable/profile/version/lifetime and requests one following frame.
Retain the local result and receipt. Inspect caller RVAs 538ED0/D8F13, ordered
submissions (including multi_elements), full transmission_state, alpha reference,
current color, texture/combine state, transforms, and every continuity/omission
counter. An absent emitter or unavailable field is unanswered, not a default.

The observer allows 8,192 records, four units and 24 stack frames with a 250 ms
query budget; a driver query can overrun that budget. It can visibly stall one
frame and is not a performance measurement. No pixels, texture bytes or geometry
are read. Queries restore active texture selection; local publication is atomic.
Collector handles close on return; native trace storage/events close on normal
extension shutdown. Relaunch normally with the opt-in absent afterward. A failed
or abandoned request is reported without an automatic retry; normal restart may
be needed. Preserve only the local evidence and its original path, with no upload
or client replacement by this lane.

This one observation would narrow current GLSL/blend/stencil/2D-combine usage;
it cannot resolve ARB state, coverage or pre-draw contents. The owner should
resolve the observer's missing support fields before spending this observation
if those fields are needed for the chosen feasibility path.

### Production proof remains required

Validate captured source RGBA/depth by recompositing over two distinct known
backgrounds against untouched native reference under identical entry state.
Include alpha-cutout edges, transparent texels, zero-alpha nonzero-RGB sources,
clipped/degenerate and overlapping successive quads, both depth-write modes,
LESS/LEQUAL/EQUAL and stencil outcomes. Compare complete RGBA/depth/stencil and
all restored state/current attributes. Replay must not repeat game material
setup or native query side effects. Preserve synchronous input lifetime,
resource cleanup and measured scratch cost. Cue halo transmission must use each
contributing owned depth at the destination pixel; output background depth is
not a substitute. Existing required cue/effects transparency tests remain red.
Next active todo: resolve these source/coverage support facts with the shared
renderer owner, then implement and verify transmission, final package and the
single consolidated live acceptance. Feature delivery is not complete.


## Observer support gap closure (owner-assigned follow-up)

The owner assigned the bounded observer changes after the feasibility record.
Dependency commit b2245e9 carries only terrain_trace.cpp/test from verified
combined5519a8e; it does not merge a moving stack. The subsequent change adds
capability-gated ARB enable/binding, alternative texture target/texgen enables,
environment color, bounded raster/profile state and explicit unknowns, with
an evidence-only material predicate for the two emitter callers. It supersedes
the earlier statement that these enable/binding fields cannot be observed.
The exact field order and conservative predicate are documented in
`docs/diagnostics/terrain-draw-trace.md`. No generic material snapshot, UV
collector, replay, feature-disable path or live request was introduced.

A material candidate is not replay eligibility. Program-zero alone is rejected
when ARB state is active/unknown, alternate program mechanisms are unobserved,
units are omitted, texgen/alternate targets are enabled, or the material falls
outside the narrow fixed-function case. Query side effects, pre-native buffers,
coverage, ROI ABI and source equivalence remain explicitly unresolved. Required
native transparency regressions are unchanged and still block feature delivery.
The owner must verify this observer delta on a new exact combined pin before
choosing a diagnostic package/observation; historical launcher hash gates remain.


Validation for this observer delta: actual full DLL builds; both native trace
profiles pass with zero skips, covering advertised/absent/unknown ARB capability,
missing getter, active program versus GLSL zero, alternate material paths,
profile/pipeline unknowns, texture enable/texgen/MODULATE gates, exact query
contracts, active-unit restoration, unsafe queries, bounds and shutdown.
All 47 Python trace/analysis tests pass and the changed Python test passes Ruff.
Native JUnit is retained in the feature worktree at
`artifacts/selected-character-cue/observer-material-tests.xml`.
These checks do not certify GPU source equivalence or a release package.
Next active todo is owner reconciliation and exact combined verification of this
observer, then resolution of the remaining native source/coverage facts.


## Exact combined verification: 1c293a1

The owner applied dffd9bb alone to produce published combined
`1c293a1a48280b83ab5493f7b0a92dfb94f2c4b7`. This lane independently fetched and
built that exact source in its clean detached verification worktree. The actual
full DLL builds, both native trace profiles pass with zero skips, and all 49
combined Python trace/analysis tests plus Ruff pass. The observer source/test
files are byte-identical to dffd9bb. JUnit is retained at
`E:/Projects/shadowbane/artifacts/cue-combined-native/1c293a1/lane-observer.xml`.
No unchanged transparency gate was rerun or relabeled passing. No final package
or connected-client observation was performed.

Assessment: retained `navigation-inspector-3534418/graphics-status-in-world.json`
reports OpenGL 4.6 Compatibility Mesa 26.1.7 and 24 depth bits for the older
`a9a590...` executable. Thus separate program-pipeline capability is a specific
remaining path, not speculation. The current observer conservatively leaves
this unknown on GL4.1+ and cannot prove fixed-function eligibility on that context.
A narrowly scoped future query of capability-gated PROGRAM_PIPELINE_BINDING could
clear this ambiguity when zero; nonzero remains unsupported without stage/output
equivalence. This is a proposal to the integration owner, not a new capture or
broad instrumentation assignment. No retained extension list establishes which
additional advertised vendor paths are present or enabled on the current client.

The next bounded source/coverage feasibility case can use scratch stencil only
when native stencil is disabled, with single-sample compatible attachments and
verified convex planar raw geometry. Copy pre-native depth, clear scratch coverage
to zero, preserve inherited alpha test, and use scratch stencil ALWAYS/passREPLACE
to mark accepted fragments while writing unblended source RGBA and fragment depth.
This would distinguish zero-alpha accepted fragments and unchanged native depth
from rejection. It is unimplemented and unproven: two-background RGBA/depth
recomposition, native buffer/state invariance, depth functions, alpha cutouts,
clipping/degeneracy, successive quads, input lifetime and query-side-effect gates
are still required. It does not solve whole-scene ordered transmission.
Next active todo: owner-directed resolution of that specific program ambiguity
and bounded GPU source/coverage equivalence, before collector implementation.


The owner authorized closing the precise pipeline ambiguity. The observer now
queries PROGRAM_PIPELINE_BINDING only for core4.1+ or ARB separate shader objects;
zero clears only that path, nonzero and unavailable stay unsupported/unknown.
EXT-only semantics and independent vendor ambiguity remain unknown. Tests cover
all those cases, including missing query output and absent-capability no-query.
The full DLL builds, both native trace profiles pass and 47 feature-branch Python
trace tests pass. Actual-GL source/coverage feasibility is the next authorized
step; this diagnostic change still never authorizes replay or live deployment.


## Authorized actual-GL source and coverage experiment

The existing cue GPU executable now has `--source-feasibility`, registered as
`wonderbane_extension_selected_cue_source_feasibility`. Its focused test-only
header uses the existing RenderSceneGeometry guard and a context-owned reusable
64x64 RGBA8/depth24-stencil8 framebuffer. There is no runtime collector, native
hook, stack/ROI assumption or second feature implementation. The integration
owner explicitly authorized this bounded developer-controlled experiment.

The controlled fixture requires a single-sample default target with depth24,
stencil8 and alpha8, fixed-function MODULATE, unit-zero nearest-filtered RGBA8
texture, no native stencil, and planar convex raw quads. Explicit test packets
establish material state identically for scratch and native reference; no game
material setup is repeated. Native depth is copied before the draw. Scratch
color stores unblended source RGBA, scratch depth writes record fragment depth,
and stencil ALWAYS/passREPLACE records coverage after inherited alpha/depth
tests. FBO changes are balanced inside the shared guard; resources release on
their owning context. An active native samples query rejects capture and remains
at zero samples in the regression. Other query classes are not established by
this controlled fixture and remain unsupported for a runtime implementation.

All 288 cases pass without skips: two distinct RGBA backgrounds; LESS, LEQUAL,
EQUAL; native depth-write and alpha-write masks both ways; nearer/equal/farther
depths; varied current RGBA/UV, below/exact GEQUAL thresholds, accepted alpha zero,
partial clipping and degenerate quads. Coverage is checked independently from
expected geometry/texture alpha/depth. Unblended source channels are also checked
against texel/current RGBA, including nonzero RGB at alpha zero. Recomposition
uses the actual same RGB/alpha blend factors: alpha is S.a*S.a+B.a*(1-S.a), with
native alpha-write masking. Tolerances are 1.5/255 for captured source channels,
2/255 for recomposition and 1e-6 for depth. Native color/depth/stencil remain
unchanged by scratch; affected material, current color/UV/normal, matrices,
stencil state and 2D enables/bindings across fixed-function units restore.
Successive overlapping quads keep distinct source depths and reversing their
native order changes the result. This explicitly does not prove that nearest
fragments or depth sorting suffice for transmission.

Final local run: scratch GPU storage 32,768 bytes (64x64x8), allocation/cold
1.822 ms, 16-sample steady median 0.092 ms, native raw-quad median 0.026 ms after
three warmups. Timings include glFinish and exclude readback; they are a small
local fixture, not client/VM or full-frame performance. CPU image arrays are
test oracles only, not a proposed retained-fragment ledger. JUnit is retained at
`artifacts/selected-character-cue/source-feasibility-passing.xml`.

The existing cue GPU regression also passes. The required native-transparency
regression was rerun because its executable changed and still fails both
foreground cases (depth-write off/on), with the same 131,16,19 expected versus
116,31,37 and 127,0,0 actual RGB. Both background cases pass and still reject
wholesale early compositing. Its results remain in
`artifacts/selected-character-cue/source-feasibility.xml`.

This establishes only the scoped single-quad source/coverage mechanism. Runtime
identity/ABI/input lifetime, supported inherited material paths, native stencil
or multisample cases, full-size cost and ordered multi-contributor transmission
remain unresolved. Next active todo: owner combined verification and selection
of a bounded integration strategy using this evidence; no deployment or live
acceptance is requested, and selected-cue delivery remains incomplete.


## Opaque visibility and retained-tap counterexamples

Owner combined source `a22a1bbb8b7252ba8a0d1c1e7c1f51078d75d4d3` was independently
fetched and GPU-built in this lane's verification worktree. Both base GPU and
source-feasibility tests pass with zero skips. Evidence is retained at
`E:/Projects/shadowbane/artifacts/cue-combined-native/a22a1bb/lane-source.xml`.
The owner then directed bounded visibility/operator regressions rather than
approving the proposed atlas. Cue owns only the cue GPU experiment/header;
particles owns the navigation/effects operator test. No atlas is implemented.

The cue experiment now exercises the production mask/composite pipeline for
opaque versus depth-writing alpha, foreground versus background, and an alpha
draw followed by an opaque LEQUAL draw at the same depth. The opaque material
is deliberately chosen to match the quantized native alpha result, constructing
a counterexample rather than recovering/inverting framebuffer source. Alpha-only
and alpha-then-opaque produce identical native RGBA 127,0,0,63 and final depth
0.25, with identical pre-alpha pixel inputs and alpha draw packet. Correct cue
references differ: 131,16,19 through alpha versus 127,0,0 with late opaque.
Opaque foreground blocks the cue; opaque behind retained halo depth does not.
Thus the current final color/depth plus earlier alpha packet cannot determine
opaque visibility. An actual late opaque coverage observation or a proven
opaque-complete boundary is necessary; neither is inferred from this test.

A separate actual-GL covered-pixel reference validates foreground transformation
at the destination pixel for retained tap depths 0.25 and 0.75. The native patch
covers the destination but not the neighboring mask-tap location. Covered
reference RGB is 25,204,153 for the near tap and 31,169,179 for the far tap.
The source fold at destination agrees within 2/255, while using the neighboring
pixel or the final background depth fails. Equal-strength taps therefore cannot
lose their distinct depths before native transformation. This does not select
or change the cue's winner/reduction behavior.

Both new witnesses, all prior 288 source cases and the existing base GPU test
pass without skips. JUnit is retained at
`artifacts/selected-character-cue/visibility-feasibility.xml`. The required native
foreground-transparency gate remains unresolved; no product renderer changed.
Particles independently found a framebuffer-saturation counterexample even for
ONE/ONE, so a factors-only affine S/T eligibility rule is also insufficient.
No native contributor storage, collector, scene hook or broad instrumentation
was added. Next active todo is establishing the actual opaque visibility source
and exact supported ordered operator domain before choosing storage or splitting
transmission implementation. Full selected-cue delivery remains incomplete.


## Published-source checks at 47c1e23

Independently built the existing cue GPU target from exact published combined
`47c1e23febd8f14588e3638f2a36a88cc9333eb7` in the lane-owned verification worktree.
The cue GPU implementation and experiment files are unchanged from the tested
feature source. Base GPU and expanded source/visibility feasibility pass without
skips. The required cue transparency test executes and still fails both native
foreground cases with the previously recorded values; background cases pass.
JUnit: `E:/Projects/shadowbane/artifacts/cue-combined-native/47c1e23/lane-cue.xml`.
This is a focused cue verification, not another complete-suite/package receipt.

The published C++ interfaces do not expose an existing opaque-only scene buffer.
`CaptureSelectedCueGeometry` and its legacy equivalent require active selected
render nesting; they cannot be repurposed as evidence of whole-scene coverage.
The depth-edge composite invokes CopyDepthTexture on the default target near
scene completion, so its texture contains the mixed native depth result. These
are source-code observations only. The separately rejected private-binary
coordination payload has not been added here or sent through another task.

No runtime correction is claimed. Next active todo remains establishing a valid
opaque-visibility input and supported ordered transmission behavior. Detailed
binary-analysis coordination is separately waiting on explicit sharing
permission after automatic review rejection. Movement work is not the reason
for the visual feature hold.


## Shared scene guard: separate shader pipeline restoration

A focused runtime fix saves, clears and restores the core/ARB program-pipeline
binding around RenderSceneGeometry, alongside the existing current-program
save/restore. Clearing only the current program exposes a bound pipeline's
stages to extension geometry. Support is gated by desktop GL 4.1+ or the exact
ARB_separate_shader_objects extension token; EXT-only support is not conflated.
Missing binding API or an unwritten binding query rejects before state mutation.
No second renderer or new package path is introduced. Integration owner confirmed
no overlapping scene_draw.cpp/h changes and will reconcile this isolated commit.

The actual-GL regression failed before the fix: native green fragment shading
incorrectly colored extension geometry green. After the fix it verifies red
extension pixels, green native pixels afterward, independent current-program and
pipeline bindings, and unchanged fragment-stage attachment. It executed on the
host (no capability skip). The Release DLL and GPU test build pass. Base cue GPU
and 288-case source/visibility feasibility tests pass; required native-transparency
still fails the same two foreground cases. JUnit is in the ignored build tree at
build/cue-full/artifacts/selected-character-cue/pipeline-guard.xml.

The pipeline rule follows the Khronos compatibility specification, section on
program pipelines: https://registry.khronos.org/OpenGL/specs/gl/glspec46.compatibility.pdf.
This state-restoration fix does not supply opaque-only visibility or solve ordered
native transmission. Next: integrate and verify this shared guard in the owner's
combined source, then continue the outstanding transparency requirement. Full
feature/package acceptance remains blocked by that requirement.


Pipeline test gate accounting: the follow-up exposes --pipeline-guard as a
separate executed GPU-test mode. Unsupported contexts return 77 explicitly;
missing required APIs on an advertised capable context fail. The ordinary cue
GPU test no longer silently includes an optional subtest. The integration owner
owns adding its named CTest and required package-gate membership to the combined
source. Runtime support for older contexts remains unchanged.


## Independent combined verification: 1b0b6c5

Verified exact owner-published source
1b0b6c5f29c7015c85006a570686253f30676f92 in the lane-owned detached verification
worktree. It includes production fix 6ca19048e3eb4c40a52d1c2527cef5d0ae2840b5
and explicit test mode f1a56c27db0e3bc90b221f7c2a3f4f5ce256884c. The guard C++
and GPU test match the feature branch; the reconciled header correctly retains
both verified background and scene/UI boundary authority.

Independently built the Release full-profile DLL and cue GPU target. Named
scene_pipeline_guard, base selected_cue_gpu, and source_feasibility all execute
and pass. Required selected_cue_native_transparency executes and fails both
foreground cases, unchanged; background cases pass. Zero skips across the four
checks. Evidence: E:/Projects/shadowbane/artifacts/cue-combined-native/1b0b6c5/lane-cue.xml.
Reviewed central CTest registration and package builder required-set validation:
a missing, skipped, failed, or duplicate pipeline gate cannot certify a package.
The integration owner separately reports both profiles' affected rendering gates
pass with zero skips; this lane's independent build is full-profile only.

The shared pipeline correction is integrated and verified. Next active todo is
correct opaque visibility and ordered native foreground transmission. Final
package validation and consolidated live acceptance remain outstanding; no
completion or installable-candidate claim is made. The feature worktree remains
on codex/selected-character-cue; normal main and navigation checkouts are untouched.


## Cue capture uses the shared native-query exclusion

The user directly authorized private analysis sharing among the existing cue,
particles and integration tasks. Coordination has resumed; private binaries,
captures and detailed audit files remain ignored local artifacts. No deployment
or public disclosure was authorized by that permission.

Imported only scene_draw.cpp/h from the owner's exact
20bd47557dae1aea7072505b45ed68fbd5d9e39b as a prerequisite checkpoint. Cue raw
capture now calls AreSceneSampleQueriesInactive before submitting geometry or
entering the legacy fallback. The duplicate SAMPLES_PASSED-only API/check was
removed; shared guarded composition handles all supported sample-query targets.
This also prevents the former depth-write-on fallback from reporting capture
success during an active query. No new renderer, lifecycle owner or hook added.

The expanded production GPU regression covers SAMPLES_PASSED,
ANY_SAMPLES_PASSED and ANY_SAMPLES_PASSED_CONSERVATIVE, each with native depth
writes off/on. It checks zero callback invocations, zero added query samples,
unchanged graphics state and rejected indicator composition. All six cases
execute on the host. They reproduced failures before the fix and now pass.
Release DLL/GPU builds, base GPU and source/visibility feasibility pass. Required
foreground transparency remains unchanged with two failures; no skip or expected
failure replaces it. Local JUnit: artifacts/selected-character-cue/query-capture.xml.

The integration owner already owns named shared query/pipeline gates and their
package membership. Next: reconcile this capture fix with the combined source
and verify it, then continue opaque visibility and ordered transparency work.


Independent query-fix verification: exact combined source
1eea5591a5884321eaddfc9fa364d99f3f327be5 matches the feature's selected_cue_gpu.cpp
and shared scene_draw.cpp/h. A fresh full-profile Release DLL and GPU executable
build pass. Base cue GPU (all six raw-capture query cases), named scene query
guard, named pipeline guard and source/coverage feasibility execute and pass.
Required cue transparency executes and still fails the same two foreground
cases; zero skips. Evidence:
E:/Projects/shadowbane/artifacts/cue-combined-native/1eea559/lane-cue.xml.
The owner separately verified both profiles. The query repair is integrated and
closed; the next active todo remains complete opaque visibility and ordered
transmission, followed by package verification and consolidated acceptance.


### Constant-alpha selected-material coverage (2026-09-05): incomplete

Do not integrate 81db951 alone. Integration review reproduced an EQUAL-pass
regression: skipping a constant-alpha zero-contribution depth-writing prepass
also removed private depth needed by a later visible selected material pass.
The correction limits suppression to depth-write OFF. Depth-writing submissions
retain the previous capture behavior and support subsequent EQUAL passes.

The actual GPU executable retains 12 constant-alpha cases plus the new prepass
sequence. After the correction, the prepass and ten constant-alpha cases pass;
the two invisible depth-writing cases fail explicitly. Geometry depth currently
doubles as visible coverage; a complete fix must separate these responsibilities.
Do not weaken or remove those failures or describe this slice as complete.

The full DLL and GPU executable build. Source feasibility passes. In addition to
the two constant-alpha coverage assertions, native foreground transparency still
fails its original two assertions. No package, deployment, or acceptance receipt
is produced by this change. Both focused commits belong to draft PR29 and require
integration-owner review; the owner's branch remains the combined destination.


### Separate EQUAL-test history from visible coverage (2026-09-05)

Supersedes the incomplete constant-alpha depth-prepass draft above. Invisible
constant-alpha and RGB-write-disabled submissions no longer enter the visible
mask; the caller still performs the original native submission. A later visible
EQUAL pass snapshots actual pre-draw native depth into a lazy private D24S8
scratch target. Raw geometry records depth/alpha/program-passing coverage in
private stencil. That stencil gates a second raw submission into the independent
nearest-visible-depth mask. No actor, wrapper, animation, or native lifecycle
callback is replayed, and native depth/stencil storage is not modified.

This path requires a single-sample default D24S8 target and framebuffer blit
support; other depth/stencil formats are explicitly rejected. It uses two raw
driver submissions and two depth/stencil blits per EQUAL capture. Its live cost
has not been measured. The extra scratch allocation is four nominal bytes per
pixel, allocated only on EQUAL use, and released with the existing context-owned
resources. Normal storage remains eight bytes/pixel; maximum legacy plus EQUAL
storage becomes 32 bytes/pixel (five texture names).

Actual GPU checks pass for all 12 constant-alpha cases, invisible depth prepass
followed by visible EQUAL, existing color-disabled prepass, partial matching
native depth, native depth/stencil and graphics-state preservation, stale-frame
coverage, bounded allocation, and cleanup. Full DLL and GPU executable build;
base GPU and source feasibility pass. The original two native foreground
transparency assertions still fail. This solves selected material coverage,
not ordered foreground compositing. Shared primitive-query protection must be
included and combined-source verification completed before integration acceptance.


### Ordinary versus EQUAL cost check (2026-09-05)

The existing `--cost` mode now compares LEQUAL/EQUAL at 640x480 and 1920x1080,
with 1 and 46 captures, 16 samples, alternating baseline/enabled order, and an
identical native depth prepass. Callback counts assert one/two supplemental raw
submissions respectively. EQUAL executes two blits per capture. Lazy storage is
asserted at 8/12 bytes per pixel, and release is checked between every case.

At 1080p/46 captures on this host, median enabled-minus-native synchronized frame
time was 2.295 ms ordinary and 4.275 ms EQUAL; enabled medians were 2.489/4.483 ms.
Ranges were 2.164–6.480 / 3.829–9.080 ms. Mask storage was 15.820/23.730 MiB.
At 640x480/46 captures, the median differences were 2.154/3.703 ms. Amortized
per-capture differences include frame setup/compositing and are not isolated
capture latency. These synthetic host results do not certify a live-client
budget. Raw local receipt: artifacts/selected-character-cue/equal-cost.txt.


### Independent combined-source receipt e7a648b (2026-09-05)

Verified clean detached exact combined source
`e7a648bc0f713d828dbaff95e1919c16d480730e` in the cue-combined-verification
worktree. Fresh full DLL and GPU executable build. Base GPU, pipeline guard,
geometry-query guard, and source feasibility pass without skips. Native
foreground transparency retains exactly its previous two failing assertions.
Receipt: E:/Projects/shadowbane/artifacts/cue-combined-native/e7a648b/lane-cue.xml.
Production cue GPU source matches d116843 except the intended shared helper
rename to AreSceneGeometryQueriesInactive, retaining primitive-query protection.

The follow-up source test also enables a partial native scissor during EQUAL
capture, verifies the scissor box/enable and stencil state are restored, and
checks native depth/stencil preservation and absent right-side coverage. It
passes in the feature worktree. Unsupported default depth/stencil formats were
not exercised with actual hardware; rejection is explicit in source, not a
verified alternate-format rendering path. No acceptance package or deployment.
