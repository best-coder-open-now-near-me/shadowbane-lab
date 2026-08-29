# WonderBane Sun Dancer versus Deflock presets

This slice turns two recognizable player builds into explicit harness presets without pretending
that the current simulator already models their full sheets.

## Assassin preset

`wonderbane.irekei-rogue-assassin.sundancer-proc.v1` follows the historical high-Intelligence
Irekei Rogue Assassin shell most closely matching the intended character:

- attributes: 35 Strength, 102 Dexterity, 85 Constitution, 165 Intelligence, 10 Spirit;
- disciplines: Sun Dancer, Bounty Hunter, Saboteur and Undead Hunter;
- primary skills: 161 Light Armor, 161 Unarmed Combat, 70 Unarmed Mastery, 101 Dodge,
  97 Shadowmastery and 21 Stalk;
- dual fast Khan'Xhir/Rha'Khanakar-class proc weapons;
- Sea Dog's Rest-quality light armor and ordinary Constitution/Dexterity jewelry;
- Greater Concoction as the normal pre-fight environment.

The full descriptive kit is retained on the preset. The first executable subset is deliberately
smaller: Shadow Bolt 5, Shadow Touch 40, Backstab 1 and Shadow Mantle 40. Fade and Invisibility
are excluded because this is a Rogue-base Assassin rather than the Mage-base stealth path.

## Warlock preset

`wonderbane.shade-fighter-warlock.deflock-sdr.v1` uses the established Shade Fighter defensive
Warlock shell:

- 150 Intelligence, 110 Constitution and all remaining allocation intended for Dexterity;
- Blade Master, Bounty Hunter and provisional Commander;
- 120 Warlockry, 140 Medium Armor, 100 Sword and 95 Block;
- Sea Dog's Rest Alloyed Imperial armor, blocking shield and Psiblade;
- Greater Concoction, defensive stance, Danger Sense, Free Thought and Psychic Shield as the
  intended pre-fight state.

The first executable subset is Mind Strike 40, Mind Snare 1 and Psychic Healing 40. The defense,
Block, shield, armor, Detect Hidden, debuffs, absorbers and self-buffs remain descriptive until the
engine has mechanics that can represent them. Commander contributes no assumed chant bonus while
its overlap with Concoction and Battlemind remains unverified.

## What these presets are for

They provide a stable place to replace normalized placeholders one field at a time. The initial
smoke duel verifies only that the selected power subsets compile and execute without rejected
actions. It is not a balance result.

Before interpreting a matchup matrix, the harness still needs meaningful implementations for:

1. hit chance, defense, Block and passive defense;
2. weapon cadence, dual wield and proc triggering;
3. typed damage, resistance and absorbers;
4. Danger Sense, Psychic Shield, Detect Hidden and the relevant debuffs;
5. Poison Blade, Steal Breath, blinds and the selected Sun Dancer actions;
6. Backstab as setup followed by a qualifying weapon swing;
7. live-sheet health, mana, stamina, movement and equipment values.

## Later live-sheet calibration

The preset can be corrected directly from a character-sheet capture. The most useful Assassin
capture is a readable record of final attributes, trained skills, power ranks, equipped items and
the ordinary pre-duel buff icons. The same capture from the constructed Warlock will replace the
remaining-Dexterity and normalized-resource placeholders.
