# Native combat entry contract — September 28

This is an offline qualification of the ordinary manual attack path, not a live
gameplay or deployment receipt. The reviewed client image has SHA-256
`7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f`.
All addresses below are RVAs; preferred-VA disassembly operands use base `0x400000`.
Build identity must be independently admitted by the native image verifier.

## Ownership and native entry

The existing native owner-update service owns selection, attack, observation, and
cancellation under the captured movement Grant. The generic transport-worker
action dispatcher is not an execution boundary for this transaction. Retain the
exact local actor and freshly reacquired target; selection at `0x498730` consumes
its input reference, so it receives a separate owned reference. Revalidate the
scene, full player identity, saved-intent fence, and complete party roster after
selection and immediately before attack admission.

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
