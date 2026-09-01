# WonderBane Elf Healer Druid guide matchups

This scenario adds a third complete level-75 guide combatant to the verified duel pipeline. The
Druid uses an accepted source-revision sheet and reviewed ruleset overrides; none of its unresolved
gear or deployment-specific values are mislabeled as live verified.

## Elf Healer Druid

`wonderbane.elf-healer-druid.bladeweaver-sanctifier.v1` reconstructs Nobuo's archived build with:

- Elf, Healer base class and Druid promotion;
- Warlord's Page and Tough as Nails;
- Blade Weaver and Sanctifier;
- guide targets of 40 Strength, 50 Dexterity, 120 Constitution, 160 Intelligence and 61 Spirit;
- 130 Nature Lore, 90 Restoration, 95 Block, 60 Sword and 69 Benediction;
- Grasp of Thorns, Hedge of Thorns, Blight, Call Lightning, Regrowth, Blessed Mending,
  Prayer of Mending, Braialla's Aid and Oaken Flesh; and
- defensive stance, Blessing of the Grove and Oaken Flesh at combat start.

Blade Weaver and Sanctifier add 20 Constitution. Blessing of the Grove adds 25 Intelligence and
Spirit, so the executable sheet enters combat at 40 Strength, 50 Dexterity, 140 Constitution,
185 Intelligence and 86 Spirit. The reviewed WonderBane calculator formulas produce 2,171 health,
964 mana and 251 stamina from those inputs; Tough as Nails raises maximum health to 2,371.

The archived guide does not specify exact equipment. The executable scenario therefore uses the
published Cleaver-class 4–15 slash baseline, a shield with the guide's trained block, and zero
invented armor defense or item resistances. This is intentionally conservative and remains
replaceable by a live max-level character sheet.

## Action semantics

The Druid powers are built from the same generic primitives as the existing Assassin and Warlock:

- Grasp of Thorns deals direct and six-pulse pierce damage, removes flight and applies a 15-second
  60% snare.
- Hedge of Thorns applies the corresponding pierce pulse and snare package in a target-centered,
  40-unit, seven-target area.
- Blight deals direct poison damage and six poison pulses.
- Call Lightning is a target-centered, 32-unit, seven-target lightning area with a three-second
  stun, flight removal and nine-second stun immunity.
- Regrowth performs a direct heal and five heal-over-time pulses while removing bleeding.
- Blessed Mending and Prayer of Mending retain their distinct rank, cost, cast, recycle and heal
  bounds instead of being collapsed into one generic heal.
- Braialla's Aid removes poison and disease. The duel policy only casts it when one of those typed
  debuffs is actually present.
- Oaken Flesh carries the published crush, pierce and cold resistance adjustments plus a
  1,000-point physical damage breakpoint. Its pre-fight cast begins with the full 300.2-second
  cooldown, so breaking it cannot produce an impossible immediate refresh.

