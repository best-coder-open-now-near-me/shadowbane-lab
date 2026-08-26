# Progression-aware duel rollouts

The rollout harness runs the same semantic affordances used by adapters through the scalar
reference environment. Its first scenario is a deterministic Assassin-versus-Warlock duel
with a generic utility policy. The runner records the winner, termination reason, duration,
remaining resources, damage, healing, action counts, and rejected-action count.

## Progression boundary

Character level, focus-skill training, enabled powers, and power rank are separate inputs.
This matters because Shadowbane awards training points for player-directed allocation; there
is no single authoritative power-rank curve for a given character level.

The current executable slice uses these published grant points:

| Profession | Power | Granted | Focus requirement | Status |
| --- | --- | ---: | --- | --- |
| Assassin | Shadow Bolt | 10 | Shadowmastery 15 | Executable |
| Assassin | Shadow Touch | 15 | Shadowmastery 36 | Executable |
| Assassin | Passwall | 28 | Shadowmastery 66 | Unresolved and excluded |
| Warlock | Mind Strike | 10 | None published | Executable |
| Warlock | Levitation | 22 | Warlockry 52 | Executable at fixed rank 5 |
| Warlock | Psychic Healing | 26 | Warlockry 61 | Executable |

Sources are the archived [Assassin power table](https://morloch.shadowbaneemulator.com/index.php?title=Assassin_Powers&oldid=36339),
[Warlock power table](https://morloch.shadowbaneemulator.com/index.php?title=Warlock_Powers&oldid=36352),
and the pinned MagicBane server revision recorded in the bundled ruleset. Every concrete
mechanic retains field-level provenance and an explicit compilation quality state.

`CharacterBuild.enabled_power_keys` can select a strict subset. `power_ranks` can select
rank 0 through 40 independently. A ruleset must be compiled at those exact ranks; mismatches,
unknown powers, invalid fixed-rank overrides, unmet levels, and unmet prerequisites fail
closed.

## Run the bracket

From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m shadowbane_lab.rollouts
```

Machine-readable output and custom brackets are available:

```powershell
python -m shadowbane_lab.rollouts --levels 10,15,22,26,40 --ranks 0,20,40 --json
```

The built-in matched progression sweep assumes the published focus prerequisites are met.
It deliberately brackets power ranks at 0, 20, and 40 instead of inventing a rank-by-level
allocation. Programmatic callers can provide exact skills, trained ranks, enabled subsets,
resources, starting distance, seed, and tick limit through `DuelConfig`.

## Initial result

With 100 health, 200 mana, a 10-unit start, and the current utility policy, the checked-in
bracket produces:

| Level | Rank 0 | Rank 20 | Rank 40 |
| ---: | --- | --- | --- |
| 10 | Warlock | Assassin | Assassin |
| 15 | Warlock | Assassin | Assassin |
| 22 | Warlock | Assassin | Assassin |
| 26 | Warlock | Warlock | Assassin |
| 40 | Warlock | Warlock | Assassin |

These are harness baselines, not balance claims. In particular, Psychic Healing changes the
rank-20 outcome after its level-26 unlock, while rank-40 Shadow Touch gives the baseline
Assassin a large control advantage after level 15.

## Known fidelity gaps

The result must remain labeled `compiled_with_override` until differential traces replace
the scalar assumptions. The current slice does not yet model:

- hit rolls, attack rating, defense, resistances, or authoritative roll distributions;
- stat/focus modifiers, regeneration, equipment, or weapon-specific basic attacks;
- cast interruption, obstacle line of sight, collision, or full flight movement semantics;
- area targets, damage-over-time ticks, absorbs, or broad buff/debuff interactions.

Published damage and healing ranges use a reviewed continuous-uniform approximation. The
specified PCG32 stream makes those rolls exactly replayable by seed and snapshot, while
expected-value policy features remain the published range midpoint. Basic attack damage and
timing are still reviewed placeholders. The useful signal at this stage is legal action flow,
progression gating, resource exhaustion, control timing, healing timing, bounded outcome
variation, and win/loss termination. Emulator differential fixtures are the next authority
for replacing the assumed distribution and closing the remaining combat gaps.
