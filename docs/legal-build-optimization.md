# Legal build optimization foundation

This branch introduces the construction and archive boundary required before large build or policy
searches can be trusted.

```text
reviewed WonderBane calculator
        +
equipment catalog
        +
compiled action ruleset
        ↓
LegalBuildGenome
        ↓
LegalBuildCompiler
        ↓
CompiledLegalBuild / ResolvedBuildView
        ↓
scenario evaluator
        ↓
evidence-aware MAP-Elites archive
```

The compiler does not make a build legal by assigning plausible-looking simulator numbers. Every
categorical choice is submitted to the reviewed calculator, every action is checked against the
compiled ruleset at the selected rank, and every equipment selection is checked against the
catalog's item/affix routes.

## Three compilation statuses

`chassis_verified` means the calculator accepted the race, base class, promotion, level, trained
attributes, and rune selection. It does not claim that a combat moveset or equipment loadout is
complete.

`source_candidate` means the build is structurally usable for an explicitly permissive experiment,
but at least one mechanic remains unresolved or was accepted from a source-revision/override
boundary. Candidate equipment values and current compiled-with-override powers live here.

`simulation_ready` is reserved for a build with a supplied ruleset, no unresolved selected
mechanics, and no accepted assumptions. Only this status is eligible for a strict archive.

## Equipment boundary

The equipment catalog can already prove that a base item exists and that a selected prefix/suffix
comes from a legal generation route. It does not yet generally prove:

- decoded equipment-slot flags;
- race, class, discipline, or ownership requirements represented by opaque tokens;
- the simulator effect associated with every affix action ID;
- current values for rows still labeled `historical_candidate`.

Consequently, selecting equipment produces explicit coverage entries. Base defense and weapon
values enter mechanics only with `apply_candidate_equipment_values=True`, and the compilation
artifact records that acceptance. Affix rolls are range-checked, but an unknown affix effect never
becomes a scalar.

## Ruleset boundary

The compiler constructs the existing `CharacterBuild` at the exact selected ranks. The caller must
compile the ruleset with matching rank overrides. Fully compiled actions are admitted normally.
`compiled_with_override` actions require `allow_ruleset_overrides=True` and leave an explicit
assumption in the output. Unresolved or unaccepted actions remain omitted.

General skill and power train budgets are still an open source-data boundary. Any non-empty
training allocation is therefore reported as `training.point_budget_unverified`; it is not silently
validated with the existing Rogue-specific helper.

## MAP-Elites admission

The quality-diversity archive separates candidate quality from evidence grade:

```text
ArchiveAdmission.CANDIDATE
ArchiveAdmission.STRICT
```

An archive configured with `required_admission=STRICT` rejects candidate evaluations before cell
comparison. A candidate archive may contain either grade, but every cell retains the grade and
evidence digest. Replacement is deterministic: quality first, then stronger admission, then
canonical candidate and evidence digests.

Behavior descriptors are explicit numeric axes with fixed boundaries. The initial intended axes
are engagement range, control contribution, and effective durability, but the archive does not
hard-code those meanings.

## Compile an example

Validate only the legal chassis:

```powershell
$env:PYTHONPATH = "src"
python -m shadowbane_lab.optimization `
  .\configs\legal-build-genome.example.json `
  --no-ruleset
```

Compile against the current guide-duel ruleset while explicitly admitting its reviewed overrides:

```powershell
python -m shadowbane_lab.optimization `
  .\configs\legal-build-genome.example.json `
  --allow-ruleset-overrides `
  --output .\artifacts\compiled-build.json
```

The output carries calculator, equipment, ruleset, policy, mechanical, construction, and full
compilation digests. Recompiling identical inputs produces the same artifact identity.

## Next tranche

The next step is an evaluator that runs each compiled candidate over common-seed, mirrored scenario
suites and emits a `MapElitesEvaluation`. It should initially use the existing reference simulator
as the correctness oracle and keep strict and candidate archives separate. CMA-ES can then tune the
interpretable utility-policy weights inside each fixed build, while MAP-Elites searches legal build
permutations. The optimized NumPy/Numba environment remains a later throughput layer and must match
reference traces before replacing the oracle.
