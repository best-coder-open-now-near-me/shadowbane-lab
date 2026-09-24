# Furnishing render ownership qualification

This continues the [native render contract](furnishing-native-render-contract.md).
It records static evidence, not an enabled renderer. All method/vtable addresses
below are RVAs in the reviewed September 24 image, SHA-256
`6347b420c6c151995f168f16fd1624408dd8911698d11a4a74b26d211fb49f19`.
No native calls, VM observation, hooks, shared runtime edits or deployment were
performed for this checkpoint. Main remains the integration destination through
draft PR #35. Private annotated evidence is retained locally at
`artifacts/furnishing-preview/queue-shader-retirement.txt`; the client binary and
private evidence are not published.

## Queue submission is a transaction with observable outcomes

Static producer `0x1cb020` increments wrapper-pool usage before metadata builder
`0x1c4150` can reject submission. Pool capacity, opacity and resource gates can
also skip individual renders. A used pool slot therefore is not evidence of a
queue insertion. The source child traversal continues even when the parent skips.

Metadata writes wrapper texture key `+8`, render sort group `+0xc`, alpha marker
`+0x10`, zero depth field `+0x14` and shader pointer `+0x18`. The shader pointer
is freshly assigned by render virtual `+0x2c`; a null optional shader argument
to `0x1c4340` does not leave the previous frame's shader in that field. These
native routines also obtain/release temporary texture references under the
texture-set lock. Copying their inputs externally does not acquire that lock.

Wrapper comparator `0x1c0dc0` orders alpha mode, applicable depth, signed shader
rank at shader `+8`, shader address, texture key and group, then wrapper address.
Thus separate valid wrapper addresses do not normally collapse just because
material keys match. The generic insertion routine `0x4d9830` still exposes no
reliable successful-insert result to this caller. It dispatches the wrapper's
comparator virtually, so exact wrapper type and shader metadata remain gates.

For a future owner-thread transaction, record the root, main queue and sentinel,
frame/context/selection generation, pool base/capacity/used count, and the owned
private render tree. Bound and validate the existing queue before calling native
enqueue. After it returns, inspect the bounded new pool interval and the entire
bounded queue; identify each exact wrapper whose `+0x1c` points into that private
tree. Require the expected wrapper class, qualified shader and exact node/payload
membership. A partial, rejected or uncertain submission must not be reported as a
visible preview. Disallow shadow/special flags and unqualified child dispatches,
which can submit outside this receipt. Do not rewind the global pool counter.

## Erase must be by current membership

`0x4d9a70(queue this, node)` calls rebalance `0x8edd0`, frees the returned 20-byte
node, and decrements queue count **unconditionally**. It performs no membership
check and never releases a wrapper/render. Passing a stale node or sentinel can
corrupt the native queue; it is not an idempotent cleanup operation.

The inspected two-child erase path transplants the successor node into the
removed node's tree position; it does not copy or release wrapper payloads.
Nevertheless, cached edges become invalid after every erase. Rewalk/revalidate
current root/parent/child/extremum links and count before each exact removal,
and verify count reduction and absence afterward. Keep the native render retain
until all of its nodes are absent and no admitted drain can still use a wrapper.
Queue reset and wrapper-pool reuse remain distinct events. Neither permits using
old wrapper addresses to identify a new frame's allocations.

## Shader ownership and the normal drain end

The ordinary static draw creates stack parameters containing opacity, reflection
flag, material bias, private texture-set pointer and a temporarily retained render.
Shader setup `0x4effe0` stores those parameters as a **borrowed** pointer at shader
`+0x10`. It retains the shared template at shader `+0xc`; the selected mesh is
borrowed into shader `+4` by `0x1bf360`, with lifetime supported by that template.
The temporary render retain is released inside `0x1cb700` before its return.
Do not treat shader fields as an additional owned reference to the preview.

| Reviewed shader | Primary vtable | Shutdown | Finding |
| --- | --- | --- | --- |
| ArcShaderStaticNoAlpha | `0x1149ca8` | `0x4f6b50` | Uses GL/native state guards, not borrowed draw parameters |
| ArcShaderStaticWithAlpha | `0x1149c84` | `0x4f6590` | Also restores blending; does not read borrowed draw parameters |

