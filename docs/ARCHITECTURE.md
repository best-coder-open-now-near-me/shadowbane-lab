# Architecture

## Core model

The simulator treats the world as a typed temporal configuration and an action as a constrained state transformation:

```text
state(t) + bound actions + seeded randomness -> state(t + dt) + events
```

A named game power is not an engine branch. It is a composition of semantic primitives.

## Layers

### 1. Simulation kernel

The kernel owns:

- virtual time;
- deterministic random streams;
- entity resources and positions;
- legal-action validation;
- cast and cooldown progression;
- effect lifecycle and ticking;
- causal event emission;
- scenario termination and truncation.

It must not know about accounts, clients, packets, SQL, Discord, or a particular wiki layout.

### 2. Rules compiler

The rules compiler turns source records into normalized action and entity specifications.

```text
wiki/client/cache record
    -> normalized semantic record
    -> reviewed overrides
    -> compiled ActionSpec / BuildSpec
```

Exceptional mechanics remain explicit rather than silently approximated.

### 3. Policy boundary

A policy receives an observation and currently legal affordances, then returns a semantic decision:

```text
observation + legal action candidates -> action + target + movement
```

The initial utility policy has perfect simulator state. Future observation wrappers will deliberately hide or corrupt information to match what a live client or human could know.

### 4. Search and learning

Build search and tactical learning are distinct:

- **build genome:** legal character construction and action kit;
- **policy parameters:** how that build chooses and times actions;
- **evaluation league:** diverse opponents, seeds, starts, and scenarios;
- **archive:** behavioral niches rather than only one scalar optimum.

CMA-ES can tune continuous utility parameters. MAP-Elites preserves diverse behavior. PPO/MAPPO can later replace or augment the utility policy.

### 5. Validation boundary

The simulator must be compared against controlled game observations:

```text
same initial state
same selected action
same relevant random assumptions
    -> compare costs, timing, range, damage, effects and final state
```

Every discrepancy becomes one of:

- a kernel correction;
- an importer correction;
- a reviewed power override;
- a documented approximation;
- an unresolved case excluded from evaluation.

## Current limitations

The first slice intentionally simplifies several things:

- only duels are exposed by the public runner;
- effect stacking uses replace/refresh behavior rather than Reforged-specific stack groups;
- completed actions resolve in deterministic actor-index order, not fully simultaneous batches;
- the utility policy observes perfect state;
- geometry is an open circular 2D arena;
- powers and formulas are abstract;
- build legality is not yet modeled.

These are visible constraints, not hidden assumptions.

## Multi-agent direction

The internal state already uses indexed combatants and team IDs. The next environment should add:

- arbitrary team sizes and inactive slots;
- per-agent life termination separate from scenario termination;
- fixed rollout truncation with critic bootstrapping;
- local engagement graphs;
- variable entity/action candidate sets;
- reinforcement and objective events;
- centralized training state with decentralized policy observations.
