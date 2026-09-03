# Catalog-backed legal-build training

This tranche connects the legal-build compiler to the existing semantic combat
lifecycle. It does not introduce a simulator-only damage model and it does not
allow an optimizer to write combat scalars directly.

```text
LegalBuildGenome
    -> reviewed WonderBane calculator
    -> calculator-authoritative allocation space
    -> equipment/ruleset compiler
    -> catalog-backed necessary-condition gate
    -> ResolvedBuildView
    -> semantic PrimitiveLoadout adapter
    -> existing action/lifecycle simulator
    -> common-seed mirrored evaluation
    -> MAP-Elites archive
```

## Calculator-authoritative allocation

`CalculatorAllocationSpace` owns the legal neighborhood for trained attributes.
It can enumerate one-point spends, transfers, and explicit refunds, but every
neighbor is accepted only after the reviewed WonderBane calculator recomputes:

- the creation and level-earned point pool;
- selected-rune cost;
- pre-rune minimum attributes and the `-5` dump floor;
- pre-rune racial caps;
- post-rune attributes and cap grants;
- health, mana, stamina, and base defense.

Rune mutation uses the same boundary. A more expensive rune selection refunds
trained points without crossing any selected rune's minimum-stat requirement. A
cheaper selection returns freed points to legal attributes. No mutation edits a
final attribute, resource, or combat scalar directly.

The first Assassin archive now starts from three mechanically distinct, fully
allocated calculator states. Display labels and tuple order do not count as
variation. `CalculatorBackedGenomeMutator` then uses calculator neighbors for
attribute changes and calculator repair for rune changes before the ordinary
compiler and catalog gate see the child.

## Additional legality gate

The general compiler intentionally retains unresolved mechanics instead of
guessing. Search adds a narrower gate for facts that are already safe to enforce:

- a catalog weapon with damage, speed, and range must occupy `main_hand` or
  `off_hand`;
- an item's named skill and displayed required rank must be met;
- a two-handed weapon cannot coexist with another occupied hand;
- selected power ranks cannot exceed the sourced Rogue training pool even under
  the optimistic lower-bound assumption of one point per power-rank increment.

The power check is necessary but not sufficient. General skill-rank costs and
opaque item requirement tokens remain unresolved, so passing the gate never
promotes a candidate to strict evidence.

## League evaluation

`StrictLegalBuildLeagueEvaluator` compiles every candidate before running it. It
evaluates the same candidate against an ordered opponent set, ordered scenario
set, and common deterministic seeds. Scenarios can mirror left/right placement
to reduce side-order bias.

The evaluator derives runtime scalars from the compiled build view and calls the
existing semantic duel path. Windup, active and recovery phases, resource costs,
cooldowns, delivery, interruption, effects, damage, death, and termination
therefore remain owned by the reference simulator.

Required actor tags are not synthesized in legal-build search. The open behavior
sandbox still supports explicit permissive exploration, but strict evaluation
records missing static or transient prerequisites and leaves the authoritative
affordance builder to withhold the action.

Optimizer identity is derived only from normalized mechanical selections. Display
labels and caller tuple order remain provenance, but cannot create a second archive
candidate or change tie-breaking.

Each archive evaluation records:

- win, loss, draw, survival, health, timing, and rejected-action metrics;
- the candidate compilation digest;
- catalog-legality audit;
- opponent compilation digests;
- scenario definitions and seeds;
- missing action prerequisites;
- every rollout trace digest;
- one aggregate evidence digest.

## Compiler-backed mutation

`CalculatorBackedGenomeMutator` can vary:

- trained attribute allocation through calculator-approved neighbors;
- selected runes with calculator-owned cost and minimum-stat repair;
- selected compiled powers;
- equipment choices by declared slot.

Every proposed child is passed through the catalog gate and legal-build compiler
before it is returned to MAP-Elites. Invalid mutations are discarded within a
bounded attempt count. Mutation cannot directly alter health, attack rating,
defense, weapon damage, resistance, or any other simulator scalar.

## First experiment

The initial experiment searches calculator-legal level-75 Irekei Rogue
Assassins. It starts from three distinct fully allocated variants and uses the
reviewed Sun Dancer and Saboteur calculator entries. The executable powers and
training snapshots come from the checked-in proc-Assassin guide preset.
Candidate unarmed weapons come from the equipment catalog, beginning with
reviewed item `29390` (Rha'khanakar).

The league uses the guide presets' explicit identities: Shade Fighter Deflock
and Elf Healer Druid. When a guide does not specify sex, the lowest reviewed
sex-specific calculator record is selected deterministically. These are stable
search baselines, not claims that their generated allocations reproduce every
live piece of the archived guide sheets.

Run a small search:

```powershell
$env:PYTHONPATH = "src"

python -m shadowbane_lab.optimization.irekei_assassin `
  --iterations 24 `
  --mutation-seed 7 `
  --rollout-seeds 1,2,3 `
  --distances 6,15,40 `
  --max-ticks 600 `
  --equipment-pool-size 12 `
  --output .\artifacts\irekei-assassin-map-elites.json
```

The archive dimensions are survival rate, executable action count, and combined
health/mana/stamina depth. Quality combines mirrored matchup outcome, remaining
health margin, completion tempo, timeout penalties, and rejected-action
penalties.

## Evidence boundary

The default archive deliberately requires `candidate`, not `strict`, admission.
Current equipment values are historical candidates, general skill-train costs
and opaque item requirements are unresolved, and selected action rows still
depend on reviewed ruleset overrides. These limitations are preserved in
compiler coverage, evaluator notes, report caveats, and evidence digests.

The next promotion steps are:

1. replace the Rogue-only lower-bound train audit with typed base-class training
   budget profiles and explicit skill/power costs;
2. decode and test additional item requirement/equip-flag families;
3. compile typed affix effects and stacking rules;
4. add held-out opponent sets and PvE/resource-efficiency scenarios;
5. add controlled build-policy co-evaluation while retaining separate attribution;
6. implement a NumPy/Numba backend with differential parity to the reference
   environment;
7. replace the current diagonal policy strategy with full covariance CMA-ES
   only after the reference policy-training fixtures remain stable.

The separate interpretable policy seam is documented in
[utility-policy-training.md](utility-policy-training.md).
