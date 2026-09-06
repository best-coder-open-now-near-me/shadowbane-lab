# PvE target authority

`/pve` now has an explicit positive target-authority contract in addition to the existing
selected-target health, position, and service-role guards. The strict gate is opt-in until the
remaining native identity channels are calibrated; existing live profiles preserve their current
behavior and do not silently claim hostile-NPC proof.

## Strict admission contract

`PvETargetAuthorityEvidence` records one revisioned claim for one opaque target token. A strict
`PvEController` admits the target only when the same coherent observation proves all of the
following:

- selected-target health is positive;
- native selected-target identity is available, is an `ArcCharacter`, and has no protected
  service role;
- both the target and local player have non-null `NativeObjectKey(object_type, object_uuid)`
  identities and those identities differ;
- the target is positively classified as an NPC rather than a player, pet, summon, or unknown
  character;
- the resolved relation is `ENEMY`;
- exact party membership is known false;
- friendly ownership is known false;
- native attackability is known true; and
- the evidence carries explicit provenance.

Missing data is rejection, not permission. `PvETargetAuthorityDecision` preserves every exclusion
rather than collapsing failures into one boolean. Population candidate quarantine also records the
authority exclusions that caused the skip.

A replay or focused unit test can use `StaticPvETargetAuthorityEvaluator`. Runtime integrations
should implement `PvETargetAuthorityEvaluator` over a coherent, revisioned native snapshot; the
evaluator is read-only and never dispatches client input.

## Exact identity and affiliation adapter

`PvETargetAuthoritySnapshot` connects the strict gate to the repository's existing
`NativeEntityIdentityMap`, `AffiliationSnapshot`, `RelationResolver`, and ruleset-owned
`RelationPolicy`. `PvEAuthorityCharacterRecord` supplies the separately proven token-to-object,
player/NPC category, and attackability facts.

The snapshot declares party, ownership, and relation completeness independently. A missing entity
binding or a false completeness declaration produces `unknown`, not a negative affiliation claim.
For example, an incomplete party snapshot yields `party_status_unavailable`; it never defaults to
"not grouped." `SnapshotPvETargetAuthorityEvaluator` then materializes the exact authority evidence
and runs the same strict decision function used by replay fixtures.

This avoids a second PvE-only relation implementation and prevents pointer, display-name, health,
position, or roster-order heuristics from entering combat admission.

## Durable authority evidence

When an authority evaluator is configured, every controller decision carries the authority result
that was evaluated from that same observation. Population candidates quarantined during the step
also carry their typed rejection and the exact authority exclusions that caused it.

The public `PvERunner` still inherits the canonical runtime dispatch loop. It enriches only trace
construction, producing a `PvEAuthorityRunTraceStep` when authority or same-step target rejections
exist. Its serialized payload adds:

- `target_authority` — the complete accepted/rejected authority decision, exact object identities,
  revision, provenance, relation, party/ownership/attackability facts, and exclusions; and
- `target_rejections` — every candidate quarantined by that controller step, including validation
  wait, population generation, selected token, and authority exclusions.

The ordinary final evidence array and the continuous JSONL journal both call the same
`step.as_dict()` path, so these fields survive either evidence mode. Steps with neither authority
nor target rejection remain ordinary `PvERunTraceStep` instances and preserve the existing payload
shape. The trace addition is optional and additive; it does not reinterpret older evidence.

## Current live limitation

The current WonderBane population reader proves living `ArcCharacter` state, exact position,
selected/action-target tokens, protected service roles, and the stable native object type/UUID for
the local player and every accepted loaded character. A live party-roster join proves object type
at `+0x18` and object UUID at `+0x1C`; the latter also distinguishes calibrated player value `53`
from NPC value `37`, retaining every other value as unknown. The reader rejects null, duplicate,
stale, or same-address-reused keys.

