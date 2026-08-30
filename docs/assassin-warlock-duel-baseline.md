# Assassin vs Warlock deterministic duel baseline

This document records the first progression-aware matchup sweep over the reference simulator. It is a harness probe, not a Shadowbane balance claim.

## Scenario

Each combatant uses normalized simulator stats:

- 500 health
- 300 mana
- 200 stamina
- 15 movement units per second

The matrix crosses:

- character levels 10, 15, 18, 19, 22, 26, 28, and 75
- explicit power-rank brackets 0, 10, 20, and 40
- starting distances 15, 60, and 110 units
- deterministic seeds 1, 2, and 3
- a 1,200-tick ceiling

That produces 96 cells and 288 playouts. Power rank is an explicit experimental axis, not an inferred training-point allocation. Powers capped below rank 40 are clamped to their real cap. Focus prerequisites are assumed satisfied so the experiment isolates level, power rank, and range.

## Executable progression slice

Common actions:

- directional movement
- normalized basic melee attack

Assassin:

- level 10: Shadow Bolt, Fade, Backstab
- level 15: Shadow Touch
- level 19: Invisibility, only when Fade is at least rank 18
- level 28: Passwall is represented in the ruleset but remains unresolved and non-executable

Warlock:

- level 10: Mind Strike
- level 18: Mind Snare
- level 22: fixed-rank Levitation
- level 26: Psychic Healing

The duel extension adds executable Fade, Backstab, Invisibility, and Mind Snare records to the existing vertical slice.

## First matrix result

| Level | Playouts | Assassin wins | Warlock wins | Draws | Time limits |
|---:|---:|---:|---:|---:|---:|
| 10 | 36 | 12 | 21 | 3 | 0 |
| 15 | 36 | 15 | 18 | 3 | 0 |
| 18 | 36 | 15 | 18 | 3 | 0 |
| 19 | 36 | 15 | 18 | 3 | 0 |
| 22 | 36 | 15 | 18 | 3 | 0 |
| 26 | 36 | 6 | 30 | 0 | 0 |
| 28 | 36 | 6 | 30 | 0 | 0 |
| 75 | 36 | 6 | 30 | 0 | 0 |
| **Total** | **288** | **90** | **183** | **15** | **0** |

By power-rank bracket:

| Power rank | Assassin wins | Warlock wins | Draws |
|---:|---:|---:|---:|
| 0 | 15 | 57 | 0 |
| 10 | 15 | 57 | 0 |
| 20 | 24 | 33 | 15 |
| 40 | 36 | 36 | 0 |

By starting distance:

| Distance | Assassin wins | Warlock wins | Draws |
|---:|---:|---:|---:|
| 15 | 48 | 48 | 0 |
| 60 | 42 | 39 | 15 |
| 110 | 0 | 96 | 0 |

All three seeds produced the same semantic trace in every cell, leaving 96 unique trajectories rather than 288. That is expected while hit rolls, damage distributions, resists, and other stochastic mechanics remain uncompiled.

## What the sweep says about the harness

The good:

- all 288 playouts terminated before the tick ceiling
- the policy submitted no rejected actions
- snapshot-derived traces are reproducible
- level and prerequisite gates select legal action subsets
- rank interpolation changes action choice and outcomes
- distance produces distinct approach and ranged-combat paths

The warnings:

- Psychic Healing creates the large level-26 swing, but level-42 Shadow Mantle is not implemented yet; the level-75 row is therefore structurally favorable to Warlock
- Mind Snare is recorded as an effect, but its magnitude does not yet change movement speed
- Levitation is available but deliberately deprioritized because flight and flight upkeep are not modeled
- invisibility is sufficient to gate Backstab, but does not yet hide the actor from targeting or apply its movement modifier
- Backstab is approximated as an immediate deterministic hit rather than a next-swing weapon modifier with attack and defense rolls
- a rollout guard removes future scheduled resolutions from an actor that died earlier; the generic timeline still needs a first-class cast, launch, interrupt, and cancellation lifecycle
- normalized health, resources, movement, melee damage, and equal power ranks do not represent a production character build

## Next fidelity increments

The next matchup-relevant mechanics should be added in this order:

1. Shadow Mantle and a generic ranked healing-block primitive.
2. Steal Breath with periodic poison damage and a movement-rate multiplier.
3. Psychic Shield and Mental Shield with typed damage absorbers.
4. Hit rolls, defense, damage distributions, resistances, and interrupt checks driven by the deterministic random source.
5. Build profiles that allocate training points and derive stats at each character level instead of assigning every selected power the same experimental rank.
6. Late progression, especially Mental Projection and Summon Darkspawn, before treating a level-75 result as a complete-kit matchup.

## Reproduction

Run the full matrix locally:

```bash
python -m shadowbane_lab.rollouts \
  --matrix \
  --levels 10,15,18,19,22,26,28,75 \
  --ranks 0,10,20,40 \
  --distances 15,60,110 \
  --seeds 1,2,3 \
  --max-ticks 1200 \
  --json
```

The `Assassin-Warlock duel matrix` GitHub Actions workflow runs the same command, writes JSON and Markdown summaries, and uploads them as a 30-day artifact.
