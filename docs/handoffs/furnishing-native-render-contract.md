# Furnishing preview: native ownership and rendering contract

This continues the [preview handoff](furnishing-preview.md) on draft PR #35.
The following is static qualification against the two exact September 24 client
hashes recorded there, plus the coordinator's consistent occupancy snapshot.
It is not runtime admission or visual acceptance. All code addresses are RVAs.
Private disassembly and input locations remain in the parent handoff.

## Destination is the occupied building

The user clarified that the character being inside a building identifies the
building in use. Follow the current actor's native pose parent; do not identify
the destination by camera position, building name, proximity, NPC or open HUD.
The Furniture HUD structure must equal that occupied building before showing a
candidate. Leaving/changing the building invalidates the candidate even if the
HUD remains open. Parent equality is a consistency check, not a server receipt.

The coordinator's September 24 reverse-rechecked snapshot establishes:

- Current actor class `0x114165c`, key `1764161:53`.
- Actor `+0x4b0` -> component -> pose; pose `+8` is the native parent.
- Parent equals HUD `+0x64c`, class `0x1177c0c`.
- Parent world key `+0x18` and management key `+0x780` are both `4761372:8`.
- Structure world translation `(79292.7421875,65.60722351074219,-52861.19140625)`;
  unit quaternion and scale. Actor local translation is approximately
  `(-3.7310195,3.0550802,3.1529570)`. Do not use actor height as the floor height.

The opt-in reader now records `occupancy_raw`, the native parent reference and
its world key for this reviewed structure class. It records HUD equality and
reverse-rechecks every added link/key. It preserves unavailable/unreviewed
states without following unknown class layouts. Its result is copied evidence,
never ownership, a pose lease or placement permission. Other building classes
need explicit qualification before this diagnostic interprets their keys.

## Native reference ownership

ArcStaticObject constructor `0xe8b70` installs the virtual-base table at `+8`;
its first offset locates the reference interface at `+0x718`. The counter is at
`+0x71c`, initially one. Generic retain `0x131190` increments the adjusted
reference counter. Release `0x1311b0` decrements and invokes the finalizer at zero.

Object-slot helper `0x89ba0` performs the virtual-base adjustment and retain.
Assignment helper `0x89bd0` releases the old slot and **adopts**, rather than
retains, its new argument. Existing `BuildingTarget` demonstrates the adjusted
retain, owner-thread admission and uncertain-fault quarantine pattern. Existing
movement lifetime registration covers the actor/parent/world tuple, not arbitrary
new rendering resources. Neither an external snapshot nor `RenderCallbackLease`
substitutes for native object ownership.

## Transform convention

The adjusted transform-interface getter `0xd59a0` returns pose `+0x20` world TQS;
`0xd59c0` returns pose `+0x48` local TQS. Each TQS occupies 40 bytes: translation
XYZ, quaternion **WXYZ**, scale XYZ. HUD conversion `0x68ac30` uses `0xd5f30`,
which copies world TQS, calls imported inverse, then transforms the point.

The exact manifest-matched Math.dll was read statically from
`C:/Users/mewhi/Downloads/WonderbaneClient/Wonderbane/Math.dll`, SHA-256
`3e1608f6ca23cd17320ab9817c22d79379b8cc40a4081b61bfbd2ac405f47cfc`.
It was not loaded or executed. Named exports and disassembly establish that
SetRotateY (DLL RVA `0x28c0`) uses radians and stores
`(cos(angle/2),0,sin(angle/2),0)`. Transform (DLL RVA `0x2fe0`) scales the point
per axis, applies `q * point * conjugate(q)`, then adds translation. The inverse
implementation is not a license to assume arbitrary nonuniform-scale/rotation
compositions are representable by a TQS without shear.

Heading updater `0x2918d0` adds radians at pose `+0x110`, wraps at two pi and
writes a **negative-heading** Y rotation. Default forward is `(0,0,-1)`.
Ordinary furniture rotation `0x67cf20`/`0x67cfb0` uses plus/minus pi/2. These
functions mutate committed objects and must not be called for a preview.

