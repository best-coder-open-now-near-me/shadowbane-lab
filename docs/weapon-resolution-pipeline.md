# Generic weapon-resolution pipeline

Weapon powers are not modeled as class-specific attacks. A normal weapon action now resolves:

1. weapon slot and damage profile;
2. attack rating versus defense;
3. passive block, dodge, and parry checks;
4. base weapon damage plus armed attack modifiers;
5. resistance;
6. typed absorbers;
7. outcome-aware one-shot triggers and persistent procs.

The current centered rating formula and caps are intentionally provisional. Build inputs use generic scalar keys such as `attack_rating`, `defense`, `weapon.main_hand.damage_min`, `resistance.physical`, and `passive.block.chance`, so live WonderBane measurements can replace values without changing the execution architecture.

## Trigger moments

Triggers may fire and consume at `action_start`, `attempt`, `hit`, or positive post-mitigation `damage`; `consume_on: never` represents a persistent proc source. An attack modifier can add attack rating, multiply or add damage, bypass defense or passive defenses, and override damage type. Its payload remains the ordinary typed effect algebra.

Backstab now uses this path: it arms a modifier, consumes on a qualifying swing attempt, adds rank-scaled physical damage, bypasses passive defenses, and removes invisibility. Miss retention and timeout remain calibration questions rather than hidden assumptions.
