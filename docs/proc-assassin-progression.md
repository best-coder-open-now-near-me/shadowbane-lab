# Irekei unarmed-proc Assassin progression

The `irekei-proc` scenario is a sourced build evaluator for an Irekei Rogue promoted to
Assassin on WonderBane. It is separate from the generic combat environment because character
legality, allocation budgets, and derived build features must be established before those
features become combat actions.

```powershell
$env:PYTHONPATH = "src"
python -m shadowbane_lab.rollouts --scenario irekei-proc --level 59 --json
```

The profile pins the current WonderBane calculator values retrieved on 2026-08-26 and
revision-pinned Morloch pages for formulas, training budgets, proc mechanics, Sun Dancer,
and unarmed weapons. The community high-proc template is retained as a comparison candidate,
not as a claim about current-server legality.

## Live build audit

`client advise-irekei-proc` composes the scalar progression reader with the lossless skill/power
vector reader. The verified level-59 snapshot had 113 training points remaining and already met
the roadmap targets for Poison Blade, Cloak of Shadows, Shadow Touch, Blindness, Steal Breath,
Silence, Backstab, and Slayer's Focus. Four power targets were below the mixed/PvP roadmap:
Shadow Mantle `24 -> 40`, Sneak `20 -> 21`, Plague of Blindness `1 -> 30`, and Shadow Bolt
`2 -> 5`, totaling 49 one-point power-rank increments.

The same snapshot showed Unarmed, Unarmed Mastery, and Light Armor at 110, Shadowmastery at 100,
and Dodge at 46. End-state displayed-rank gaps are reported independently: Unarmed `110 -> 161`,
Light Armor `110 -> 161`, and Dodge `46 -> 100`. They are targets, not an instruction to spend
blindly; numeric attribute caps and equipment were required inputs before committing the 168
unspent ability points or training beyond the current focus cap.

Live Runestones inspection then identified `Brilliant Mind` and `Wizard's Apprentice` as the two
creation traits, with no disciplines applied. Those traits establish pre-rune caps of
`85/130/85/130/80`. Applying Sun Dancer and Saboteur first adds 5 Constitution and 20 Dexterity,
and raises those caps by the same amounts. A Godly Intelligence rune applied at 120 INT raises
Intelligence by 10 and its cap by 40. The exact level-59 high-proc allocation from
`35/55/57/80/15` is therefore:

1. Apply Sun Dancer and Saboteur, resulting in `35/75/62/80/15` without spending ability points.
2. Raise Intelligence `80 -> 120` (40 points).
3. Apply Intelligence of the Gods (15 points, resulting in 130 INT and a 170 cap).
4. Raise Intelligence `130 -> 165` (35 points).
5. Raise Constitution `62 -> 85` (23 points).
6. Put the remaining 55 points into Dexterity, ending at `35/130/85/165/15`.

That consumes all 168 currently unspent points. The plan is included as the first simulator
candidate; its order matters because discipline grants affect the allocation and the Godly rune
requires 120 INT.

## Known facts in the slice

- An Irekei Rogue has 526 earned training points at level 59 and 588 at level 75.
- WonderBane grants two discipline slots below level 70 and three at level 70 or above.
- Sun Dancer grants the unarmed path and ambidexterity; Saboteur currently grants 20 Dexterity
  and 20 Dexterity cap in the server calculator.
- A proc checks at 5% per successful hit, scales primarily from Intelligence through the
  spell-damage formula, and benefits from fast weapons.
- The baseline Rha'khanakar and generic fast-fist models use speed 20.0, or two seconds per
  hand before speed modifiers, with the global one-attack-per-hand-per-second cap.

## Deliberate boundaries

Proc comparisons are normalized to successful hits and exclude target defense, resistance,
buffs, gear attack rating, and the server-specific legality of unknown creation traits. The
`CharacterProgressionObservation` contract carries current stats/caps, remaining points,
skill and power ranks, discipline runes, and equipment. The live harness should populate that
contract from the client data model before a real allocation is committed.

The ArcHUD skin configuration exposes upstream data-field identifiers for the five attributes,
their qualitative ratings, remaining ability points, and skill list. Live inspection confirmed
that fields 35-39 render labels such as `Average`, `Very Good`, and `Excellent`; they are not
numeric caps. Those identifiers are data-model seams, not screen coordinates. Numeric attribute
caps are not currently exposed by the native reader. This known build derives them from the
observed creation traits, the planned disciplines, and the sourced rune table; unknown rune
combinations still require independent calibration before real ability-point allocation.