HUD `0x68acb0` maps screen deltas to local X/Z using `HUD[+0x640] * zoom`.
`0x5936d0` casts down from local Y=1000 onto the selected native floor triangles.
The coordinator observed layout scale approximately 6.25012255 and zoom 1.
The candidate must reuse the qualified floor-height calculation, then compose
its local pose with the occupied structure TQS. Rotated-building acceptance
remains outstanding; the captured building has identity rotation.

## Private render copy

ArcStaticObject's secondary interface is `+0x44`, vtable `0x114350c`. Its render
walk reaches `0xce580`, which obtains root render `object+0xc0` and composes the
object world pose via `0x1c5950`. Calling this on the borrowed inventory model
would alter its render transforms and may change other native state.

Native clone `0x1c68f0` takes a source ArcRenderObject (`this`), output slot and
recursive flag. It allocates 0x168 bytes, uses copy constructor `0x1c1e40`,
recursively clones/attaches children and returns one owned reference in the
output slot. This is a candidate ownership path, not yet a qualified API call.

The copy has independent world/local TQS (`+0x48`/`+0x70`), child vector and
texture set (`+0xe8`, RTTI ArcTextureSet, vtable `0x114a5a4`, copied through
`0x1e3b30` and texture virtual `+0x80`).
It retains a **shared template** at `+0xc4`, borrows `+0xf4`, copies secondary
callbacks at `+0x34`, and resets registration/resource fields `+0xf8..+0x110`.
Copy construction calls `0x1cd970(false,true)`, which selects index zero in the
shared template mesh render-set under native locking. Therefore a private
transform/texture-set copy does not imply fully independent render resources.
Source eligibility, callbacks, dynamic/skinned material paths and shared mesh
selection still require qualification before invoking the clone in production.

Compose `0x1c5950` writes private world TQS from parent TQS and local TQS:
translation = parent translation + rotated/scaled local translation;
quaternion = parent quaternion * local quaternion; scale = per-axis product.
It recursively composes child copies. Destructor `0x1c2700` (adjusted `this`
is render+0x34) destroys the owned texture set, releases template/children,
and handles callback/registration cleanup. Do not replace it with raw free.

## Static submission and the main queue

Correction to the earlier exploratory path: **static** render producer is
`0x1cb020`, with a 32-byte wrapper whose draw is `0x1c89a0`. Producer `0x1cb100`
and wrapper `0x1c8a90` are a different, character-oriented variant and must not
be substituted for static furnishing submission.

Static enqueue takes render+0x30 and the queue. It uses a global frame wrapper
pool, stores a **borrowed** render pointer at wrapper+0x1c and submits through
`0x1c4340`, with recursive child submissions. Queue insertion `0x4d9830` uses
native material/depth ordering. Flags 0x80 and 0x40 can create additional shadow
or special submissions. The reviewed copy constructor clears these two bits
(`+0x148` keeps source bits 1..5, sets bit 4 and clears bit 0); validate the
postcondition instead of carrying shadow/special behavior into a preview.

Static wrapper `0x1c89a0` assigns render+0xec from wrapper+0x18 and calls
`0x1cb700(true,false)`. This path uses render world TQS and the native view,
updates native material/shader state and GL_NORMALIZE tracking, and does not
perform the character wrapper's extra `0x1cd970` preparation. Calling it inside
a driver-state-only save/restore would leave native caches inconsistent.

MainDisplay `0x797ad0` receives secondary `this = complete root+4`. Its world
queue is **complete root+0xfc**. After the reviewed clear and sky, `0x1ca470`
resets/grows frame wrapper pools; ordinary objects enqueue; MainDisplay invokes
main drain `0x79c730` at `0x79817e`. The drain's glPushMatrix returns at
`0x79c73e`, before enumerating queue nodes. Its glPopMatrix returns at
`0x79c7f7`, after this traversal. These are possible IAT boundaries; do not patch
executable text, which the existing exact-image admission verifies in full.

