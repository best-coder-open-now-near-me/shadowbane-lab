# ADR 0003: Fail closed on unresolved Shadowbane rules

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

The MagicBane server source describes how powers execute, but concrete power rows and tokens
come from deployment data that is not present in the public source repository. Community wiki
tables expose useful rank values while omitting or simplifying combat formulas. Treating either
source as complete would silently turn approximations into simulator truth.

## Decision

Ruleset declarations retain immutable, revision-pinned sources and field-level provenance.
Every action is classified as:

- `compiled`: executable with no known semantic gaps;
- `compiled_with_override`: executable using a documented reviewed approximation; or
- `unresolved`: non-executable because a required behavior cannot be represented faithfully.

Only the first two states enter the simulator's `ActionCatalog`. An override record must list
its unresolved differences, and an unresolved record must not contain an executable
`ActionSpec`. Rank curves are resolved during compilation so the simulator sees only concrete
values.

The first slice pins the MagicBane `subdate2` source revision and historical Assassin and
Warlock wiki revisions. Midpoints stand in for published damage and healing ranges and are
marked as overrides. Concrete power tokens remain null until an authorized deployment data
export is available. Passwall remains unresolved because the current action algebra does not
yet express terrain-aware teleport validation and damage-interruptible channels.

## Consequences

- Source drift cannot silently change a compiled ruleset.
- Executable approximations are visible and queryable rather than buried in code.
- Missing deployment data produces an explicit mapping gap.
- Differential traces can promote records or replace individual override fields without
  changing policy-facing action keys.

## Pinned public references

- [MagicBane Server revision](https://repo.magicbane.com/MagicBane/Server/src/commit/ab96cfcda4e983dd7fc1fc205205810f11ddd3de)
- [Assassin Powers revision 36339](https://morloch.shadowbaneemulator.com/index.php?title=Assassin_Powers&oldid=36339)
- [Warlock Powers revision 36352](https://morloch.shadowbaneemulator.com/index.php?title=Warlock_Powers&oldid=36352)