Their shutdown helpers `0x4f2710`, `0x4f2810`, `0x4f2770` use only each guard's
byte and native state/GL functions. Shader shutdown does not clear its retained
template or borrowed parameter field. The next setup overwrites parameters
before draw. This supports the normal-return path for these exact families; it
does not qualify arbitrary shader subclasses, callbacks, asynchronous consumers,
context destruction or exceptional unwinding.

Drain `0x79c730` finishes node traversal, calls `0x51c490` at `0x79c7da`, then calls
glPopMatrix with return `0x79c7f7`. `0x51c490` shuts down the current shader through
virtual `+0x10` and zeros global `0x16a9dd4`. After that pop, the drain only restores
its stack and returns; it has no further queue access. A persistent pop observer
can therefore be a normal-path retirement boundary after the original pop returns,
provided the matching outer main drain, owner, context and submission receipt
remain valid. It must not infer this from the shared return address alone.

The ColorTexture bind slot `+0x58` follows the official image's jump to `0x8f7202`.
It can call load slot `+0x44` when resource `+0x5c` is null; otherwise it binds the
ArcImage texture name `+0x44` and target `+0xfc` through native state management.
Consequently, a preview must require a retained, exact-class resource and usable
current-context texture before submission; it must not use the draw path to load
missing resources. ArcImage status bytes alone remain insufficient readiness.

## Durable runtime boundaries still required

The intended owner is the verified HWND/native update thread. External snapshots
are diagnostics only. A private native render copy must be reacquired when row,
entry, selected deed, occupied building, floor or context generation changes.
Character occupancy identifies the building; the HUD is a consistency check.

The lifetime states and release requirements are:

| State | Ownership and permitted transition |
| --- | --- |
| Empty | No native retain or queued pointer; may acquire on verified owner |
| Owned | One qualified private render tree; no queued uses; pose changes only here |
| Submitted | Immutable tree and exact current-frame queue receipt; no release |
| Retiring | Matching outer drain has ended; validate and erase exact current nodes |
| Quarantined | Uncertain native call, generation, membership or completion; no reuse, replacement allocation or guessed release |

Cross-thread Stop closes new admission but must leave persistent cleanup
observation available. Existing render callback leases do not cover the native
interval between separate push/pop callbacks. A future furnishing push/pop hook
must remain independent of ordinary cel-shading Stop and preserve any existing
IAT ownership; never patch executable text or overwrite another feature's hook.
Nested/alternate drains cannot consume the outer main receipt. Window/context
loss invalidates admission and requires an explicit owner-thread recovery proof;
if absent, retain bounded quarantine until process teardown. A new Start must not
silently discard the outstanding receipt or create more copies.

Further inspection corrects the initial two-map hypothesis: `+0x120` is an
owned byte string (begin/end/capacity at `+0x120/+0x124/+0x128`), and `+0x12c`
is one tree with count at `+0x130`. The native writer identifies these as vertex
program name (`VPNAME`) and parameters (`VPPARAM`); `+0x114` is its active flag
(`VPACTIVE`). The copy allocates name length plus terminator, copies the bytes
through `0x1d2b60`, and appends NUL. **`+0x124` is an end pointer, not a count.**

Tree copy `0x1d0880` creates independent nodes through `0x1d1a60`. Payload copy
consists of five DWORDs: an integer key at node `+0x10` and four float values
at `+0x14..+0x20`. The parser writes at `0x1c76c0`, writer `0x1c7f28` and serializer
`0x1c2ba3` confirm the four floats; copy/destruction make no payload retain or
release calls. This removes the suspected hidden native-object ownership in
these fields. The name and parameter values still need bounded source validation,
and active vertex-program execution is not qualified by ordinary static shader
shutdown. Current live evidence does not include these fields. A nonempty name
alone is not proof that the program is active.

The copy's `+0x148` clears bit 0 and bits 6/7, preserves source bits 1/2/3/5 and
sets bit 4. This is rechecked against the instructions; the runtime must validate
the resulting clone rather than assume all source flags were copied. The shared
mesh index-zero change remains a separate gate.

