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

## Current live limitation

The current WonderBane population reader proves living `ArcCharacter` state, exact position,
selected/action-target tokens, and protected service roles. It deliberately does not claim a
verified matching object type/UUID, player-versus-NPC category, hostility relation, ownership, or
attackability field. Therefore the live `/pve` launcher does not yet enable
`require_verified_target_authority`.

Do not fill this gap with display names, health totals, pointer ordering, target-cycle position,
model appearance, or proximity. The existing native identity foundation requires exact structural
joins.

## Native calibration sequence

The remaining live bridge should be added in this order:

1. Calibrate object type and UUID on the local player and every loaded `ArcCharacter`, then prove
   that those values match the exact keys already present in group-roster records.
2. Calibrate a structural player/NPC discriminator and retain unknown values explicitly.
3. Project the exact party roster and ownership graph through `NativeEntityIdentityMap`.
4. Calibrate the client field or protocol state that proves attackability and hostile relation.
5. Materialize one revisioned `PvETargetAuthoritySnapshot` inside the coherent PvE observation
   boundary.
6. Enable strict authority in passive observation and plan-only traces before allowing live combat
   input.

The activation gate is complete when mixed player/NPC/group fixtures and live passive traces show
that only positively verified hostile NPCs receive accepted authority decisions.
