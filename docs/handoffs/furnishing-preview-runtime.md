# Furnishing preview runtime

## Delivery status

Native 1.8.29 / host 0.3.49, branch `codex/furnishing-preview`, targets
[draft PR #35](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/35)
into `main`. This includes recorder dependency `c764e22` through merge `c890260`.
The versions were reserved by the coordinating task on September 24.
Source implementation and local validation are present; exact-source packaging
and live visual acceptance are the remaining delivery steps. Nothing from this
preview lane has been installed or activated in the VM. The coordinating task
owns deployment and the single restart, preserving the current game and rollback.

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
`glPushMatrix` / `glPopMatrix` import observers identify its exact reviewed call
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

## Validation and remaining acceptance

The full Win32 Release DLL builds with warnings as errors; the required local
native suite passes 198 executed tests (three private-image probes are checked
separately by packaging). All 337 host package-gate cases pass. Local tests cover native ABI and faults, selection changes, resource families,
queue membership, poses, actual Win32 click pairs, and production runtime flows
using controlled engine calls. Runtime scenarios include nesting, rotation,
Stop during submission, context loss, missing completion, nonzero shader state,
foreign threads, alternate passes, replaced bindings, hidden HUD, modal input,
missing floor, partial installation and unsealed images. Required package gates
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
