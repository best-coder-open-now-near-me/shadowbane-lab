# Furnishing preview runtime

## Delivery status

Native 1.8.30 / host 0.3.50, branch `codex/furnishing-preview`, targets
[draft PR #35](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/35)
into `main`. This includes recorder dependency `c764e22` through merge `c890260`.
The coordinating task reserved these corrective versions on September 24.
The coordinator installed the previous 1.8.29 / 0.3.49 package and owns all VM
input, deployment and restart actions. Corrected exact-source packaging is next;
live visual acceptance and PR review/integration into `main` remain.

### Confirmed startup failure and correction

The user selected Bench while inside building 4761372:8 on floor 0. Read-only
live checks confirmed all observable SelectionCapture gates (122 reverse-checked
blocks), but the game HWND had no preview child window. The exact installed DLL
had a published runtime and renderer_ready=1, with every preview callback and
both preview import slots zero. The game matrix imports already pointed to the
renderer wrappers (DLL RVAs 0x41b00 / 0x41a40). Preview startup rejected those
imports because it expected bare OpenGL procedures. This was a startup ownership
collision, not the user's selection, an open menu, or an asset-loading failure.
Private receipts remain with the coordinator (`live-preview-globals.json`,
`live-selection-gates.json`, `live-child-windows.json`). The exact old DLL symbol
map and read-only diagnostic manifest remain in the ignored local directory
`artifacts/furnishing-preview/runtime-symbols`; its reconstructed DLL is byte-for-byte
identical to the previously packaged DLL. Do not deploy that diagnostic copy.

The renderer now solely owns the matrix imports and dispatches preview events
after original GL calls, preserving the game caller address. Its matrix wrappers
remain installed across Stop, allowing matching outer completion to retire a
submitted receipt. Re-enable accepts only those exact retained slots, originals
and wrappers; foreign hooks remain rejected. Preview startup verifies this shared
ownership and registers persistent callbacks without replacing imports.

The runtime regression now runs the actual renderer installer before preview
startup and sends drains through its actual wrappers. It covers call-through,
foreign callers/threads, display-list suppression, Stop and re-enable during
submission, replaced imports, context loss and failed context registration.
The focused Release build and 28 preview/renderer/context checks pass.
Full exact-source package qualification is the next checkpoint.

## Using the preview

The character must be inside the building. Open its furnishing panel and select
one loaded furniture item. The Preview bar appears at the bottom of the client.
Choose **Preview**, then move over the floor plan to position the actual model
on the selected floor in the 3D world. Click the floor plan to hold the position;
click again to follow it. **Rotate left/right** turns by 90 degrees. **Cancel**
or **Esc** removes the preview. Selection/floor/building changes, a hidden panel,
modal input or lost foreground cancel it too. The last valid position stays
visible while moving to the rotation controls.

While previewing, the bar labels the image as a preview and owns floor-plan left
clicks; they cannot become ordinary placement clicks. Other input remains native.
There is no placement command, network message, furniture scene insertion or
manufactured world object. Cancel preview before using ordinary placement.
Preview appearance does not establish collision validity or server acceptance.

## Ownership and rendering

`furnishing_runtime.cpp` registers only after successful shared startup and exact
client sealing. The existing native update owns selection and pose work. Actual
actor parent identifies the building; HUD structure must match it. The native
mouse-coordinate conversion and top-level UI hit determine floor-plan position.
Selection includes visible-HUD ownership, row/model generation, selected floor,
rectangle/zoom/scale, exact mapping interfaces and a reverse-read journal.

A model retain keeps shared resources alive through a private recursive render
clone. Only the reviewed preloaded static mesh / ColorTexture / ArcImage family
is admitted, with bounded metadata and GL-context texture checks. Uniform positive
building scale is supported; other scale can require unrepresentable shear.
Unsupported assets show unavailable without entering a native clone operation.

A verified main depth clear grants one outer native queue drain. Persistent
renderer-owned `glPushMatrix` / `glPopMatrix` import observers identify its exact reviewed call
sites and survive renderer Stop. The push observer adds only private renders,
qualifies actual wrapper shader/texture metadata before iteration, and keeps an
exact receipt. Only matching outer completion after shader shutdown retires its
nodes. Nested/alternate passes cannot acquire or retire that receipt. There is
no direct replay of shared native model draw state or raw GL cache restoration.

Stop closes admission immediately; a submitted receipt can still retire and
release on its owner. HWND destruction notifies preview before retiring reference
observation. Context or drawable changes invalidate preview before unbinding,
even if the switch fails. Uncertain native calls, missing completion or broken
queue proof retain at most the one model/clone transaction and disable preview
for the session. A foreign thread cannot inspect or mutate owner state.

## Previous package validation and remaining acceptance

The full Win32 Release DLL builds with warnings as errors; the required local
native suite passes 198 executed tests (three private-image probes are checked
separately by packaging). All 337 host package-gate cases pass. Local tests cover native ABI and faults, selection changes, resource families,
queue membership, poses, actual Win32 click pairs, and production runtime flows
using controlled engine calls. Runtime scenarios include nesting, rotation,
Stop during submission, context loss, missing completion, nonzero shader state,
foreign threads, alternate passes, replaced bindings, hidden HUD, modal input,
missing floor, partial installation and unsealed images (the previous isolated startup fixture did not compose the renderer and preview installers). Required package gates
include these and the furniture response recorder in both build profiles.

Exact-source package validation and the reviewed original-image checks must pass
before handing a candidate to the coordinator. Two pre-existing ideal-transparency
stretch diagnostics are reported separately by the established builder; they do
not verify this native preview. Live acceptance must verify the selected model's
actual textures, scale, floor height and rotation; cancellation on selection,
floor and occupancy changes; and no placement dispatch during preview. A rotated
building and repeated preview/cancel cycles remain live checks. No live result
is inferred from synthetic engine or local GL tests.

Private builds, test logs and original-client inspection remain under ignored
`artifacts/`. Source docs are published; client binaries and captures are not.


## Qualified package - September 24

Exact pushed package source: `0193dd74662eb368c4961a2ab8d9db6826fb70b4`.
Documentation-only updates after that source do not change the packaged runtime.
The coordinator received this package for staged-candidate replacement review;
activation and all VM actions remain with that task.

Private package root:
`C:/Users/mewhi/.codex/worktrees/c079/shadowbane/artifacts/p29/fc7b8466`.

- `navigation-inspector-acceptance.zip` SHA-256:
  `9ca0fe2e669677f83335a3f6ba8b62c5af270b2e23bc9fbe23d24936b68e67e4`.
- `full/wonderbane-extension.dll` SHA-256:
  `33cdf5f8bf656766ad944a1bc06ad76b60ebcb5b8cd4728cabebf7fdc9163365`.
- `diagnostics-only/wonderbane-extension.dll` SHA-256:
  `fe3b1654e1e5b778b976a8eaadc7203347130055bd920873b58544bddd195838`.
- `dist/shadowbane_lab-0.3.49-py3-none-any.whl` SHA-256:
  `07c74cc5ec944f996f5255df80d618d2707b7067ff5c4ba58c3c169fc0732010`.

The receipt reports `acceptance_eligible: true`, no known failed required gates,
and 36 executed validation steps. All 61 recorded files were independently
checked for size/hash, and ZIP CRC/hash verification passed. This certifies a
candidate for acceptance testing, not live visual acceptance.

Final host suite: **3,811 passed, 18 skipped**. Each native profile passes **198**
executed required-suite cases; the three private-image probes skipped in that
generic suite were separately verified against the reviewed original client.
Each profile passes **63 movement IPC tests** without skips. Wheel/source archive
builds, isolated installation, entry point, panels and installed contracts pass.
The two known transparency stretch diagnostics remain separately recorded per
profile (four deferred findings), with no new required-gate failures.

Reproduction uses the prepared project environment:
`E:/Projects/shadowbane/.venv/Scripts/python.exe scripts/build_navigation_inspector_package.py --output-root artifacts/p29 --reviewed-client E:/Projects/shadowbane/artifacts/guard-deploy/client-update-20260924/official/sb.exe`.
The default system Python lacked the `build` module. Its completed native checks
were not substituted for the final prepared-environment run. Superseded package
attempts `artifacts/p29/ba50d541` and `artifacts/p29/84fef440` were removed;
retained final evidence is the qualified package root above and the existing
private `artifacts/furnishing-preview` build/static-review evidence.

Next: the coordinator stages the qualified candidate while preserving the live
client/rollback, then waits for the user to close the game for one restart.
Supervised preview/recorder acceptance follows. PR #35 remains draft and outside
`main` until that acceptance and required review; no merge or deployment is
claimed by this source handoff.


## Live operator cues and coordinated restart

Use the coordinating task's one restart. When convenient, the user closes
WonderBane normally in the VM and confirms there. After that task updates and
validates the closed client, launch **Vendor Test**, log in as **Bart**, retain
the **Bench contract**, and wait for capture to be armed. Return to the occupied
carpenter building and Furniture Placement. Select Bench once, then use Preview,
rotation, hold/follow and Cancel first, without ordinary placement. The coordinator
separately conducts one ordinary placement capture after preview has ended.

The Preview bar is visible only for an admitted visible furnishing HUD, matching
occupied building, selected owned static model and selected floor. No bar means
that admission is unavailable; it is not evidence of a server or resource fault.
The initial Preview button is an entry point, not prior proof of resource support.

- `Move over the selected floor plan to preview`: the copy was acquired; no valid
  floor point is currently selected.
- `Preview only - click floor plan to hold; Esc cancels`: a candidate pose is ready.
- `Position held - rotate, or click the floor plan to follow again`: hold mode.
- `This item's loaded model is unavailable for preview`: qualification/acquisition
  rejected the current loaded model. Do not infer which resource field failed.
- `Preview unavailable at this building or floor`: candidate pose is unavailable,
  including unsupported nonuniform/negative building scale.
- `Preview unavailable for this session`: uncertain native ownership/lifecycle;
  no replacement clone is allocated in that session.

These status cues describe admission and pose, not proof that pixels were drawn.
The operator must visually verify the actual textured model, scale, floor height,
orientation, removal on cancellation and no placement dispatch. The supported
resource path is the reviewed ArcStaticModel / ArcObjRender tree with one selected
ArcSinglePolyMesh and loaded ArcColorTexture/ArcImage per node (up to 64 nodes).
Other families remain unavailable. Graphics context/drawable loss disables this
session; selecting the item again cannot override that lifetime decision.

PR #35 includes recorder source `c764e22` and its package handoff `5beb192` through
merge `c890260`; it does not include the coordinator's later recorder staging-only
document `2672e26`. PR #37 and PR #35 remain separate unmerged reviews targeting
`main`. The combined package contains recorder source already; neither a branch
push nor staging merges either PR. Preserve the later staging documentation when
reviewing the overlapping branches for integration.
