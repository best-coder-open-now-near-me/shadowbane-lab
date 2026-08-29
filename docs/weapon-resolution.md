# Weapon action resolution and build-search ablation

This document records the first generic weapon-action pipeline used by the open build explorer. The implementation is deliberately parameterized: current numbers are useful harness defaults, not claims that WonderBane uses the same formulas or ordering.

## Resolution pipeline

A weapon action now resolves through one shared sequence:

```text
weapon action reaches its configured phase
    -> collect every matching armed or persistent trigger
    -> resolve attempt-time trigger checks and modifiers
    -> roll attack rating against defense
    -> evaluate ordered passive defenses unless bypassed
    -> roll the weapon's damage range
    -> combine all fired attack modifiers
    -> apply resistance and then absorber pools
    -> apply remaining health damage
    -> resolve hit-time and damage-time trigger payloads
    -> consume each trigger at its configured boundary
```

The action declares its weapon slot, damage type, phase index, scalar names, fallback values, hit-chance bounds, and passive-defense order. Character bodies and equipment provide concrete values through ordinary scalar maps such as:

```text
attack_rating
defense
weapon.main_hand.damage_min
weapon.main_hand.damage_max
resistance.physical
passive.block.chance
passive.dodge.chance
```

This lets live character snapshots, package inventories, historical templates, and generated bodies all use the same action recipe.

## Trigger timing

Triggers now distinguish four moments:

- action start
- weapon attempt
- successful hit after passive defenses
- positive post-mitigation damage

Consumption independently supports those moments plus `never`. A persistent equipment proc can therefore fire on hit without being consumed, while a manually armed weapon power can be consumed on the attempt even when the swing misses.

An attack modifier may change:

- attack rating
- damage multiplier
- bonus damage range
- defense bypass
- passive-defense bypass
- damage type
- semantic event tags

Payload effects remain ordinary typed primitives and can add damage, control, exposes, dispels, drains, or other state changes after the configured trigger moment.

## Backstab mapping

Backstab no longer applies an immediate damage payload. It now:

```text
requires stealth, a melee weapon, and Stalk access
    -> spends stamina
    -> arms a timed next-weapon-power state
    -> waits for an attack + weapon + melee action
    -> consumes on the weapon attempt
    -> bypasses passive defenses for that swing
    -> adds its ranked damage bonus to the ordinary weapon roll
    -> removes invisibility
```

The miss-retention choice, exact armed timeout, per-hand qualification, and weapon-swap cancellation remain calibration questions. The current mapping consumes on attempt, which is explicit and replaceable rather than hidden in Backstab-specific code.

## Defense and mitigation

The current generic ordering is:

```text
attack/defense roll
    -> block, dodge, parry or other declared passive defenses
    -> resistance floor/cap
    -> matching typed or universal absorber pools
    -> health
```

Absorbers are ordinary active effects tagged for a damage type or for all damage. Their magnitude is a consumable pool. Earliest-expiring pools are consumed first, and depleted effects are removed with explicit events.

Direct `DealDamage` effects use the same resistance and absorber path, so spell and proc damage no longer bypass mitigation merely because they did not originate from a weapon action.

## Trace output

The semantic trace now records:

- attack rating, defense, hit chance and random roll
- hit or miss
- passive-defense activations and their rolls
- requested damage
- effective resistance and resisted amount
- absorber consumption and remaining pool
- final effective health damage
- trigger checks, chances, rolls, fires and consumption
- weapon slot and modifier tags

This makes a surprising result inspectable without relying only on the final winner.

## Validation

Focused regressions cover:

1. resistance before absorber consumption;
2. a passive defense preventing an ordinary swing;
3. Backstab bypassing passive defense and adding bonus weapon damage;
4. a miss consuming Backstab without firing its hit result;
5. a never-consumed on-hit proc firing repeatedly;
6. multiple armed attack modifiers contributing to the same qualifying swing;
7. generic body scalars flowing through loadouts and package assemblies.

The complete repository suite currently passes 139 tests on Python 3.11, 3.12 and 3.13, together with Ruff lint and formatting checks.

## First body-versus-recipe ablation

Sixteen generated loadouts were crossed at 60 units, three seeds and both orientations. Each variant produced 720 playouts and 720 unique traces.

| Variant | Time limits | Top win rate |
|:---|---:|---:|
| Mixed random bodies and recipe bags | 150 | 86.7% |
| One fixed body with varied recipe bags | 36 | 91.1% |
| Varied bodies with only common movement and weapon attacks | 136 | 75.6% |

The mixed ranking correlated only **0.162** with the fixed-body recipe ranking, but **0.921** with the body-only ranking. In this deliberately broad generator, body rolls currently dominate the mixed leaderboard.

That is a search-method finding, not a balance conclusion. Recipe discovery and body optimization should be separate experiments:

```text
fixed body + varied recipe bags
    -> discover useful behavior combinations

fixed recipe bag + varied body/equipment packages
    -> optimize realization of that behavior

legal package closure
    -> map the promising pair back to a buildable WonderBane character
```

Within the fixed-body sample, healing, ranged damage and invisibility were associated with the strongest recipe bags, but the sample is small and the present recipe catalog is still narrow. Those signals should guide the next catalog expansion, not be treated as settled rankings.

## Next fidelity increments

The most reusable next additions are:

1. per-hand and dual-wield attack schedules;
2. attack-delay modifiers and recovery timing;
3. typed exposes and armor-piercing interaction with resistance;
4. shields and non-pool defensive effects;
5. periodic effects and pulse-triggered procs;
6. live-derived body and equipment scalar packages;
7. availability constraints for actual owned runes and equipment.

The pipeline is already able to accept later WonderBane corrections by changing scalar values, action recipes, trigger moments, consumption rules, or ordering policies without restoring class-specific combat code.