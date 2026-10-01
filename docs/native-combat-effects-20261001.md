# Native combat effects — October 1, 2026

The client has an actor-owned effect interface and an incoming effect-list update
path worth qualifying. There is **no production active-buff observer** yet.
The facts below do not authorize buff maintenance, identify an expired buff, or
prove Shot to the Leg applied a snare.

This was a bounded offline inspection of exact prepared client **1.3.38.13**,
SHA-256 `0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d`.
Private image:
`artifacts/guard-deploy/client-update-20260930-late/review-prepared-sb.exe`.
Official original SHA-256:
`e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8`.
All instruction addresses below are RVAs. No native function, VM action, live
probe or effect mutation was executed for this audit.

## Concrete native ownership lead

- Actor constructor `97870` initializes collection storage at actor `+58C`
  (`97907..97914`) and an embedded `ArcEffectListIF` interface at `+588`
  (`97919`). The actor's derived interface table is `1141DF0`, published
  at `979D3`. Its relevant callbacks resolve to `9B530` and `9B9D0`.
  `9B9D0` explicitly recovers the actor with interface-pointer minus `588`.
- RTTI identifies incoming `ArcUpdateEffectsMsg`, table `11598A4`.
  Decode `3C4F40` reads the target key into message `+78` and decodes the
  effect-list payload referenced by message `+74`, through `151A70`.
- Process `3C4D80` resolves that key through the current native manager
  `16A7C3C`, checks the resolved object's native type, calls actor helper
  `9A120` at `3C4DDE`, then calls `99940` with the decoded list at
  `3C4DE9`. This is an explicit object path independent of UI selection.
  The manager is distinct from world global `1389028`; do not conflate them.
- `9A120` passes actor `+58C` and the actor to `1512B0`, which visits
  existing effect-related records. `99940` iterates decoded records, looks up
  definitions and invokes `99D20`, including visual-effect work, before
  calling `150EE0` on actor `+58C`.
- Collection decoding `151A70` uses a pointer vector at collection
  `+28/+2C/+30`, allocating `50`-byte records. `150EE0` destroys records
  in that vector and resets its end. These are not sufficient grounds to
  interpret that vector as the persistent active-buff set. Other collection
  storage, callbacks, definition references and visual state require separation.
- RTTI also identifies `ArcRemoveEffectMessage`, table `1156AC4`, but its
  process method `38F4E0` only returns zero. The name supplies no incoming
  removal or expiry authority.

These paths establish a concrete actor-owned boundary to investigate. They do
not yet establish a complete live collection schema, stable instance identifiers,
all mutation paths, or which records represent gameplay effects.

## Existing observations do not fill the gap

Native current/max resource values can establish that resource limits changed.
Even simultaneous reductions in maximum health, mana and stamina do not identify
the responsible buff, its source or whether it expired, was removed, or changed
through recalculation. Full current resources do not settle those distinctions.

Actor `+65C/+660/+664` is the qualified power-protocol initiation vector.
Its IDs can be duplicated and removed during protocol processing while an effect
continues. It is not an active-buff inventory or a skill-consumption receipt.

Existing inventory-item effect records are scoped to item instances; simulation
active effects describe the simulator. Neither is a live actor-buff observer.
Visual spell objects, displayed icons, combat text and outgoing queue receipts
also cannot supply the missing gameplay-effect semantics.

## Finite qualification and observer acceptance

1. Follow the actor constructor/destructor, full-list replacement and interface
   callbacks to distinguish persistent gameplay entries from pending decoded
   records and visual objects. Qualify complete insertion, removal, refresh,
   stacking and reset paths, including actor replacement.
2. Resolve each relevant record's effect-definition ID, instance identity,
   rank/magnitude, recipient, and source identity where actually carried.
   Establish whether snapshots are complete for the local actor and for remote
   NPCs; an absent or partial remote list must remain unknown.
3. Qualify duration/remaining-time fields and their clock, plus the removal
   paths. A complete snapshot can prove current absence. Calling that absence
   *expiry* additionally requires a qualified reason or timing transition.
4. A future observer must use the current registry-owned actor key/address
   lifetime, bounded structural reads and complete relevant rereads. It must
   reject churn, unreadable members, ambiguity and replacement; never select
   heap candidates or infer removal from a failed capture. Remote rereads do not
   provide native retained-reference ownership or defeat arbitrary ABA changes.
5. Validate with synthetic ownership/churn/duplicate/stacking/expiry cases and
   exact-image conformance evidence before any passive acceptance. Preserve
   unknown fields and reason codes instead of converting them to negative facts.

For **Shot to the Leg (power ID 563795161)**, independently qualify the native
power-to-effect-definition relationship and target-side instance membership.
An effect record must belong to the same tracked NPC lifetime. Source/request
attribution may require additional evidence even after identifying a matching
effect. Local SELF_POWER then ATTACK queue admission proves neither weapon-skill
consumption nor snare application.

The current [queued-skill implementation and acceptance record](queued-skills-20261001.md)
retain those limits. No observer, runtime change or automatic buff action is
introduced by this note.