`NativePartyAuthoritySnapshotReader` now samples group/population/group, rejects roster or process
identity changes across that boundary, and publishes the exact identity and party portion of a
revisioned authority snapshot. An unresolved roster key makes party completeness false; it is never
treated as proof that an entity is outside the party. This bridge does not yet claim hostility
relation, ownership, or attackability. The coherent observation source and runner
now accept an optional native group reader and party identifier. When configured,
they bracket the frame with group identity reads inside the selected-target
boundary, carry its immutable authority snapshot through the canonical dispatch
loop, and record passive authority decisions in the existing trace. Changing
coordinates, vitals, follow state, or roster ordering does not invalidate party
identity; changing membership does. Failed frames cannot reuse completed evidence.
The ordinary live `/pve` launcher does not yet configure this optional channel.
Therefore the live launcher does not yet enable
`require_verified_target_authority`.

Do not fill this gap with display names, health totals, pointer ordering, target-cycle position,
model appearance, or proximity. The existing native identity foundation requires exact structural
joins.

## Native calibration sequence

September 6 ownership investigation: registration references in the reviewed local
image `feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff`
identify these sparse descriptors. They are candidates, not ownership evidence:

| Field | String RVA | Registration reference RVA | Descriptor RVA | Runtime key |
| --- | --- | --- | --- | --- |
| `petData` | `0x12c49d4` | `0x4554a` | `0x1373148` | `3959642336` |
| `wasPet` | `0x12c49e0` | `0x45671` | `0x1373130` | `2890482807` |
| `isMinion` | `0x12c4a88` | `0x45bb1` | `0x13730b0` | `1455701066` |

The bounded read-only guest sample on reviewed running image
`bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87`
confirmed the previous local-player and selected-party-player keys. Neither
character's sparse table contained any of these three keys. This establishes only
an absent-field baseline; absence does not prove lack of ownership. The `petData`
payload layout, edge direction, and completeness remain unverified. `wasPet` must
not be treated as current ownership from its name alone.

The owner reports no pets are currently available and deferred that gameplay
check. Resume with a known pet and known owner, then prove an exact object-key join
and behavior across ownership changes before enabling ownership completeness.
Raw captures and VM credentials remain outside source control.

Source delivery: `codex/live-entity-identity-bridge` contains identity checkpoint
`e691baf` and party snapshot checkpoint `8a1395b`. These published checkpoints await
review into `codex/native-lifecycle-hardening`; `main` remains the eventual shared
merge destination. This note does not certify deployment or combat activation.

The remaining live bridge should be added in this order:

September 6 peace-restriction follow-up (same reviewed static and live images as
above): the selected-target action path at RVA `0x7d3d31` calls virtual slot
`+0xdc` on the local and selected characters before producing
`CastPower:CannotBeAggressiveInPeaceZone`. The ArcCharacter vtable entry at
RVA `0x1141738` resolves through thunk `0x215c6` to predicate `0x4b9e0`.
That predicate reads the pointer at character `+0xd40`, then the byte at pointed
object `+0x1f1`; a null pointer returns true. Zone parsing independently writes
`+0x1f1 = 1` at RVA `0x24d8e6` in the `PEACEZONE=` branch.

The passive guest check verified the predicate's exact 20 instruction bytes and
vtable entry against the static image. Both previously identified players had a
non-null pointer and stable byte value `1`. Object keys, selection slots, and
pointer/byte rereads remained stable within each sample. This is a verified
peace restriction, not a complete attackability predicate: the surrounding action
path also tests character category and pet data. A false peace byte must never
be converted to `attackable=True`, and a missing pointer must not grant permission.
No client functions were invoked or combat actions dispatched during calibration.

The `GameWindow:Enemy` string reference at RVA `0x7da805` belongs to a guild/nation
dialog path; it does not independently establish hostile-NPC authority. The
`CannotAttack` string at RVA `0x12d0aa0` registers a token at `0x158600`; its name
alone does not establish a character flag or pairwise attackability check.

1. Project the ownership graph through `NativeEntityIdentityMap`.
2. Calibrate the client field or protocol state that proves attackability and hostile relation.
3. Configure the live launcher's authority channels after their remaining facts are calibrated.
4. Enable strict authority in passive observation and plan-only traces before allowing live combat
   input.

The activation gate is complete when mixed player/NPC/group fixtures and live passive traces show
that only positively verified hostile NPCs receive accepted authority decisions.