## Current todos

- Complete: owned scene-collection observer (`01397ac`), 169 focused tests.
- Complete: exact wrapper comparator/erase and standard static shader normal-end
  qualification recorded here, against the reviewed image.
- Complete: clone vertex-program string/map payload ownership qualified; no
  hidden object references in the copied payloads.
- Complete: bounded queue receipt implementation and native failure-path tests.
- Active: implement owner capture/private render lifetime, including the remaining
  resource/shader eligibility and exceptional/reentrant retirement requirements.
- Pending: coordinate shared wiring ownership with the furniture response task,
  implement the coherent native preview slice, run native lifecycle/failure tests,
  and obtain real in-building visual acceptance with no placement messages.

This checkpoint changes documentation only. The annotated methods and their
callees were inspected directly; no runtime test is claimed for these conclusions.


## Native queue receipt implementation checkpoint

`furnishing_queue.h/.cpp` now implement the durable queue ownership component.
It is linked into the full extension and has no startup/render hook yet. Its
caller supplies exact-build read/owner/erase operations, retains the private
render tree, and proves the matching outer drain/shader boundary before retirement.
The component itself never acquires, releases, draws or modifies a render.

The receipt validates up to 8,192 native queue nodes and 64 private renders,
including parent/child/extremum links, unique nodes, red/black invariants and a
reverse read check. It reserves room before native entry, distinguishes prepared
from entered transactions, and matches inserted wrappers to the exact newly used
pool interval. Pre-existing queue nodes and payloads must remain intact. Even a
pre-entry discovery that a supposedly fresh private render is already queued
quarantines that ownership rather than authorizing release.

Retirement checks the frame ticket and owner, rewalks the current tree before
every erase, and proves exact removal without damage to other entries afterward.
A failed or uncertain erase is never retried. Reentry is refused while mutating.
Partial insertion is counted accurately; consumed slots with no insertion do not
invent draw success. Quarantine forbids replacement transactions and release.

The full extension build and native test target passed using reviewed Visual
Studio 2022 Win32 Release with warnings as errors. It exercises normal and partial submission, two-child
rebalancing, the 8,192-node bound, malformed topology/red-black state, replaced
wrappers, changed reads, wrong tickets, pre-existing private uses, owner loss,
failed/partial erase and cleanup reentry. The package gate now requires this
native test; all 199 package-gate host cases and repository Ruff pass. Earlier
recorder integration passed 455 combined focused host cases. Local build evidence
is retained under `artifacts/furnishing-preview/native-build-2022`; the initial
2026-toolchain smoke build remains separately at `native-build` as non-authoritative
scratch evidence. Neither build is an installable preview delivery.

Next active item: implement owner-captured selection/pose and private render
retains/cloning around this receipt, then persistent frame/context integration
and the Preview user affordance. Shared native versions remain 1.8.28 inherited
from recorder source c764e22; no new version or package has been assigned here.
The complete preview, lifecycle validation and live visual acceptance remain open.


## Native owner selection checkpoint

`furnishing_selection.h/.cpp` implement the synchronous native capture boundary.
Its caller must supply the verified HWND/native-update owner, current lifetime
watch and exact reviewed image. The capture does not itself grant a lease or call
native code. It validates character occupancy first, then requires the one owned
Furniture HUD to refer to that exact structure. An open HUD cannot keep a building
eligible after the character leaves it.

The capture validates the complete bounded HUD, child and row ownership chains,
the HUD-selected deed and static model/root, the layout name/mapping values, the
selected floor within the occupied structure, and the structure's finite world
TQS. It rereads all consumed bytes in reverse and rechecks owner/lifetime admission
before returning borrowed selection data. Native retain/clone callers must keep
and recheck that authority; copied pointers are not ownership. Row, model, floor,
building, actor or lifetime changes invalidate selection identity.

Full extension and selection tests pass in VS2022 Win32 Release with warnings as
errors. Tests include all collection bounds together (128 HUDs, 512 children,
128 rows), duplicate ownership, detached/rebuilt selection, stale occupancy,
invalid floor/transform/layout, every consumed field changing during capture,
owner loss, and read/admission reentry. The mandatory package gate includes this
suite; 205 host gate cases and Ruff pass. No native calls, renderer wiring,
version change, package, deployment or live visual acceptance are claimed.

