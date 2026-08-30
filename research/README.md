# Behavior research data

`shadowbane-behavior-corpus-v1.json` is the machine-readable research layer between raw evidence
and executable simulator rules.

It separates:

- named game/server profiles;
- version-pinned and pending sources;
- atomic behavior claims;
- supporting, contradicting and qualifying evidence;
- confidence and compile disposition;
- contradiction groups;
- required differential tests;
- intended simulator bindings;
- domain coverage and next evidence.

The corpus is validated by `schemas/behavior-evidence-v1.schema.json` and
`tests/test_behavior_corpus.py`.

## Editing rules

1. Add the source before adding a claim that cites it.
2. Give mutable sources `capture_status: pending` until a snapshot or immutable revision exists.
3. Never reuse a claim across profiles; create a new profile-specific claim.
4. Use `block` for disputed or unresolved behavior.
5. Put incompatible hypotheses in the same non-null `contradiction_group`.
6. Give every claim at least one planned or implemented `simulator_binding`.
7. Add the claim ID to relevant coverage rows.
8. Prefer small atomic claims that a focused scenario can falsify.
9. Do not store credentials, private server material, or unauthorized exports.

A claim becoming executable should normally be accompanied by a ruleset/engine test and, when
available, a differential fixture against the named runtime.