The same drain also has a second direct caller: alternate pass `0x797900`
invokes it at `0x797a2c` using global queue `0x16aaec8`. Thus the drain's own
push/pop return address does **not** identify the main queue. Native main-frame
phase and camera/context evidence must distinguish these passes; do not recover
a speculative caller or queue by walking the stack. Exact-image sealing does
not make a shared return address unique.

MainDisplay clears its queue through `0x4d9a00` at `0x797eca`, before its clear
and new submissions. This tree reset returns 20-byte nodes to the native pool
without dereferencing their wrapper/render payloads. It does not release render
ownership. The reset and frame-wrapper pool are distinct lifetimes. Static
enqueue also skips its own wrapper when that pool is full; it cannot promise
submission success just because the clone and texture are ready.

This drain does not itself clear the tree. Finishing its first traversal is not
yet proof that no later native path will inspect the queued wrapper. Furthermore,
`0x1cb000` only clears a native activity flag; it is **not queue retirement**.
The generic drain `0x4d9980` also serves UI previews and other passes, so it is
not an interchangeable main-world boundary.

Before enabling submission, prove root/queue identity, exact caller seals,
render-context and owner-thread equality, frame generation, queue disposal and
all last uses (including exceptional/reentrant paths). Do not retain wrapper
addresses across pool resets. A render copy must outlive every queued raw use.
Cross-thread Stop/context invalidation must defer native release to its owner;
callback-only render leases do not cover the interval between enqueue and drain.
An uncertain native call must quarantine ownership rather than guess a release.

## Eligibility details and next live evidence

Callback copy `0x197b40` duplicates source callback registrations when the source
secondary flag at render `+0x38` has bit 0 set. An ordinary static preview must
reject that case until those callbacks and retirement are independently owned.
Render flag `+0xf0` enables a branch in `0x1cb700` that dereferences borrowed
`+0xf4` and can create a resource at `+0x104`. A simple opaque preview must
qualify that branch or require it disabled; a render clone alone is insufficient.

The texture-set copy dispatches virtually for each texture. ArcSingleTexture
(vtable `0x114a2f4`, clone `0x1df2d0`) creates its own texture wrapper, copies
metadata and **retains the shared resource at texture+0x5c** through the generic
adjusted reference interface. ArcColorTexture (vtable `0x114a39c`) clone `0x1df650` delegates to
`0x1df2d0`, so its `+0x5c` shared reference has the same reviewed ownership.
ArcAnimatedTexture remains separately unqualified. Do not claim all materials are independent or treat
an archive texture-type value as the loaded native class. No texture bytes or
client binaries are required in published source.

An owned unselected row is sufficient for baseline resource evidence. Selection
is a separate required gate for the eventual runtime candidate. The next
coordinator-owned snapshot should bind the owned entry/deed/model and occupied
structure in one process lifetime,
then qualify the model's root render, bounded children, callback/feature flags,
texture-set and actual texture classes, shared resource readiness and reference
interfaces. No clone or draw call is needed for that read-only evidence. Owner
update/render thread and context evidence must separately establish the proposed
runtime boundary. The coordinator subsequently confirmed ordinary single-click
selection: list+0x404 points at the owned row control and HUD+0x660 at its owned
entry. No drag/drop or Accept occurred. That establishes selection, not resource
ownership, runtime admission or placement acceptance.

## Remaining acceptance

Active: finish clone eligibility and queue last-use/retirement qualification.
Then implement the owner-captured selection/pose, retained private renderer and
native queue integration as one coherent runtime slice. No native hook has been
authored from these leads. The coordinator owns unresolved ordinary row selection
and all VM observation/deployment. No selection is fabricated to bypass it.

Runtime acceptance still needs real Bench geometry/materials in the occupied
building, selected floor, cursor-following pose/orientation, clear Preview label,
depth/occlusion, cancellation, building/row changes, context/stop/reopen behavior,
and evidence that no placement message is emitted before explicit confirmation.
A successful observation test or offline disassembly is not preview completion.


