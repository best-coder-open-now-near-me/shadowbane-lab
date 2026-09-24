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

Clone eligibility also needs the two copied render property maps at `+0x120` and
`+0x12c` qualified. Their counts at `+0x124/+0x130` and copy paths were visible in
`0x1c1e40`; the current copied helper has not observed them. Nonempty maps cannot
be assumed inert. The copy's `+0x148` clears bit 0 and bits 6/7, preserves source
bits 1/2/3/5 and sets bit 4. This is rechecked against the instructions; the
runtime must validate the resulting clone rather than assume all source flags
were copied. The shared mesh index-zero change remains a separate gate.

## Current todos

- Complete: owned scene-collection observer (`01397ac`), 169 focused tests.
- Complete: exact wrapper comparator/erase and standard static shader normal-end
  qualification recorded here, against the reviewed image.
- Active: qualify remaining clone property-map values and resource/shader
  eligibility, then finalize the exceptional/reentrant retirement contract.
- Pending: coordinate shared wiring ownership with the furniture response task,
  implement the coherent native preview slice, run native lifecycle/failure tests,
  and obtain real in-building visual acceptance with no placement messages.

This checkpoint changes documentation only. The annotated methods and their
callees were inspected directly; no runtime test is claimed for these conclusions.
