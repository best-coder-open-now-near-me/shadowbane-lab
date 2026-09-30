# Native combat entry contract — September 28

This is an offline qualification of the ordinary manual attack path, not a live
gameplay or deployment receipt. The reviewed client image has SHA-256
`7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f`.
All addresses below are RVAs; preferred-VA disassembly operands use base `0x400000`.
Build identity must be independently admitted by the native image verifier.
The combined September 28 candidate also admits prepared client 1.3.38.12 at
`2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289`.
The [complete-file comparison receipt](../evidence/pvp/combat-client12-qualification-20260928.json)
proves that only one embedded version byte differs; callback bodies and class
tables are unchanged. The loaded-image verifier remains mandatory. Original
unprepared images and unknown hashes do not receive combat capability.

## Ownership and native entry

The existing native owner-update service owns selection, attack, observation, and
cancellation under the captured movement Grant. The generic transport-worker
action dispatcher is not an execution boundary for this transaction. Retain the
exact local actor and freshly reacquired target; selection at `0x498730` consumes
its input reference, so it receives a separate owned reference. Revalidate the
scene, full player identity, saved-intent fence, and complete party roster after
selection and immediately before attack admission.

Supported callers serialize complete workflows for each exact client. The managed
worker starts its next operation only after the current operation thread exits
and its terminal receipt is published (`ExactClientWorkerRuntime.serve` in
`src/shadowbane_lab/manager/worker_runtime.py`). A cancellation that cannot join
the operation exits the worker; it does not admit a successor. Standalone vendor,
guard, funding, and navigation sessions each open their own native action
transport. Its `_claim_host_lease` in
`src/shadowbane_lab/client_extension/action_channel.py` rejects any live producer
lease, including another session in the same host process. Listed combat instead
uses its existing movement session and exact Grant.

The read-only source review also checked `RunNativeOwnerServices` in
`native/wonderbane_extension/native_owner_services.h` and both native runtimes.
Their callbacks run sequentially on the owner update, but callback ordering does
not provide mutual exclusion across outstanding vendor and combat transactions.
A low-level caller sharing one producer lease must finish or confirm cancellation
of one workflow before starting the other. Concurrent vendor/combat workflows on
one lease are outside the supported caller contract; transport command completion
alone does not establish workflow completion.

Ordinary action 1551 dispatches through `0x7ca9c0` to `0x7d3c10`. It preserves
native legality checks, including mode and peace-zone restrictions. The dispatch
return value does not prove attack submission. Mode changes can invoke synchronous
callbacks before the handler reloads its selected target. A scoped factory gate
must therefore validate the actual actor, target, and key at the actor's D0 slot,
and its CC follow-up must reject an invalidated or denied scope.

The reviewed D0 implementation is `0x5f4b0`. Its melee request copies the retained
actor key into request `+0x70` and the supplied target key into `+0x78`. The factory
scope must correlate that exact returned message with the actual outbound append
slot at `0x114cea4`. Passing the sender is insufficient: its unavailable-controller
path drops the message. A receipt means only that this particular request entered
the client's outbound queue; it proves neither server acceptance nor damage.

## Exact-key target acquisition - September 30

Combat reacquires its immutable player key through the ordinary ArcWorld registry
resolver at RVA `0x1fcc80`, also used by ArcTargetedActionMessage. Its thiscall
receiver is the captured world; the two arguments are an output-reference slot
and the complete two-word key. It returns the same slot containing one retained
ArcObject reference, or null when the key is absent. The native registry is
`world+0x94`; its hash and equality compare both key words at `object+0x18`.
The [exact-image evidence](../evidence/pvp/combat-registry-contract-20260930.json)
records fingerprints and the supported ownership boundary.

The former building/door spatial query used `world+0x164` and a coarse 1024-unit
X/Z acquisition box. Spatial leaf membership and multiplicity are not the
character registry contract. The replacement intentionally removes that coarse
acquisition dependency; it does not introduce a melee-distance rule. Fresh host
camp admission and the ordinary client's attack-legality checks remain in force.
The recorded 1.8.34 `query_match:stale` result does not distinguish missing or
multiple matches from query cleanup failure. A later passive registry census
stopped before reading the registry because the active character was unavailable;
it does not establish live registry membership or successful combat.