## Bounded helper for coordinator review

`read_native_furnishing_preview(memory, resource_entry_key=(5017277, 30))`
now optionally captures the one requested **owned entry key**, independently of
whether it is selected. Use the existing read-only process handle admitted by
exact PID, creation time and reviewed executable digest. This task did not run
the helper on the VM. The default recorder remains unchanged and does not follow
render resources unless this keyword is explicitly supplied by its caller.

The result preserves normal `selected_entry_address`, list selection and per-row
`selected`, and adds `render_resources_raw` only to the requested row. An absent
or ambiguous owned key is an error; this argument never supplies a native pointer
or changes selection. It uses the same read set as the HUD/row/occupancy capture,
so changed ownership, graph links, flags, transforms or resource class words
invalidate the entire snapshot on reverse verification.

Strict layout predicates (all RVAs): model `0x1143540`, secondary+0x44
`0x114350c`; render `0x1149dbc`, secondary+0x30 `0x1149d94`; template
`0x114a074`; mesh set `0x11499f4`; texture set `0x114a5a4`; single/color texture
`0x114a2f4`/`0x114a39c`. Unknown primary classes are reported without following their fields.
Unknown resource target/mesh classes are raw references only. The reviewed
ArcImage target (`0x11490f0`) permits the additional raw metadata listed below;
resource readiness is never inferred from those values.

Bounds per requested row: 64 total render nodes, depth at most 8, 16 members per
mesh/texture set and 256 total set members. Repeated/cyclic or null child nodes,
invalid vectors/pointers, inconsistent secondary interfaces, and nonfinite TQS
or opacity are rejected. These conservative evidence limits are not a claim
that every legitimate furnishing fits them. Render+0xf4 is an untyped borrowed
address and is never dereferenced. No geometry/texture payload is exported.

`selection_admitted`, `render_lifetime_owned`, `resource_readiness_verified` and
`native_calls_made` remain false. All reads are copied evidence with no native
calls, retain/release, loading, cloning, drawing or placement. A stable external
copy still cannot prevent native address reuse. The focused helper/observer/
recorder suite passes **115 tests**; Ruff passes. Next: coordinator resource
baseline/selected snapshot, while queue and owner-thread qualification continues.


## Selected Bench resource evidence

The coordinator ran the helper transiently, with the exact process creation time
and prepared executable hash, and obtained a reverse-rechecked selected snapshot.
Its private receipt is `carpenter-investigation/20260924/selected-resource-graph.json`
in the coordinator's VM evidence directory; no capture is published here.
The requested entry key `5017277:30` is selected in both list and HUD, and actor
occupancy matches structure key `4761372:8`. The screenshot separately shows
"Furniture deed for Bench". No drop, placement or native function call occurred.

The model/root/template/set classes match the static contract. The root has no
children, callback flags 2 (registration bit 0 clear), opacity 1, feature bytes
`[48,16]`, special bytes `[0,0]`, and a null borrowed `+0xf4`. Both current root
TQS values are the asset-local offset `(0.001,0.001,-0.001)`, identity rotation
and unit scale; this is not the candidate building/world pose. The mesh set
has one element and selected index zero. Its actual class is
**ArcSinglePolyMesh**, vtable `0x11498a0`, qualified by RTTI; no mesh fields are
interpreted by the helper.

The texture set has one element and selected index zero. Its actual texture is
**ArcColorTexture**, vtable `0x114a39c`, rather than the initially permitted
ArcSingleTexture. The initial helper correctly stopped at that unknown class.
Static qualification of the color clone's direct delegation now permits copying
its `+0x5c` resource reference. The actual target class and context readiness
remain unknown until another copied observation; no arbitrary resource fields
are read. The updated helper/observer/recorder suite passes **117 tests** and Ruff.

This evidence establishes the selected model's simple static resource shape and
supports further clone qualification independently of placement. It does not
establish owned native references, GL context/thread admission, queue lifetime,
rendering, collision validity or placement acceptance.


## ArcImage metadata and row rebuild

