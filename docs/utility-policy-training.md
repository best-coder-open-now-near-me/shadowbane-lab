# Interpretable utility-policy training

Build search and decision-policy search are intentionally separate optimization
problems. A stronger character should not be credited for a better policy, and a
better policy should not silently change the build genome.

This tranche exposes seven interpretable multipliers over the existing
`UtilityDuelPolicy`:

```text
damage
control
healing
survival
setup
mobility
resource
```

The policy still receives only legal semantic affordances from the reference
environment. The weights cannot create actions, bypass targeting, ignore
cooldowns, change resource costs, or modify effect resolution. They only rescale
the existing deterministic utility score for an already legal bound action.

## Exact baseline parity

`UtilityPolicyWeights()` is the identity vector. The custom-policy duel runner
uses the same:

- primitive-loadout resolver;
- action catalog;
- entity materializer;
- fixed-tick reference environment;
- correlation identifiers;
- dead-actor schedule cancellation;
- result and trace digest builders.

A regression test requires default weighted policies to produce the exact same
`DuelResult`, trace digest, and resolved loadouts as the ordinary
`run_open_duel` path. This keeps policy injection from becoming a second combat
implementation.

## Common-seed league evaluation

`UtilityPolicyLeagueEvaluator` evaluates one controlled loadout against a fixed
opponent roster, scenario roster, and seed set. Mirrored scenarios run the
controlled policy from both sides. Each result records wins, losses, draws,
health margin, duration, rejected actions, and a digest binding:

- the ruleset;
- controlled and opponent mechanical loadouts;
- candidate and opponent policy vectors;
- scenarios and common seeds;
- every rollout trace digest.

Loadout identifiers and display names are excluded from mechanical identity.
They remain useful provenance but cannot produce a distinct policy-training
case by themselves.

## Diagonal evolution strategy

The first optimizer adapts an axis-aligned Gaussian over the seven utility
weights. It keeps the current mean in every generation, evaluates a bounded
unique population, retains deterministic top elites, updates the coordinate
means, and smooths each coordinate variance.

It is deliberately reported as:

```text
deterministic_diagonal_evolution_strategy_v1
```

and explicitly records `not_cma_es: true`. It does not maintain or adapt a full
covariance matrix and therefore must not be described as CMA-ES. The purpose of
this stage is to establish deterministic policy-vector evidence and a baseline
that a later full CMA-ES implementation can compare against.

## Current boundary

This optimizer remains a reference-simulator tool. Large policy populations
should move to the parity-tested NumPy/Numba environment before long training
runs. The same policy vector and action-family classification can then be used
without changing the semantic affordance or result contracts.
