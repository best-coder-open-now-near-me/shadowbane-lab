# WonderBane Sun Dancer versus Deflock guide matchup

This scenario executes the complete combat-relevant portions of two archived level-75 builds. It
uses accepted source-revision sheets and explicit ruleset overrides, so the simulator will not
mistake guide-derived values for live-verified character data.

## High-Intelligence Irekei proc Assassin

`wonderbane.irekei-rogue-assassin.sundancer-proc.v1` contains:

- 35 Strength, 102 Dexterity, 85 Constitution, 165 Intelligence and 10 Spirit;
- Sun Dancer, Bounty Hunter, Saboteur and Undead Hunter;
- 161 Light Armor, 161 Unarmed Combat, 70 Unarmed Mastery, 101 Dodge,
  97 Shadowmastery and 21 Stalk;
- independently scheduled Rha'Khanakar- and Khan'Xhir-class hands with the guide's tier-three
  mental-proc scenario;
- Shadow Bolt, Shadow Touch, Backstab, Shadow Mantle, Blind, Shadow of Blindness, Silence,
  Steal Breath, Poison Blade and Consecrate Weapon; and
- defensive stance plus Cloak of Shadows, Poison Blade, Consecrate Weapon, Slayer's Focus,
  Embrace the Phoenix and optional Catlike Tread at combat start.

The sheet has 1,856 health after the sourced Sea Dog's Rest armor-health allowance. Its
Sea Dog's Rest defense and both proc affixes remain source-derived scenarios rather than live
item inspection.

## Shade Fighter defensive Warlock

`wonderbane.shade-fighter-warlock.deflock-guide.v1` contains:

- the guide's unbuffed targets of 50 Strength, 98 Dexterity, 110 Constitution,
  150 Intelligence and 35 Spirit;
- +10 Dexterity gloves, +60 Intelligence jewelry and Free Thought's attribute state in the
  combat sheet;
- Blade Master, Traveler and Bounty Hunter;
- 120 Warlockry, 140 Medium Armor, 100 Sword and 95 Block;
- a Legendary Psiblade of the Mentalist and the guide shield;
- Mind Strike, Mind Snare, Psychic Healing, Psychic Shield, Psychic Shout, Shatter Will,
  Break Enchantment, Dull the Mind, Dull the Body, Surpass Limits and Needs of the One; and
- defensive stance plus Danger Sense, Free Thought, Psychic Shield, Ignore the Old Order and
  Detect Hidden at combat start.

The equipment-defense input is calibrated so the compiled post-buff sheet reaches the guide's
reported 2,030 defense. Exact item rounding, the Legendary/Mentalist values and dynamic
attribute-output recompilation remain accepted source overrides.

## Executable combat semantics

The guide scenario runs through the complete-sheet compiler rather than the older normalized duel
profiles. It includes source-formula attack and defense ratings, power scaling, per-hand weapon
cadence, typed damage and resistances, block/dodge/parry, physical breakpoints, periodic effects,
healing denial, control immunity, AoE origins and target caps, resource costs, movement to range,
and deterministic trigger timing.

Backstab arms the next qualifying melee weapon attempt, bypasses passive defense, inherits that
weapon's typed damage channel, adds its ranked bonus and removes invisibility. Poison Blade,
Consecrate Weapon and item procs fire from the same generic hit-trigger path. Complete-sheet
weapon attacks and older generic weapon recipes therefore share the same attempt, hit, damage and
trigger moments.

Invisible enemies are absent from both observations and target affordances unless the observer has
`detection.see_invisible`. Silence removes active chants and blocks actions tagged as chants; it no
longer suppresses unrelated powers. Needs of the One now rolls to hit, drains only mana the targets
actually possess and credits the caster at its trained conversion efficiency. Break Enchantment
peels one newest matching debuff per cast, preserving cover-debuff behavior, and Mind Snare applies
its trained movement multiplier.

The utility baseline compares attack choices using their actual current hit probability and values
temporary debuffs over a bounded setup horizon. A hidden Assassin arms Backstab before committing
its next qualifying melee attack. The Warlock values Shatter Will from the mental damage it can
deliver during the debuff window, drains only when usable target mana is in range, and declines to
snare a stationary target already in melee range.

## Source-pinned stance profiles

