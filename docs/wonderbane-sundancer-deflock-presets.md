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
`detection.see_invisible`. Silence suppresses actions tagged as powers while leaving ordinary
weapon attacks available. The utility baseline compares attack choices using their actual current
hit probability and values temporary debuffs over a bounded setup horizon.

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

## First guide-build sweep

The implementation checkpoint ran 20 seeds per cell for 2,400 ticks, or eight minutes of virtual
combat. Every cell reached the time limit with both combatants alive:

| Assassin opener | Distance | Assassin mean final HP | Warlock mean final HP | Assassin mean damage | Warlock mean damage |
|:--|--:|--:|--:|--:|--:|
| visible | 6 | 1,232.3 | 2,260.5 | 397.5 | 623.7 |
| visible | 15 | 1,184.9 | 2,241.4 | 416.6 | 671.1 |
| visible | 40 | 1,165.4 | 2,229.8 | 428.2 | 690.6 |
| visible | 100 | 1,084.4 | 2,231.1 | 426.9 | 771.6 |
| hidden | 6 | 1,134.2 | 2,209.4 | 448.6 | 721.8 |
| hidden | 15 | 1,180.9 | 2,207.6 | 450.4 | 675.1 |
| hidden | 40 | 1,090.1 | 2,203.6 | 454.4 | 765.9 |
| hidden | 100 | 1,111.4 | 2,223.2 | 434.8 | 744.6 |

This is a useful mechanics result, not a settled balance result. The compiled defensive sheets
start at 805 Assassin main-hand attack, 708 Warlock main-hand attack, 1,220 Assassin defense and
2,030 Warlock defense. Both characters' base weapon attacks, and the Warlock's 777.78 power attack
against the Assassin, begin at the pinned formula's 4% hit floor. The long timeouts therefore
follow from the guide inputs and current defensive opening state rather than an inactive action
loop.

The next discriminating simulation increment is authoritative numeric stance modifiers and a
stance-selection policy. The simulator already represents normal, offensive, defensive, precise
and travel as exclusive states, but it does not invent current WonderBane rating/damage modifiers.
Live max-level sheets will later replace the remaining accepted-source fields without changing the
scenario API.

## Remaining evidence gaps

- exact current crafted weapon affixes and item proc rows;
- exact Sea Dog's Rest armor contributions and per-item rounding;
- current numeric offensive, defensive and precise stance modifiers;
- Greater Concoction values and stacking;
- dynamic derived-stat recompilation while Dull Mind or Dull Body is active; and
- live max-level resources, ratings, resistances and ordinary pre-fight buff state.

Primary guide inputs are the archived
[Rogue Assassin templates](https://shadowbanetemplates.weebly.com/assassin-rogue-templates.html),
the [Warlock builds page](https://morloch.shadowbaneemulator.com/index.php/Warlock_Builds), the
[WonderBane calculator](https://wonderbane.com/) and the pinned MagicBane formula revision
`3649c629b709c67625a09150a3752107f4b873cc`.
