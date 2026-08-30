# Assassin vs Warlock: ranked Shadow Mantle experiment

This document records the first fidelity increment applied to the progression-aware Assassin-versus-Warlock duel. It is a simulator and policy probe, not a Shadowbane balance claim.

## Change under test

The branch adds Shadow Mantle at level 42 and a reusable ranked resource-restoration blocker.

The compiled power record represents:

- Assassin level 42 progression gate
- Shadowmastery 97 requirement
- ranks 0 through 40
- 100-unit range
- one-second active phase
- rank-scaled mana cost from 55 to 95
- a 30-second `BMHealing` effect
- immunity to health restoration from effects at the same or a lower rank

`RestoreResource` now carries its source effect rank. During restoration, the executor searches active effects for `resource.restore.block.<resource>` tags and denies the restoration when the strongest blocker rank is greater than or equal to the restoration rank. The event still records the requested and effective amounts, plus the blocking rank and effect key when blocked.

The policy observation exposes active restoration-block ranks as scalars such as `restore_block_rank.health`. That lets a policy reject an equal-or-lower-rank healing action without hard-coding Shadow Mantle inside the engine.

The reviewed source values and unresolved emulator questions are retained in [`assassin_shadow_mantle_v1.json`](../src/shadowbane_lab/rulesets/data/assassin_shadow_mantle_v1.json).

## Expanded matrix

The baseline matrix had 96 cells and 288 playouts. The expanded matrix adds the level-42 unlock point, producing:

- levels 10, 15, 18, 19, 22, 26, 28, 42, and 75
- power ranks 0, 10, 20, and 40
- starting distances 15, 60, and 110 units
- deterministic seeds 1, 2, and 3
- 108 cells and 324 playouts

| Level | Playouts | Assassin wins | Warlock wins | Draws | Time limits |
|---:|---:|---:|---:|---:|---:|
| 10 | 36 | 12 | 21 | 3 | 0 |
| 15 | 36 | 15 | 18 | 3 | 0 |
| 18 | 36 | 15 | 18 | 3 | 0 |
| 19 | 36 | 15 | 18 | 3 | 0 |
| 22 | 36 | 15 | 18 | 3 | 0 |
| 26 | 36 | 6 | 30 | 0 | 0 |
| 28 | 36 | 6 | 30 | 0 | 0 |
| 42 | 36 | 6 | 30 | 0 | 0 |
| 75 | 36 | 6 | 30 | 0 | 0 |
| **Total** | **324** | **96** | **213** | **15** | **0** |

By power-rank bracket:

| Power rank | Playouts | Assassin wins | Warlock wins | Draws |
|---:|---:|---:|---:|---:|
| 0 | 81 | 15 | 66 | 0 |
| 10 | 81 | 15 | 66 | 0 |
| 20 | 81 | 27 | 39 | 15 |
| 40 | 81 | 39 | 42 | 0 |

By starting distance:

| Distance | Playouts | Assassin wins | Warlock wins | Draws |
|---:|---:|---:|---:|---:|
| 15 | 108 | 54 | 54 | 0 |
| 60 | 108 | 42 | 51 | 15 |
| 110 | 108 | 0 | 108 | 0 |

All 96 cells shared with the original matrix retained the same winner counts. Shadow Mantle changes fight paths and healing totals, but this normalized slice does not yet contain enough Assassin fidelity to overturn any existing cell.

## Concrete mechanical effects

The most visible level-75 changes were:

| Rank | Distance | Baseline ticks | Mantle ticks | Baseline Warlock healing | Mantle Warlock healing | Winner |
|---:|---:|---:|---:|---:|---:|:---|
| 20 | 15 | 283 | 209 | 212.0 | 53.0 | Assassin |
| 40 | 15 | 111 | 108 | 64.5 | 0.0 | Assassin |
| 40 | 60 | 295 | 272 | 129.0 | 0.0 | Warlock |

At level 42 and level 75, the current harness produces identical cells. That is not evidence that the real levels are equivalent. The normalized combatant profiles and executable power sets do not change between those points yet.

