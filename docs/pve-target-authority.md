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
relation, ownership, or attackability, and is not yet wired into the live `/pve` observation loop.
Therefore the live launcher does not yet enable
`require_verified_target_authority`.

Do not fill this gap with display names, health totals, pointer ordering, target-cycle position,
model appearance, or proximity. The existing native identity foundation requires exact structural
joins.

## Native calibration sequence

The remaining live bridge should be added in this order:

1. Project the ownership graph through `NativeEntityIdentityMap`.
2. Calibrate the client field or protocol state that proves attackability and hostile relation.
3. Wire the revisioned native authority snapshot reader into the coherent PvE observation boundary.
4. Enable strict authority in passive observation and plan-only traces before allowing live combat
   input.

The activation gate is complete when mixed player/NPC/group fixtures and live passive traces show
that only positively verified hostile NPCs receive accepted authority decisions.