Next: private render resource qualification and owner-thread clone/release, then
pose, persistent frame/context cleanup and the Preview affordance. This remains
unfinished preview work in PR #35 targeting main; the recorder dependency remains
unchanged at source c764e22 (native 1.8.28 / host 0.3.48).


## Private render ownership transaction checkpoint

`furnishing_render_owner.h/.cpp` compose selection identity and queue receipts into
one persistent ownership transaction. This is the production lifetime boundary;
reviewed-image native operation adapters and resource/shader qualification are
still required before it can be registered with owner/render callbacks. The
component is linked, but startup does not instantiate or enable a preview.

It retains the source model for the entire private render lifetime, keeping shared
resources alive through private destruction. It publishes reference slots before
native entry, refuses replacement while owning any copy, only changes pose when
unqueued, and only releases after receipt retirement on the acquisition owner and
graphics context. Private release precedes source-model release. A wrong drain
ticket is ignored; an uncertain call or cleanup quarantines the bounded transaction
without retry or replacement. Invalid private postconditions also quarantine.

Cross-thread Close only closes admission. It does not release or remove cleanup
observers. A normal matching drain can still retire after Close or a selection
change and then release on its owner/context. Context invalidation is owner-thread
only and preserves uncertain ownership. Reopening requires a completely empty
transaction. The runtime must still prove the outer main drain and shader shutdown;
this component cannot infer that proof from a ticket alone.

All three furnishing native suites and the full extension build pass with VS2022
Win32 Release and warnings as errors. The new suite uses synthetic operations to
exercise pre/post-entry failures in retain, clone, compose, enqueue and release;
partial/no insertion; cleanup faults; source/clone rejection; native reentry;
selection/Stop changes during calls; and context loss. It never executes the game
or establishes visual acceptance. The package gate requires this suite; 211 host
gate cases and Ruff pass.

Next active item: reviewed native operation adapters and resource/shader gates,
followed by cursor/floor pose, persistent frame/context callbacks and Preview
controls. Version/package coordination, native integration validation and real
in-building visual acceptance remain pending. No new versions or VM changes.


## Reviewed native call adapter checkpoint

`furnishing_native_calls.h/.cpp` provide the actual x86 adapters for retain,
recursive clone, adopting release, private transform composition, static enqueue,
wrapper-pool reads and exact queue erase. Configuration requires one of the two
reviewed September 24 file hashes and the loaded-code seal. It executes no game
code. Binding requires the native window's thread/process, a current GL context,
and its window drawable; every operation rechecks that owner/context.

The adapter checks exact primary, virtual-base and reference interfaces before
object calls. Static models must still use the existing lifetime observer's
registered finalizer hook; private ArcRenderObject finalizers must match their
reviewed native slot. The observer exposes an owner-only reference ABI check for
independently borrowed/retained objects. It does not watch or retain those objects,
and no observer lock is held across a native call. Terminal/broken observers reject
this check. Selection/resource ownership remains the caller's separate obligation.

C++ and Windows exceptions are contained without rewriting output/reference slots.
Thus an output published before a fault, or a release consumed before a fault,
remains visible to the RenderOwner quarantine rules. The adapters do not replace
resource/shader qualification, exact queue membership, context generations or the
matching outer-drain proof. They remain unregistered; no preview game calls occur.

Validation: full extension build and 47 native tests pass with VS2022 Win32
Release and warnings as errors (43 movement-lifetime cases plus four furnishing
suites). The adapter suite uses controlled x86 stand-ins to check ECX/stack argument
layouts, recursive clone, render secondary-interface adjustment, release adoption,
reference-slot behavior, wrong owner/context/interface rejection, and C++/SEH
faults. No client binary is executed. All 217 package-gate host cases and Ruff pass.

Next active item: source/private resource and shader eligibility, then cursor/floor
pose, persistent frame/context runtime and Preview controls. No version assignment,
package, VM change or live visual acceptance has occurred in this lane.