The [Morloch stance table](https://morloch.shadowbaneemulator.com/index.php/Stances) publishes
different values by base class, promotion and trained rank. The guide sheets now keep their normal
ratings immutable and carry these values as separately versioned profiles:

| Rogue Assassin stance | Rank | Attack | Defense | Damage dealt | Weapon delay | Stamina recovery |
|:--|--:|--:|--:|--:|--:|--:|
| Defensive | 20 | -11% | +17% | -7% | — | +24% |
| Offensive | 35 | +9.25% | -23% | — | -23% | — |
| Precise | 25 | +36% | — | -19% | — | — |

| Fighter Warlock stance | Rank | Attack | Defense | Damage dealt | Weapon delay | Movement | Stamina recovery |
|:--|--:|--:|--:|--:|--:|--:|--:|
| Defensive | 30 | -13% | +21% | — | +8.5% | -8.5% | +42% |
| Offensive | 20 | — | -34% | +34% | -17% | — | -14% |
| Precise | 30 | +29.5% | — | — | +21% | — | — |

Normal, offensive, defensive and precise are instant self-actions with an independent 20-second
recycle; choosing one replaces the current state. Attack and defense are recompiled through the
pinned integer OCV/DCV formulas, so the simulator preserves server rounding rather than
multiplying an already-rounded rating. Damage dealt, weapon delay and movement use independent
runtime scalar channels. Stamina recovery is preserved as a state channel, but it will not change
resources until ambient stamina-regeneration ticks are modeled.

The generic policy enters precise only when its projected rating materially improves a hit-floor
matchup, enters offensive only when projected hit-adjusted throughput improves by at least 15%,
and enters or remains defensive below 55% health. Unjustified stance actions are rejected instead
of becoming idle-time stance cycling.

## Running it

Run one deterministic guide duel:

```powershell
$env:PYTHONPATH = "src"
python -m shadowbane_lab.rollouts `
  --scenario wonderbane-guide-duel `
  --distance 15 `
  --episodes 1 `
  --assassin-stealthed `
  --max-ticks 2400 `
  --seed 1 `
  --json
```

Run a contiguous 1,000-seed batch by changing `--episodes` to `1000`. Run a range matrix with:

```powershell
python -m shadowbane_lab.rollouts `
  --scenario wonderbane-guide-duel `
  --matrix `
  --distances 6,15,40,100 `
  --episodes 1000 `
  --assassin-stealthed `
  --max-ticks 2400 `
  --seed 1 `
  --json
```

Omit `--assassin-stealthed` for the visible opener. Programmatic callers can use
`wonderbane_sundancer_deflock_matrix` to cross both opener states in one invocation.

## Stance-aware guide-build sweep

The source-semantics and policy correction checkpoint ran 20 seeds per cell for 2,400 ticks, or
eight minutes of virtual combat. `A/W/D` is Assassin wins, Warlock wins and draws/timeouts:

| Assassin opener | Distance | A/W/D | Mean ticks | Assassin mean final HP | Warlock mean final HP | Assassin mean damage | Warlock mean damage |
|:--|--:|:--:|--:|--:|--:|--:|--:|
| visible | 6 | 0/0/20 | 2,400.00 | 1,169.6 | 1,139.5 | 1,518.5 | 686.4 |
| visible | 15 | 0/0/20 | 2,400.00 | 670.9 | 1,597.7 | 1,060.3 | 1,185.1 |
| visible | 40 | 0/2/18 | 2,353.30 | 576.4 | 1,884.1 | 773.9 | 1,279.6 |
| visible | 100 | 0/1/19 | 2,366.80 | 549.1 | 1,857.2 | 800.8 | 1,306.9 |
| hidden | 6 | 0/0/20 | 2,400.00 | 923.0 | 1,366.9 | 1,291.1 | 933.0 |
| hidden | 15 | 0/0/20 | 2,400.00 | 767.9 | 1,417.0 | 1,241.0 | 1,088.1 |
| hidden | 40 | 0/2/18 | 2,353.40 | 576.9 | 1,878.3 | 779.7 | 1,279.1 |
| hidden | 100 | 0/1/19 | 2,366.85 | 537.8 | 1,849.7 | 808.3 | 1,318.2 |

This remains a mechanics result, not a settled balance verdict. The raw normal sheets compile to
905 Assassin attack / 1,043 defense and 814 Warlock attack / 1,677 defense. Their defensive openers
recompile to the guide-era values of 805 / 1,220 and 708 / 2,030 respectively; precise reaches
1,231 Assassin weapon attack and 1,054 Warlock weapon attack. Stance selection substantially raises
contact over the earlier defensive-only checkpoint, but the tested Assassin still records no wins.
The Warlock wins only at 40 or 100 units; every close cell reaches the time limit. This is a major
change from the previous free-mana behavior: Needs of the One can no longer credit mana after its
target is empty, and both builds exhaust their modeled mana without ambient regeneration or
consumables. The matrix therefore exposes a resource-lifecycle evidence gap rather than establishing
a settled balance result.

The seed-one, 15-unit traces provide a rotation sanity check. The hidden Assassin arms Backstab
exactly once before melee, while the visible Assassin does not try it. The Warlock applies Dull the
Mind, Dull the Body and Shatter Will once each, uses Needs of the One twice while drainable mana
exists, and casts Break Enchantment three times to peel individual debuffs. It does not spam Mind
Snare against the stationary melee target. The Assassin does not waste Silence because this Warlock
has no modeled chant actions. Starting hidden is not uniformly advantageous here: the Deflock has
Detect Hidden, and Backstab's five-second arming commitment can cost more pressure than its one
trigger adds in some seeds.

The result is still constrained by accepted-source gear, proc and power rows. Live max-level sheets
will replace those fields without changing the stance or scenario APIs.

## Remaining evidence gaps

- exact current crafted weapon affixes and item proc rows;
- exact Sea Dog's Rest armor contributions and per-item rounding;
- live WonderBane verification of the source-pinned class/rank stance rows;
- ambient stamina-recovery tick timing;
- ambient mana-recovery timing and the modeled role of consumables;
- Greater Concoction values and stacking;
- dynamic derived-stat recompilation while Dull Mind or Dull Body is active; and
- live max-level resources, ratings, resistances and ordinary pre-fight buff state.

Primary guide inputs are the archived
[Rogue Assassin templates](https://shadowbanetemplates.weebly.com/assassin-rogue-templates.html),
the [Warlock builds page](https://morloch.shadowbaneemulator.com/index.php/Warlock_Builds), the
[WonderBane calculator](https://wonderbane.com/) and the pinned MagicBane formula revision
`3649c629b709c67625a09150a3752107f4b873cc`.
