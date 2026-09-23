# Differential validation

The reference simulator is a correctness oracle for optimized backends, but it is not the
authority for Shadowbane behavior. A running emulator is authoritative. Differential traces
make the boundary explicit and reproducible.

## Trace contract

A version-1 trace pins a ruleset revision and scenario, then records each controlled step as:

```text
captured pre-state
    -> legal semantic affordances
    -> semantic decisions
    -> causal event batch
    -> captured post-state
```

State capture includes entity positions and velocities, scalar resources, active effects and
stack keys, effect expiry times, cooldown readiness, cast/busy time, life identity, and alive
state. It contains no packet identifiers or screen coordinates. Nested protocol messages use
the same canonical version-1 codec as policies and adapters.

Comparison removes producer-specific trace, message, observation, affordance, and event IDs.
It preserves correlation IDs and compares the semantic content under the following categories:

- legality;
- timing and interruption;
- resource and damage changes;
- effects and stacking;
- cooldowns;
- movement; and
- life/world termination.

Numeric tolerance is category-specific and defaults to exact equality. Tag and scalar-map order
does not affect comparison. A captured trace can be round-tripped through canonical JSON for
review and source control.

## Gap ledger policy

Every observed difference is unexpected by default. The bundled gap ledger starts with open
entries for known unsupported or approximate mechanics; open entries document work but never
make a comparison pass.

Only a deliberately reviewed `accepted_approximation` entry can accept a difference. Such an
entry must be scoped by scenario, category, path pattern, and optionally a maximum absolute
delta. It should cite captured evidence. Resolved entries remain as history and accept nothing.

This keeps broad tolerances from hiding regressions in unrelated mechanics.

## Emulator capture workflow

1. Pin the emulator source and deployment data revisions.
2. Construct a controlled initial state and seed, if the authoritative path exposes one.
3. Export the pre-state and legal semantic affordances.
4. Submit the same semantic decision used by the reference trace.
5. Export authoritative events and post-state at every pulse until the action settles.
6. Compare the emulator trace to the reference trace with exact tolerances first.
7. Fix the importer or simulator, or add a narrowly reviewed ledger entry with evidence.

The repository currently contains the recorder, canonical trace codec, comparator, and open gap
ledger. It does not claim emulator parity yet: the public MagicBane source lacks the deployment
power rows/tokens, and no authoritative runtime trace has been supplied.

The planned [evidence spine](evidence-spine.md) closes the orchestration gap without changing this
comparison authority. A research case binds the exact fingerprints, hypotheses, experiment,
synchronized producer records, raw artifact IDs, normalized trace, comparison result, and affected
gap entries. Required capture channels that are missing or dropped make the run incomplete rather
than widening comparison tolerance.