## Policy ablations

Two focused experiments crossed levels 42 and 75, all four power ranks, all three distances, and all three seeds: 24 cells and 72 playouts each.

### Forced-priority ablation

Shadow Mantle received a 10,000-point utility bonus whenever it was legal. The result was bit-for-bit identical to the normal policy in all 24 cells:

| Variant | Assassin wins | Warlock wins | Draws |
|:---|---:|---:|---:|
| Normal policy | 12 | 60 | 0 |
| Forced Mantle priority | 12 | 60 | 0 |

The existing utility score is therefore not suppressing a legal Mantle cast. The policy already chooses it when it is available and useful by its one-step score.

### Setup and mana-reservation ablation

A second variant suppressed Assassin damage utility only while an unblocked Warlock was beyond Shadow Mantle's 100-unit range. This made the Assassin close before spending mana on Shadow Bolt and cast Mantle once it entered range.

The result again retained the same winner counts:

| Variant | Assassin wins | Warlock wins | Draws |
|:---|---:|---:|---:|
| Normal policy | 12 | 60 | 0 |
| Reserve for first Mantle | 12 | 60 | 0 |

The rule did alter every 110-unit sample at levels 42 and 75:

- Mantle casts changed from zero to one.
- At rank 0, Warlock healing changed from 41.5 to zero.
- At rank 20, Warlock healing changed from 106.0 to zero.
- At rank 10, the Warlock still healed after the 30-second block expired.
- At rank 40, healing was already zero; reserving mana reduced early Shadow Bolt pressure and lengthened the sample fight from 251 to 276 ticks.

This is evidence against adding another matchup-specific utility constant. The policy needs to compare short action sequences and their opportunity costs: approach, resource reservation, debuff duration, likely time to first heal, damage sacrificed during setup, and whether a recast will be affordable.

## What the experiment establishes

- Ranked restoration denial works at the engine boundary rather than as a duel-only exception.
- Policies can observe the active blocking rank and avoid known-invalid healing actions.
- Shadow Mantle materially changes healing and time-to-resolution in several cells.
- The original winner distribution was not caused merely by omitting Shadow Mantle or undervaluing its immediate utility.
- Long-range Assassin losses are not fixed by reserving enough mana for one Mantle cast.
- All three seeds remain semantically identical because hit rolls, defense, damage distributions, resistances, and interrupt checks are still deterministic or absent.

## Recommended next increments

### Mechanics fidelity

1. Add a generic periodic-effect primitive and compile Steal Breath's initial poison hit plus five-second damage ticks.
2. Add movement-rate modifiers and flight removal so Steal Breath and Mind Snare affect positioning.
3. Add typed shields and absorbers for Psychic Shield and Mental Shield.
4. Add deterministic-random hit, defense, damage, resistance, and interrupt checks.
5. Replace normalized level profiles with explicit build profiles that allocate attributes, skills, focus training, power ranks, equipment, and resistances.
6. Add late-progression powers before interpreting the level-75 row as a full-kit matchup.

### Policy fidelity

1. Keep the current utility policy as a fast deterministic baseline.
2. Add a bounded look-ahead policy over cloned snapshots, initially depth two or three.
3. Score terminal health, resources, position, active-effect remaining time, cooldown state, and invalidated enemy affordances.
4. Run the same matrix as a policy tournament: greedy utility versus look-ahead on each side, then mirrored matchups to separate build strength from policy strength.
5. Preserve trace digests and action counts so a policy improvement can be distinguished from a mechanics change.

## Reproduction

Run the expanded matrix locally:

```bash
python -m shadowbane_lab.rollouts \
  --matrix \
  --levels 10,15,18,19,22,26,28,42,75 \
  --ranks 0,10,20,40 \
  --distances 15,60,110 \
  --seeds 1,2,3 \
  --max-ticks 1200 \
  --json
```

The policy ablations are retained on `codex/shadow-mantle-policy-ablation`. They modify the checked-out policy only inside their workflows, leaving the simulator mechanics and production policy unchanged.