Static factory `0x18d340` and constructor `0x18d450`, plus RTTI, qualify ArcImage
primary vtable `0x11490f0`. ArcColorTexture getter `0x1df630` reads the target's
`+0x44` texture name; `0x192310` reads status byte `+0x51`. The reader now records
only for that exact target class: width/height at `+0x38/+0x3c`, name `+0x44`,
and raw status bytes `+0x50/+0x51`. It does not call these getters or export image
payloads. A nonzero name or status byte is not proof of a usable texture in the
preview's current GL context. No live ArcImage metadata has yet been captured.

The coordinator's later user-driven selected drag rebuilt the row and entry,
while the same deed key and model remained. Both native selection fields and
scene selection became zero. No successful placement is inferred. A renderer
must cancel on that generation/selection change even if the asset/model pointer
is unchanged. The resource helper deliberately reacquires one owned entry by key
and reports its new selection state; it never caches the old row/entry address.

Focused helper/observer/recorder validation now passes **121 tests** and Ruff.
The full host suite at `57d43f0` (before the four ArcImage cases) passed **3,493
tests**, **20 skipped**, **756 subtests**. These remain source and copied-data
checks; no native preview has been built, deployed or visually accepted.

## Queue phase and owner-thread continuation

Static review of the alternate producer found seven direct call sites. Each is
preceded by a non-main depth clear: six cube-face paths at clear RVAs `0x796d94`,
`0x796e2a`, `0x796ec0`, `0x796f5c`, `0x796ffc`, `0x797094`, and the reflected pass
at `0x79764c`. The masks include the depth bit. The existing `StrongClear`
invalidates the main camera and main-scene authority on such a clear. This
supports using a single valid reviewed main-clear generation to distinguish the
main drain, together with matching context/camera/owner and no nested drain.
A shared drain return alone remains insufficient. There were no absolute-address
references to the alternate producer or its thunk in the inspected image; this
xref result is not a blanket guarantee about arbitrary runtime function pointers.

Main queue construction/destruction uses complete window `+0xfc`. Its ordinary
reset `0x4d9a00` and window destructor's equivalent `0x773bd0` return tree nodes
without reading the wrapper payload; destructor cleanup `0x7a1940` also frees
only the sentinel. Static pool wrapper destructor `0x1cab30` writes its base
vtable and does not release or dereference the borrowed render. Pool reuse,
queue-node disposal and render-reference release must therefore remain separate.

A possible explicit retirement path is to track exactly the wrappers/nodes added
for private render copies, then remove those nodes after the outer main drain
using native tree erase `0x4d9a70` on the owner thread. That method rebalances and
returns a 20-byte node; it does not release render payloads. This is a **candidate
implementation contract**, not code already invoked or proof that a shader never
retains additional data. Before adopting it, verify current node membership and
payload identity, exclude special submissions/callbacks, track nested drains,
and quarantine uncertain enqueue/erase outcomes rather than release early.

The existing native update service runs only after the movement runtime has
verified HWND process/thread identity and observed the scene on that owner.
This service can own capture, native retains/cloning and candidate pose updates;
a furnishing service would need its own registration, without replacing the
vendor callback. Render admission must also compare the current render thread
to that owner and validate the current context and unchanged actor parent. Merely
copying `NativeScene` from another thread never acquires ownership.

`StopStrongCelShading` restores ordinary GL hooks under a callback lease barrier.
That barrier covers extension callbacks, not the native interval after enqueue.
Therefore an in-flight native preview cannot depend on those hooks surviving
Stop. Cleanup observation must remain process-pinned until retirement is proven,
or Stop must defer retirement to a confirmed owner boundary. The extension
already pins its module, and context/lifetime observers use persistent hooks.
Window destruction terminates ordinary movement updates, so it must also
invalidate preview admission and explicitly handle outstanding ownership. A
missed/uncertain cleanup boundary must not lead to cross-thread native release,
unbounded replacement copies or reuse after restart. No native hook is enabled
until these conditions are implemented and exercised.
