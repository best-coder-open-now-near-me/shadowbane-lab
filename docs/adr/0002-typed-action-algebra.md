# ADR 0002: Compile actions into a bounded typed algebra

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

Shadowbane powers, movement, transfers, and objective interactions must run in a fast
deterministic simulator while remaining inspectable and mappable to emulator or client
commands. Arbitrary executable callbacks would prevent safe ingestion, deterministic
serialization, static validation, policy feature extraction, and optimized batch execution.

## Decision

Compiled actions are immutable `ActionSpec` values containing:

- targeting and relation constraints;
- resource costs and cooldowns;
- ordered windup, active, and recovery phases;
- immediate or projectile delivery;
- bounded typed effects; and
- semantic tags and numeric features.

The algebra uses independent axes instead of one class per power or per combination:

- `TargetingSpec` binds self, entity, position, or direction and declares range, relation,
  and line-of-sight constraints.
- `AreaEffect` is a target-set combinator around the actor or bound target. Single-target and
  area are therefore not different attack primitives; the same nested effect can use either.
- `AttackGate` chooses the basic-attack or power hit curve. Omitting it represents an explicit
  no-hit-roll action. Attack kind is independent of target-set shape.
- `ChanceGate` adds one seeded probability without changing the nested effect.
- phases and delivery describe when an effect resolves and whether it is immediate or a
  projectile.
- direct effects change one thing: scalar, damage, resource restoration, tag, timed state,
  movement, item ownership, objective progress, or stance.

The executable normal form is consequently a timeline containing either a direct effect or a
bounded composition such as `AreaEffect(AttackGate(ChanceGate(DealDamage)))`. Unsupported
nesting is rejected during construction and ruleset loading.

Damage origin is metadata. A sword, fist, spell, proc, and environmental hazard all use the
same `DealDamage` primitive. Its resistance channel comes from the closed `DamageType`
vocabulary; complete sheets likewise use a closed `ResistanceType` vocabulary, with healing
kept as a resistance channel rather than mislabeled as damage. `unknown` is reserved for
unattributed observations and cannot participate in resistance calculations.

Timed effects carry typed mechanical modifiers. For example, Shadow Mantle is an ordinary
`ApplyEffect` containing `ResourceImmunity("health")`; its policy-facing immunity tag is
derived from that modifier. Free-form tags may describe and query state, but adding a tag alone
must not invent simulator behavior.

Exceptional Shadowbane mechanics must be represented by reviewed, reusable typed extensions
rather than arbitrary callbacks or power-name branches embedded in ruleset data. The next
required extensions are a generic periodic scheduler for damage-over-time effects and generic
damage interception for absorbs. Until those exist, powers requiring them remain unresolved;
they must not be approximated through bespoke code.

Action values are concrete after ruleset compilation. Rank curves, build modifiers, and
source-specific formulas belong to the ruleset compiler, while the simulator executes the
resulting typed values.

## Consequences

- One grammar represents combat and noncombat actions.
- Direct/area, hit/no-hit, delivery, chance, timing, and damage channel can be varied
  independently without multiplying action classes.
- Policies can score actions using semantic tags and features instead of memorizing IDs.
- Reference and batched simulators can implement the same closed effect set.
- Ruleset ingestion can classify unsupported records as unresolved instead of approximating
  them silently.