Lookup executes only on the existing verified owner-update thread. The inspected
lookup-to-retain closure consists of concrete hash, key, iterator and atomic
reference helpers, with no gameplay callback, message pump or allocation before
retention. This uses the ordinary native owner-world serialization contract.
The scene watch detects invalidation; it is not a registry lock. Arbitrary
concurrent registry writers and foreign modified clients are not qualified.

The output goes directly into the transaction's persistent owned slot before
native entry, so exceptions or an unexpected return ABI quarantine uncertain
ownership. After lookup, the existing checks still require the exact ArcCharacter
class, distinct player key, full first name/server, current scene and unchanged
complete party roster before selection. Selection receives a separate retained
reference. Saved-intent admission, outbound correlation and cancellation remain
under the same immutable request and movement Grant.

Selection is an admission input, not proof of whom an existing attack or cast is
hitting. A selection change currently requests cancellation as interference with
the owned workflow; it never proves that cancellation completed. Cleanup requires
fresh mode 1, action state 1 and a null native combat target. An ongoing attack or
cast after deselection must retain the cleanup obligation until those conditions
are observed. This contract does not add spell casting or infer a cast target from
selection.

The developer-only `wonderbane_extension_combat_registry_probe` executes the real
reviewed resolver and reference helpers against synthetic registry buckets and
objects. It verifies exact keys, collisions, misses, tombstones, the output-slot
ABI, returned ownership and finalization after registry removal. It neither opens
nor modifies a live client. Exact-client packaging builds and runs it for both
native profiles against original and package-prepared images; failures stop
qualification. NativeTarget regressions separately exercise transaction checks,
callback invalidation, cleanup and uncertain-reference quarantine.

## Synchronous callback qualification

The mode/action notifier `0x4520c0` invokes subscribers synchronously. D0 later
reads the global local actor before writing `+0xc1d`, so an assertion that all
notifications are deferred would be incorrect.

The reviewed registration-call inventory, native subscriber classes, and concrete
transition helpers close the supported callback paths:

- Relevant HUD callbacks update visual state or ignore these two event types.
  Other registered native input/channel/item callbacks ignore them.
- D0 passes `send=false` to its mode/action transitions; their message-builder
  branches are not reached with those arguments.
- Equipment and animation helpers copy state, update native resources, and use
  qualified rendering methods. Both render-construction paths install the same
  no-op method at the relevant render slot. The remaining predicate and proxy
  methods compare counters or return the captured transform pointer.
- Audio callbacks resolve to the native pooled-channel table, named Sound.dll
  play/stop/volume APIs, and a getter that copies the retained actor's coordinates.

No supported synchronous actor publication/clear, receive processing, or game-frame
dispatch was found on those paths. This conclusion covers the reviewed image,
native class set, and ordinary imported API semantics. It does not qualify foreign
listener registration, replacement native classes, or modified dependencies.
The current extension adds no subscriber registration to this callback family.

## Cancellation and limits

Once admitted at the scoped D0 boundary, an old-owner request may finish entering
the outbound queue. Revocation cannot recall a queued message or establish a
server-side cancellation. It prevents subsequent extension admissions and leaves
the exact old owner's local cleanup obligation intact.

Use the existing native stop pipeline for that owner. Invoke ordinary action 1558
only while the same actor is actually in combat mode 2; blindly toggling mode 1
would enter combat. Native cooldown rejection remains pending cancellation.
Local cancellation requires a fresh same-scene observation of mode 1, action
state 1, and a null native combat target. Never repair those fields by raw writes.
Confirmed scene retirement terminates the host encounter; it does not permit
resuming a replacement character's PvE run.

An exact cancellation received before its START must register a terminal request
identity before acknowledging cancellation, preventing a delayed START from
becoming a new attack. Full immutable binding equality is required for replay.

Automatic response insertion remains separately blocked on the authoritative
[server session fence](pvp-response-provenance.md). This manual-entry qualification
does not establish incoming-event character-session provenance.

## Retained evidence

Private evidence remains under `artifacts/pve-pvp-resume-20260924` in the normal
project checkout: `native-callback-closure-20260928.asm.txt`,
`native-callback-inventory-20260928.json`, and
`native-transition-helper-audit-20260928.md` with its companion disassembly.
The inventory alone is a candidate-class census, not a runtime registry proof;
the registration and concrete helper analyses are required together. Original
client bytes, disassembly, and captures are not published with source.
