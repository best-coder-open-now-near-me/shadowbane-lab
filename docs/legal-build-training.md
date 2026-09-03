# Catalog-backed legal-build training

This tranche connects the legal-build compiler to the existing semantic combat
lifecycle. It does not introduce a simulator-only damage model and it does not
allow an optimizer to write combat scalars directly.

```text
LegalBuildGenome
    -> reviewed WonderBane calculator
    -> equipment/ruleset compiler
    -> catalog-backed necessary-condition gate
    -> ResolvedBuildView
    -> semantic PrimitiveLoadout adapter
    -> existing action/lifecycle simulator
    -> common-seed mirrored evaluation
    -> MAP-Elites archive
```

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

`LegalBuildLeagueEvaluator` compiles every candidate before running it. It
evaluates the same candidate against an ordered opponent set, ordered scenario
set, and common deterministic seeds. Scenarios can mirror left/right placement
to reduce side-order bias.

The evaluator derives required runtime tags from the already compiled action
specifications, projects sourced weapon and power attack ratings, and then calls
the existing `run_open_duel` path. Windup, active and recovery phases, resource
costs, cooldowns, delivery, interruption, effects, damage, death, and
termination therefore remain owned by the reference simulator.

Each archive evaluation records:

- win, loss, draw, survival, health, timing, and rejected-action metrics;
- the candidate compilation digest;
- catalog-legality audit;
- opponent compilation digests;
- scenario definitions and seeds;
- every rollout trace digest;
- one aggregate evidence digest.

## Compiler-backed mutation

`CompilerBackedGenomeMutator` can vary:

- trained attribute allocation;
- selected runes;
- selected compiled powers;
- equipment choices by declared slot.

Every proposed child is passed through the catalog gate and legal-build compiler
before it is returned to MAP-Elites. Invalid mutations are discarded within a
bounded attempt count. Mutation cannot directly alter health, attack rating,
defense, weapon damage, resistance, or any other simulator scalar.

## First experiment

The initial experiment searches calculator-legal level-75 Irekei Rogue
Assassins. It starts from Intelligence-, Dexterity-, and Constitution-prioritized
fully allocated variants and uses the reviewed Sun Dancer and Saboteur
calculator entries. The executable powers and training snapshots come from the
checked-in proc-Assassin guide preset. Candidate unarmed weapons come from the
equipment catalog, beginning with reviewed item `29390` (Rha'khanakar).

The league uses calculator-legal builds carrying the checked-in Deflock and Elf
Druid executable movesets as stable opponents. These are deterministic search
baselines, not claims that their calculator allocation reproduces every live
piece of the archived guide sheets.

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

1. decode and test the first item requirement/equip-flag families;
2. compile typed affix effects and stacking rules;
3. replace the lower-bound train audit with complete base-class training costs;
4. add held-out opponents and PvE/resource-efficiency scenarios;
5. implement a NumPy/Numba backend with differential parity to the reference
   environment;
6. expose utility-policy weights and optimize them separately from build
   choices.
