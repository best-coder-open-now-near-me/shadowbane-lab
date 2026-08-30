# Group targeting foundation

This foundation separates three concerns that Shadowbane powers often combine in
client-facing behavior:

1. **affiliation facts** — party, guild, nation, scenario side, ownership, and
   explicit relation overrides;
2. **relation policy** — how a ruleset maps those facts to `SELF`, `ALLY`,
   `ENEMY`, or `NEUTRAL`; and
3. **target selection** — exact affiliation requirements plus kind, life state,
   visibility, range, line of sight, ordering, and target caps.

The modules are intentionally independent of simulator action lifecycle code and
rollout/permutation generation.

## Scenario affiliation state

`shadowbane_lab.sim.affiliations` exposes an immutable, revisioned
`AffiliationSnapshot`. Party, guild, nation, and scenario-side affiliations are
symmetric set memberships. Pet and summon ownership is a separate directed,
cycle-checked graph.

`RelationResolver.facts_between()` returns exact `RelationFacts`. A
ruleset-owned `RelationPolicy` derives the coarse compatibility relation. This
keeps facts such as “same party” distinct from policy such as “party members are
allies on this server or in this scenario.”

Legacy `EntityState.team_id` values can be adapted to scenario-side memberships
without changing existing duel semantics. Permutation code should provide
scenario composition but must not infer affiliation meaning itself.

## Canonical snapshot boundary

`shadowbane_lab.sim.affiliation_codec` provides:

- `affiliation_snapshot_to_data()` / `affiliation_snapshot_from_data()`;
- `encode_affiliation_snapshot()` / `decode_affiliation_snapshot()`; and
- `affiliation_snapshot_digest()`.

Encoding is deterministic across input tuple ordering and symmetric override
orientation. Strict decoding rejects unknown, missing, and duplicate fields,
invalid UTF-8, non-standard JSON constants, and invalid model state. The encoded
bytes and digest are suitable for an opaque scenario component payload and case
signature once the simulation-case integration branch owns that seam.

## Standalone target resolution

`shadowbane_lab.sim.targeting.TargetResolver` consumes source-independent
`TargetSelectorSpec` and `TargetCandidate` values. It evaluates exact
relationship requirements before coarse relation filtering, then applies
spatial and visibility constraints, deterministic ordering, and caps.

Every considered candidate produces a `TargetDecision`. Normal result artifacts
may retain accepted targets and aggregate rejection counts; trace mode may retain
the full decisions. Runtime integration should use the same resolver for both
single-target affordances and area-effect recipients.

The final “evaluate affiliation at cast start, release, impact, or pulse” field
is intentionally absent until lifecycle-core defines canonical action moments.

## Native object identity

`shadowbane_lab.client_observation.native_identity.NativeObjectKey` is the
adapter-boundary identity `(object_type, object_uuid)`. It maps one-to-one to
simulator entity IDs through `NativeEntityIdentityMap`.

Native joins never fall back to display name, memory pointer, health percentage,
position, or roster order. Missing and unbound identities remain explicit
`NativeIdentityDecision` rejections. Duplicate roster keys and ambiguous
bindings fail closed.

`shadowbane_lab.client_observation.group_affiliations` projects a native party
roster into `GroupMembership` values. The caller must supply a verified
`GroupKey(GroupKind.PARTY, ...)`, sourced from protocol/client data or explicit
scenario configuration. The adapter does not synthesize a durable party ID from
the roster.

The live party reader already exposes object type and UUID per roster member.
The loaded-character population reader does not yet expose a verified matching
object-type/UUID channel, so population-to-roster joining remains intentionally
unavailable rather than heuristic. Once that native channel is calibrated, its
records can use the same structural identity join without changing simulator
identity.

## Deferred integration

After lifecycle-core stabilizes, the integration change should be small:

1. place the materialized affiliation snapshot in scenario runtime state;
2. construct one shared `RelationResolver` and `TargetResolver`;
3. route single-target affordance generation and area-effect selection through
   that shared path; and
4. preserve seed-for-seed legacy behavior when only `team_id` is supplied.

Dynamic join, leave, leader-change, summon, and dissolution events should update
revisioned runtime snapshots only after static integration is correct.
