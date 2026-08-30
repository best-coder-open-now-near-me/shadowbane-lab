# Compositional build and simulation-case views

This layer separates construction, scenario layout, and runtime execution. It is
intentionally independent of class-specific simulator branches and of group
relation semantics.

```text
primitive behavior
    -> ability recipe
    -> source package
    -> build blueprint
    -> ResolvedBuildView

scenario slot + starting-state overlay
    -> ResolvedScenarioView

ResolvedBuildView + policy + scenario slot + seed
    -> SimulationCaseView
    -> runtime actor state
```

## Source packages

A `SourcePackage` is one reusable source of mechanics and constraints. Its
`kind` may identify a body, race, base class, promotion, discipline, stat rune,
equipment item, consumable, or experimental search piece. The kind and display
name are construction provenance only. Runtime behavior comes from the granted:

- action recipe keys;
- passive and capability tags;
- persistent trigger keys;
- body, attribute, and scalar changes;
- training-access keys.

Packages may require or conflict with other packages. Optional selection slots
and catalog slot limits express constraints such as one race, one base class,
one promotion, a bounded number of disciplines, or one item in a particular
equipment slot.

The resolver closes requirements, rejects conflicts and slot overflow, combines
numeric grants, and retains grant provenance. Partial catalog entries are valid:
unknown actions, triggers, or training access are reported in the resolved view
rather than fabricated or used to block unrelated mechanics.

## Build blueprints and resolved views

A `BuildBlueprint` is a construction request. It selects source packages and
contains the current attribute allocation, training allocation, direct recipe
keys, and any exact live-sheet scalar inputs.

A `ResolvedBuildView` is immutable and suitable for reuse across many
simulations. It contains:

- final body resources and movement speed;
- executable and omitted action recipes;
- tags and persistent triggers;
- scalar, attribute, and training values;
- selected and automatically added packages;
- unresolved training access;
- per-grant source provenance;
- coverage and deterministic signatures.

The mechanical signature excludes construction labels and package identity. Two
different source combinations that produce the same executable mechanics may
therefore be deduplicated during behavior search. The construction signature
retains the package path and unresolved coverage so both ways of building the
same mechanical result remain recoverable.

The existing `PrimitiveLoadout` rollout path remains supported through explicit
adapters. Rollout orchestration does not need to understand package closure.

## Scenario views

Group membership is not part of a build. A `ScenarioOverlay` describes one
slot's starting position, resource fractions, scalar overrides, added or removed
tags, and initial effect keys. A `ScenarioSlotView` owns the simulator entity
identity and may retain the legacy `team_id` compatibility value.

A `ResolvedScenarioView` owns:

- scenario slots and starting-state overlays;
- ruleset and environment profile revisions;
- duration and tick settings;
- environment tags and scalars;
- an opaque affiliation snapshot identifier, digest, and revision.

The composition layer does not interpret party, guild, nation, side, ownership,
or neutrality. The group-targeting subsystem owns those facts and produces the
affiliation snapshot. Including its digest in the scenario signature prevents
two different party layouts from collapsing into one simulation case.

## Simulation cases

A `SimulationParticipantView` pairs one scenario slot with one resolved build
and one policy. A `SimulationCaseView` requires exactly one participant for each
scenario slot and adds the deterministic seed.

Independent permutation axes can therefore vary without contaminating one
another:

```text
build package selection
attribute and training allocation
equipment and consumables
policy
starting position and resources
visibility and prebuff state
affiliation snapshot
ruleset/environment revision
seed
```

Case signatures are stable under participant ordering. Changing a policy,
starting state, affiliation snapshot, ruleset revision, or seed changes the case
signature while leaving the reused build signature intact.

## Integration boundary

The permutation runner should select or generate blueprints, resolve them once,
select scenario views and policies, and emit `SimulationCaseView` rows. It
should not interpret package labels, `team_id`, party membership, or target
friendliness.

The runtime materializer will eventually combine a case with the action catalog,
affiliation resolver, and lifecycle-correct environment. Until that final seam
is wired, these contracts provide stable artifacts for catalog population,
deduplication, reporting, and parallel group-development work.
