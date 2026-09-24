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
adjusted reference interface. ArcColorTexture and ArcAnimatedTexture have
separate implementations. Do not claim all materials are independent or treat
an archive texture-type value as the loaded native class. No texture bytes or
client binaries are required in published source.

The next coordinator-owned snapshot, once ordinary selection works, should bind
the selected entry/deed/model and occupied structure in one process lifetime,
then qualify the model's root render, bounded children, callback/feature flags,
texture-set and actual texture classes, shared resource readiness and reference
interfaces. No clone or draw call is needed for that read-only evidence. Owner
update/render thread and context evidence must separately establish the proposed
runtime boundary. Current captures establish model identity and occupancy only;
they do not contain this resource graph or a selected native row. Runtime
activation/visual qualification cannot proceed from the existing capture alone.

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