The [Druid powers table](https://morloch.shadowbaneemulator.com/index.php/Druid_Powers) supplies the
rank-40 values and explicitly describes the Druid as a kiting profession. The simulator therefore
adds a target-relative retreat intent only to builds tagged `behavior.kite`. It layers control or
damage first, then opens to 30 units after the target is snared or stunned. The movement remains a
generic near/far primitive; it does not encode a Druid-specific path or left/right orbit.

## Running it

Run one deterministic Assassin/Druid duel:

```powershell
$env:PYTHONPATH = "src"
python -m shadowbane_lab.rollouts `
  --scenario wonderbane-druid-duels `
  --druid-opponent assassin `
  --distance 15 `
  --episodes 1 `
  --assassin-stealthed `
  --max-ticks 2400 `
  --seed 1 `
  --json
```

Use `--druid-opponent warlock` for the Deflock. The complete matrix crosses both Assassin opener
states and both opponents:

```powershell
python -m shadowbane_lab.rollouts `
  --scenario wonderbane-druid-duels `
  --matrix `
  --distances 6,15,40,100 `
  --episodes 1000 `
  --max-ticks 2400 `
  --seed 1 `
  --json
```

Programmatic callers can use `wonderbane_sundancer_vs_druid`, `wonderbane_deflock_vs_druid` and
`wonderbane_druid_matchup_matrix`.

## Twenty-seed guide sweep

The checked sweep ran 20 contiguous seeds per cell for 2,400 ticks, or eight minutes of virtual
combat. `O/D/R` means opponent wins, Druid wins and draws/timeouts.

| Opponent | Assassin opener | Distance | O/D/R | Mean ticks | Opponent mean final HP | Druid mean final HP | Opponent mean damage | Druid mean damage |
|:--|:--|--:|:--:|--:|--:|--:|--:|--:|
| Assassin | visible | 6 | 0/19/1 | 284.4 | 7.2 | 2,158.7 | 212.3 | 1,848.8 |
| Assassin | visible | 15 | 0/20/0 | 182.7 | 0.0 | 2,221.8 | 149.2 | 1,856.0 |
| Assassin | visible | 40 | 0/19/1 | 295.4 | 25.0 | 2,186.6 | 184.4 | 1,831.0 |
| Assassin | visible | 100 | 0/20/0 | 187.6 | 0.0 | 2,215.0 | 156.0 | 1,856.0 |
| Assassin | hidden | 6 | 0/20/0 | 211.1 | 0.0 | 2,060.0 | 311.0 | 1,856.0 |
| Assassin | hidden | 15 | 0/19/1 | 365.1 | 16.9 | 1,983.5 | 387.5 | 1,839.1 |
| Assassin | hidden | 40 | 0/20/0 | 237.8 | 0.0 | 2,101.8 | 269.2 | 1,856.0 |
| Assassin | hidden | 100 | 0/20/0 | 251.2 | 0.0 | 2,117.0 | 254.0 | 1,856.0 |
| Deflock | n/a | 6 | 0/0/20 | 2,400.0 | 2,038.3 | 1,516.7 | 2,433.6 | 619.7 |
| Deflock | n/a | 15 | 0/0/20 | 2,400.0 | 2,034.4 | 1,483.1 | 2,459.0 | 623.6 |
| Deflock | n/a | 40 | 0/0/20 | 2,400.0 | 2,196.3 | 1,494.7 | 2,442.7 | 461.7 |
| Deflock | n/a | 100 | 0/0/20 | 2,400.0 | 2,167.3 | 1,532.9 | 2,327.2 | 490.7 |

The initial expectation that both existing builds would beat this Druid is not supported by the
source-bounded model. The Druid records 157 wins and three timeouts against the Assassin, with no
Assassin wins. Oaken Flesh sharply reduces the build's crush pressure while the Druid layers
long-duration damage, cleanses poison and preserves distance. Hidden Backstab openers raise the
Assassin's mean damage in several cells but do not reverse the matchup.

Every Deflock cell times out. The Warlock wins the resource exchange: it applies the output and
attribute debuffs, uses Needs of the One while mana remains, reduces the Druid to roughly zero mana
and deals 2,327–2,459 mean damage. The Druid restores 1,489–1,579 mean health, then keeps retreating
at equal speed after both sides lose their remaining productive casts. This is a coherent
long-horizon stalemate under the current primitives, not evidence that the live matchup is a draw.

No cell records a rejected action.

## Remaining evidence boundaries

- a live max-level Druid sheet, exact robe/shield/sword affixes, defense and resistances;
- current WonderBane power tokens, rank rounding and same-power stack/refresh behavior;
- the Oaken Flesh source conflict: the current page lists cold rather than slash resistance while
  the physical breakpoint covers crush, pierce and slash in this scenario;
- ambient health, mana and stamina regeneration, including Spirit scaling;
- consumable timing and inventory limits;
- collision, finite arena boundaries and terrain-aware chase geometry; and
- current deployment verification of class/rank stance rows.

The primary build input is the archived
[Druid templates page](https://shadowbanetemplates.weebly.com/druid-templates.html). Static class,
discipline and resource inputs come from the reviewed [WonderBane calculator](https://wonderbane.com/),
the [Druid class page](https://morloch.shadowbaneemulator.com/index.php/Druid),
[base-class powers](https://morloch.shadowbaneemulator.com/index.php/Base_Class_Powers),
[stances](https://morloch.shadowbaneemulator.com/index.php/Stances),
[starting traits](https://morloch.shadowbaneemulator.com/index.php/Starting_Traits) and
[sword weapons](https://morloch.shadowbaneemulator.com/index.php/Sword_Weapons).
