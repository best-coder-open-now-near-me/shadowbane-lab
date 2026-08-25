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

The initial effect set covers scalar changes, damage, restoration, tags, timed effects,
movement, item transfer, and objective progress. Exceptional Shadowbane mechanics must be
represented by reviewed typed extensions rather than arbitrary code embedded in ruleset
data.

Action values are concrete after ruleset compilation. Rank curves, build modifiers, and
source-specific formulas belong to the ruleset compiler, while the simulator executes the
resulting typed values.

## Consequences

- One grammar represents combat and noncombat actions.
- Policies can score actions using semantic tags and features instead of memorizing IDs.
- Reference and batched simulators can implement the same closed effect set.
- Ruleset ingestion can classify unsupported records as unresolved instead of approximating
  them silently.
