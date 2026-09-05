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

The updated feature test measured 640x480 enabled median 1.897 ms (1.646–2.316 ms),
native-only median 0.069 ms, and cold setup frame 2.654 ms. At 1080p it measured
2.646 ms (2.428–2.985 ms), native-only 0.095 ms, and cold frame 3.528 ms. Normal
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
