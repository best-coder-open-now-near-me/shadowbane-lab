# Native combat effects — October 1, 2026

The client has a persistent actor-owned effect collection and an incoming
effect-list update path with remaining semantic gaps. There is **no production
active-buff observer** yet.
The facts below do not authorize buff maintenance, identify an expired buff, or
prove Shot to the Leg applied a snare.

This was a bounded offline inspection of exact prepared client **1.3.38.13**,
SHA-256 `0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d`.
Private image:
`artifacts/guard-deploy/client-update-20260930-late/review-prepared-sb.exe`.
Official original SHA-256:
`e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8`.
All instruction addresses below are RVAs; field offsets and sizes are hexadecimal.
No native function, VM action, live probe or effect mutation was executed for
this audit.

## Verified storage and lifecycle

- Actor constructor `97870` initializes collection storage at actor `+58C`
  (`97907..97914`) and an embedded `ArcEffectListIF` interface at `+588`
  (`97919`). The actor's derived interface table is `1141DF0`, published
  at `979D3`. Its relevant callbacks resolve to `9B530` and `9B9D0`.
  `9B9D0` explicitly recovers the actor with interface-pointer minus `588`.
- Let `C = actor + 58C`. Constructor `A0B20` initializes a primary vector
  at `C+0/+4/+8` (begin/end/capacity), with eight-byte entries containing a
  definition lookup key and an owned record pointer. Secondary indices are at
  `C+C` and `C+18`; `C+24` is an aggregate mask, not an entry count.
- Add callback `9B530` allocates a `78`-byte record, constructs it through
  `14E410`, and inserts through `150590`. Existing-record comparisons may
  reject or replace an add; exact-record replacement removes through `1507B0`.
  Remove callback `9B9D0` invokes `1508D0`, matching the primary key plus
  record `+24` and tagged source fields before destroying/freeing the record
  and rebuilding indices. Records must not be collapsed into a set of power IDs.
- Both callbacks invoke `D9090`, which refreshes actor `+4E8` through its
  owned-reference path. This does not establish attribution of a resource delta.
  Actor destructor `97D50` reaches collection destructor `14FF90` at
  `97F56`; it destroys/frees primary records through `1531A0/14E580` and
  releases the collection's buffers. An allocation address is not a durable
  effect-instance identity.
- RTTI identifies incoming `ArcUpdateEffectsMsg`, table `11598A4`.
  Decode `3C4F40` reads the target key into message `+78` and decodes the
  effect-list payload referenced by message `+74`, through `151A70`.
- Process `3C4D80` resolves that key through the current native manager
  `16A7C3C`, checks the resolved object's native type, calls actor helper
  `9A120` at `3C4DDE`, then calls `99940` with the decoded list at
  `3C4DE9`. This is an explicit object path independent of UI selection.
  The manager is distinct from world global `1389028`; do not conflate them.
- `9A120` passes actor `+58C` and the actor to `1512B0`, which snapshots
  existing primary record pointers and calls each definition's virtual slot
  `+14`. `99940` processes incoming definitions through virtual slot `+C`,
  alongside visual work in `99D20`. The concrete apply/undo callbacks still
  need qualification; this is not yet proof of unconditional full replacement.
- Collection decoding `151A70` uses a separate pointer vector at
  `C+28/+2C/+30`, allocating `50`-byte records. `99940` resets the input
  collection's primary records/indices through `150F70` and iterates its decoded
  vector. `9A0F0` can pass the actor's own collection into this rebuild path.
  At the end, `150EE0` destroys the actor's transient decoded records and resets
  that vector's end. An empty decoded vector does not mean no active effects.
- RTTI also identifies `ArcRemoveEffectMessage`, table `1156AC4`, but its
  process method `38F4E0` only returns zero. The name supplies no incoming
  removal or expiry authority.

The primary records participate in native effect-property evaluation, with a
descriptor at record `+0`, property data at `+14`, and another definition
reference at `+68`. Tagged source data begins at `+28`; its tag meanings and
identity domains are not yet established. Add construction writes a double at
`+60/+64` from a computed duration plus client clock `16A2D70`. This is a
candidate absolute time, not a qualified expiry or remaining-time contract.

These paths establish persistent ownership distinct from decoded and visual
state. They do not establish stable server instance IDs, every mutation/reset
path, full-list completeness for remote actors, or which entries are temporary
buffs. `151D20` (called by `98278`) is text serialization, not a further
network decoder or reset source.

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

1. Resolve concrete definition virtual slots `+C/+14` reached by
   `99940/1512B0`, all `9A0F0` callers, and actor reset/reload paths.
   Qualify apply/undo, refresh and stacking semantics, full-update completeness,
   and any temporary empty state during rebuild. The verified add/remove and
   destructor paths alone do not close this mutation boundary.
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
