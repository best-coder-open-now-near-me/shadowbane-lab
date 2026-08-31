import json
import unittest
from contextlib import redirect_stdout
from io import StringIO

from shadowbane_lab.combat import CompatibilityStatus
from shadowbane_lab.combat.compiler import (
    CombatCompilePolicy,
    compile_combatant,
)
from shadowbane_lab.protocol import Vector2
from shadowbane_lab.rollouts import (
    run_verified_duel,
    wonderbane_deflock,
    wonderbane_deflock_vs_druid,
    wonderbane_druid_matchup_matrix,
    wonderbane_elf_healer_druid,
    wonderbane_sundancer_deflock_matrix,
    wonderbane_sundancer_proc_assassin,
    wonderbane_sundancer_vs_deflock,
    wonderbane_sundancer_vs_druid,
)
from shadowbane_lab.rollouts.__main__ import main
from shadowbane_lab.rollouts.duel import (
    BACKSTAB,
    MIND_SNARE,
    MIND_STRIKE,
    PSYCHIC_HEALING,
    SHADOW_BOLT,
    SHADOW_MANTLE,
    SHADOW_TOUCH,
)
from shadowbane_lab.rollouts.presets import (
    BLESSED_MENDING,
    BLIGHT,
    BLIND,
    BRAIALLAS_AID,
    BREAK_ENCHANTMENT,
    CALL_LIGHTNING,
    CONSECRATE_WEAPON,
    DULL_THE_BODY,
    DULL_THE_MIND,
    GRASP_OF_THORNS,
    HEDGE_OF_THORNS,
    NEEDS_OF_THE_ONE,
    OAKEN_FLESH,
    POISON_BLADE,
    PRAYER_OF_MENDING,
    PSYCHIC_SHIELD,
    PSYCHIC_SHOUT,
    REGROWTH,
    SHADOW_OF_BLINDNESS,
    SHATTER_WILL,
    SILENCE,
    STEAL_BREATH,
    SURPASS_LIMITS,
)
from shadowbane_lab.rollouts.ruleset import (
    load_assassin_warlock_duel_ruleset,
    load_wonderbane_guide_duel_ruleset,
)
from shadowbane_lab.sim import (
    ApplyEffect,
    AreaEffect,
    AreaOrigin,
    AttackKind,
    CombatStance,
    DamageBreakpoint,
    DealDamage,
    PeriodicPulse,
    RemoveEffect,
    ResistanceAdjustment,
    RestoreResource,
    ScalarMultiplier,
    TransferResource,
)


class WonderBanePresetTests(unittest.TestCase):
    def test_sundancer_preset_compiles_the_full_archived_combat_loadout(self) -> None:
        preset = wonderbane_sundancer_proc_assassin()
        attributes = dict(preset.attribute_targets)
        intended = dict(preset.intended_power_ranks)
        enabled = set(preset.build.enabled_power_keys or ())

        self.assertEqual(165, attributes["intelligence"])
        self.assertEqual(102, attributes["dexterity"])
        self.assertEqual(85, attributes["constitution"])
        self.assertEqual(
            {"sun_dancer", "bounty_hunter", "saboteur", "undead_hunter"},
            set(preset.disciplines),
        )
        self.assertEqual(1, intended[BACKSTAB])
        self.assertEqual(40, intended[SHADOW_MANTLE])
        self.assertEqual(
            {
                SHADOW_BOLT,
                SHADOW_TOUCH,
                BACKSTAB,
                SHADOW_MANTLE,
                BLIND,
                SHADOW_OF_BLINDNESS,
                SILENCE,
                STEAL_BREATH,
                POISON_BLADE,
                CONSECRATE_WEAPON,
            },
            enabled,
        )
        self.assertIsNotNone(preset.combat_sheet.off_hand_weapon)
        self.assertIn("equipment.melee_weapon", preset.combat_sheet.tags)
        self.assertIn("power.stalk", preset.combat_sheet.tags)
        self.assertIn("poison_blade_proc", {item.effect_key for item in preset.initial_effects})
        concoction = next(
            effect for effect in preset.initial_effects if effect.effect_key == "greater_concoction"
        )
        self.assertEqual(3_600_000, concoction.duration_ms)
        self.assertEqual(35, concoction.trains)
        self.assertEqual(
            {"attack_speed.buff", "attribute.buff", "defense.buff", "mana_recovery.buff"},
            set(concoction.tags) - {"buff"},
        )
        stances = {profile.stance: profile for profile in preset.combat_sheet.stance_profiles}
        self.assertEqual(0.36, stances[CombatStance.PRECISE].modifiers.attack_percent)
        self.assertEqual(-0.23, stances[CombatStance.OFFENSIVE].modifiers.weapon_delay_percent)
        self.assertEqual(0.0, preset.combat_sheet.modifiers.negative_ocv_percent)
        assert preset.combat_sheet.weapon is not None
        self.assertEqual(0.0, preset.combat_sheet.weapon.character_damage_percent)
        self.assertEqual(-0.36, preset.combat_sheet.weapon.attack_delay_percent)
        self.assertEqual(
            (93, 175, 159, 223, 68),
            (
                preset.combat_sheet.strength,
                preset.combat_sheet.dexterity,
                preset.combat_sheet.constitution,
                preset.combat_sheet.intelligence,
                preset.combat_sheet.spirit,
            ),
        )
        self.assertEqual(
            (2770.0, 671.0, 585.0),
            (
                preset.combat_sheet.maximum_health,
                preset.combat_sheet.maximum_mana,
                preset.combat_sheet.maximum_stamina,
            ),
        )
        self.assertAlmostEqual(989.66, preset.combat_sheet.equipment_defense)
        self.assertEqual(295.2, preset.combat_sheet.modifiers.flat_dcv)
        resistances = dict(preset.combat_sheet.resistances)
        self.assertEqual(
            {"crush": 20.0, "pierce": 20.0, "slash": 20.0},
            {key: resistances[key] for key in ("crush", "pierce", "slash")},
        )
        self.assertEqual(15.0, resistances["fire"])
        self.assertEqual(-15.0, resistances["cold"])

        compiled = compile_combatant(
            preset.combat_sheet,
            preset.build,
            load_wonderbane_guide_duel_ruleset(rank_overrides=dict(preset.build.power_ranks)),
            policy=CombatCompilePolicy(
                accepted_compatibility=(CompatibilityStatus.SOURCE_REVISION_ACCEPTED,),
                allow_ruleset_overrides=True,
            ),
        )
        entity = compiled.entity("assassin", "red", Vector2(0.0, 0.0))
        self.assertEqual(1634.0, entity.effective_scalar("defense"))
        entity.stance = CombatStance.DEFENSIVE
        self.assertEqual(1912.0, entity.effective_scalar("defense"))
        self.assertEqual(937.0, entity.effective_scalar("attack.main_hand"))
        self.assertTrue(preset.unresolved)

    def test_deflock_preset_compiles_the_full_archived_combat_loadout(self) -> None:
        preset = wonderbane_deflock()
        attributes = dict(preset.attribute_targets)
        skills = dict(preset.skill_ranks)
        enabled = set(preset.build.enabled_power_keys or ())

        self.assertEqual(150, attributes["intelligence"])
        self.assertEqual(110, attributes["constitution"])
        self.assertEqual(120, skills["warlockry"])
        self.assertEqual(140, skills["medium_armor"])
        self.assertEqual(95, skills["block"])
        self.assertEqual(
            {
                MIND_STRIKE,
                MIND_SNARE,
                PSYCHIC_HEALING,
                PSYCHIC_SHIELD,
                PSYCHIC_SHOUT,
                SHATTER_WILL,
                BREAK_ENCHANTMENT,
                DULL_THE_MIND,
                DULL_THE_BODY,
                SURPASS_LIMITS,
                NEEDS_OF_THE_ONE,
            },
            enabled,
        )
        self.assertEqual(
            {"blade_master", "traveler", "bounty_hunter"},
            set(preset.disciplines),
        )
        self.assertNotIn("discipline.commander", preset.tags)
        self.assertIn("psychic_shield", {item.effect_key for item in preset.initial_effects})
        stances = {profile.stance: profile for profile in preset.combat_sheet.stance_profiles}
        self.assertEqual(0.295, stances[CombatStance.PRECISE].modifiers.attack_percent)
        self.assertEqual(0.34, stances[CombatStance.OFFENSIVE].modifiers.damage_dealt_percent)
        self.assertEqual(-0.085, stances[CombatStance.DEFENSIVE].modifiers.movement_percent)
        self.assertEqual(30.0, preset.combat_sheet.move_speed)
        self.assertEqual(0.0, preset.combat_sheet.modifiers.positive_dcv_percent)
        self.assertTrue(preset.unresolved)

    def test_elf_druid_preset_preserves_guide_training_and_pre_fight_state(self) -> None:
        preset = wonderbane_elf_healer_druid()
        attributes = dict(preset.attribute_targets)
        skills = dict(preset.skill_ranks)
        enabled = set(preset.build.enabled_power_keys or ())

        self.assertEqual(120, attributes["constitution"])
        self.assertEqual(160, attributes["intelligence"])
        self.assertEqual(130, skills["nature_lore"])
        self.assertEqual(90, skills["restoration"])
        self.assertEqual(95, skills["block"])
        self.assertEqual({"blade_weaver", "sanctifier"}, set(preset.disciplines))
        self.assertEqual(
            {
                GRASP_OF_THORNS,
                HEDGE_OF_THORNS,
                BLIGHT,
                CALL_LIGHTNING,
                REGROWTH,
                BLESSED_MENDING,
                PRAYER_OF_MENDING,
                BRAIALLAS_AID,
                OAKEN_FLESH,
            },
            enabled,
        )
        self.assertEqual(140, preset.combat_sheet.constitution)
        self.assertEqual(185, preset.combat_sheet.intelligence)
        self.assertEqual(86, preset.combat_sheet.spirit)
        self.assertEqual(2371.0, preset.combat_sheet.maximum_health)
        self.assertEqual(964.0, preset.combat_sheet.maximum_mana)
        self.assertEqual(0.0, preset.combat_sheet.equipment_defense)
        self.assertIn("behavior.kite", preset.combat_sheet.tags)
        self.assertEqual(((OAKEN_FLESH, 300_200),), preset.initial_cooldowns)
        self.assertEqual(
            {"blessing_of_the_grove", "oaken_flesh"},
            {effect.effect_key for effect in preset.initial_effects},
        )
        oaken = next(
            effect for effect in preset.initial_effects if effect.effect_key == "oaken_flesh"
        )
        self.assertEqual(
            3,
            sum(isinstance(modifier, ResistanceAdjustment) for modifier in oaken.modifiers),
        )
        self.assertTrue(any(isinstance(modifier, DamageBreakpoint) for modifier in oaken.modifiers))
        stances = {profile.stance: profile for profile in preset.combat_sheet.stance_profiles}
        self.assertEqual(0.38, stances[CombatStance.OFFENSIVE].modifiers.damage_dealt_percent)
        self.assertEqual(0.17, stances[CombatStance.DEFENSIVE].modifiers.defense_percent)

    def test_druid_actions_compile_their_distinct_area_dot_heal_and_cleanse_shapes(
        self,
    ) -> None:
        ruleset = load_wonderbane_guide_duel_ruleset()
        self.assertEqual(ruleset, load_assassin_warlock_duel_ruleset())

        grasp = ruleset.record(GRASP_OF_THORNS).action
        hedge = ruleset.record(HEDGE_OF_THORNS).action
        regrowth = ruleset.record(REGROWTH).action
        cleanse = ruleset.record(BRAIALLAS_AID).action
        oaken = ruleset.record(OAKEN_FLESH).action
        assert all(action is not None for action in (grasp, hedge, regrowth, cleanse, oaken))
        assert grasp is not None and hedge is not None and regrowth is not None
        assert cleanse is not None and oaken is not None

        self.assertTrue(any(isinstance(effect, DealDamage) for effect in grasp.phases[0].effects))
        grasp_carrier = next(
            effect
            for effect in grasp.phases[0].effects
            if isinstance(effect, ApplyEffect) and effect.effect_key == "grasp_of_thorns"
        )
        self.assertTrue(
            any(isinstance(modifier, PeriodicPulse) for modifier in grasp_carrier.modifiers)
        )
        hedge_area = next(
            effect for effect in hedge.phases[0].effects if isinstance(effect, AreaEffect)
        )
        self.assertIs(AreaOrigin.TARGET, hedge_area.origin)
        self.assertEqual(40.0, hedge_area.radius)

        self.assertTrue(
            any(isinstance(effect, RestoreResource) for effect in regrowth.phases[0].effects)
        )
        regrowth_carrier = next(
            effect for effect in regrowth.phases[0].effects if isinstance(effect, ApplyEffect)
        )
        self.assertTrue(
            any(isinstance(modifier, PeriodicPulse) for modifier in regrowth_carrier.modifiers)
        )
        self.assertEqual(
            {"poison", "disease"},
            {
                effect.matching_tag
                for effect in cleanse.phases[0].effects
                if isinstance(effect, RemoveEffect)
            },
        )
        oaken_effect = next(
            effect for effect in oaken.phases[0].effects if isinstance(effect, ApplyEffect)
        )
        self.assertTrue(
            any(isinstance(modifier, DamageBreakpoint) for modifier in oaken_effect.modifiers)
        )

    def test_druid_matchups_execute_kiting_healing_cleanse_and_initial_cooldown(self) -> None:
        assassin_duel = run_verified_duel(
            wonderbane_sundancer_vs_druid(
                starting_distance=15.0,
                max_ticks=500,
                seed=1,
                assassin_starts_stealthed=True,
            )
        ).duel
        warlock_duel = run_verified_duel(
            wonderbane_deflock_vs_druid(
                starting_distance=15.0,
                max_ticks=500,
                seed=1,
            )
        ).duel

        for duel in (assassin_duel, warlock_duel):
            druid = duel.combatants[1]
            actions = {item.action_key.split("@")[0]: item.count for item in druid.actions}
            self.assertIn(GRASP_OF_THORNS, actions)
            self.assertIn("sim.range.open", actions)
            self.assertNotIn(OAKEN_FLESH, actions)
            self.assertEqual(0, druid.rejected_actions)
        assassin_actions = {
            item.action_key.split("@")[0] for item in assassin_duel.combatants[1].actions
        }
        self.assertIn(BRAIALLAS_AID, assassin_actions)
        self.assertTrue(
            {REGROWTH, BLESSED_MENDING, PRAYER_OF_MENDING}
            & {item.action_key.split("@")[0] for item in warlock_duel.combatants[1].actions}
        )

    def test_druid_matrix_covers_both_opponents_and_assassin_openers(self) -> None:
        cells = wonderbane_druid_matchup_matrix(
            starting_distances=(15.0,),
            assassin_stealth_openers=(False, True),
            episodes=2,
            max_ticks=50,
            seed_start=3,
        )

        self.assertEqual(3, len(cells))
        self.assertEqual({"assassin", "warlock"}, {cell.opponent for cell in cells})
        self.assertEqual(
            {False, True},
            {cell.assassin_starts_stealthed for cell in cells if cell.opponent == "assassin"},
        )
        self.assertTrue(all(cell.batch.episodes == 2 for cell in cells))

    def test_druid_cli_runs_a_named_opponent_and_the_complete_matrix(self) -> None:
        single_output = StringIO()
        with redirect_stdout(single_output):
            single_exit = main(
                (
                    "--scenario",
                    "wonderbane-druid-duels",
                    "--druid-opponent",
                    "warlock",
                    "--episodes",
                    "1",
                    "--max-ticks",
                    "20",
                    "--json",
                )
            )
        single = json.loads(single_output.getvalue())

        matrix_output = StringIO()
        with redirect_stdout(matrix_output):
            matrix_exit = main(
                (
                    "--scenario",
                    "wonderbane-druid-duels",
                    "--matrix",
                    "--distances",
                    "15",
                    "--episodes",
                    "1",
                    "--max-ticks",
                    "20",
                    "--json",
                )
            )
        matrix = json.loads(matrix_output.getvalue())

        self.assertEqual(0, single_exit)
        self.assertEqual(0, matrix_exit)
        self.assertEqual("complete_combat_sheet", single["mode"])
        self.assertEqual(3, len(matrix))
        self.assertEqual({"assassin", "warlock"}, {cell["opponent"] for cell in matrix})

    def test_guide_action_semantics_preserve_chant_denial_transfer_and_snare_state(self) -> None:
        ruleset = load_assassin_warlock_duel_ruleset()
        silence = ruleset.record(SILENCE).action
        needs = ruleset.record(NEEDS_OF_THE_ONE).action
        snare = ruleset.record(MIND_SNARE).action
        dispel = ruleset.record(BREAK_ENCHANTMENT).action

        assert silence is not None and needs is not None and snare is not None
        assert dispel is not None
        silenced = next(
            effect for effect in silence.phases[0].effects if isinstance(effect, ApplyEffect)
        )
        self.assertIn("control.block.action_tag.chant", silenced.tags)
        self.assertNotIn("control.silence", silenced.tags)
        self.assertIn("denies.action_tag.chant", silence.tags)

        area = next(effect for effect in needs.phases[0].effects if isinstance(effect, AreaEffect))
        transfer = next(effect for effect in area.effects if isinstance(effect, TransferResource))
        self.assertIs(AttackKind.POWER, needs.hit_roll)
        self.assertAlmostEqual(17.15, transfer.amount)
        self.assertAlmostEqual(0.415, transfer.efficiency)

        snare_effect = next(
            effect for effect in snare.phases[0].effects if isinstance(effect, ApplyEffect)
        )
        slow = next(
            modifier
            for modifier in snare_effect.modifiers
            if isinstance(modifier, ScalarMultiplier)
        )
        self.assertIn("applies.snared", snare.tags)
        self.assertAlmostEqual(0.4, slow.factor)

        removal = next(
            effect for effect in dispel.phases[0].effects if isinstance(effect, RemoveEffect)
        )
        self.assertEqual(1, removal.maximum_count)

    def test_hidden_opener_arms_backstab_and_sets_up_the_warlock_debuff_stack(self) -> None:
        result = run_verified_duel(
            wonderbane_sundancer_vs_deflock(
                starting_distance=15.0,
                max_ticks=8,
                seed=1,
                assassin_starts_stealthed=True,
            )
        ).duel
        assassin, warlock = result.combatants
        assassin_actions = {item.action_key.split("@")[0]: item.count for item in assassin.actions}
        warlock_actions = {item.action_key.split("@")[0]: item.count for item in warlock.actions}

        self.assertEqual(1, assassin_actions[BACKSTAB])
        self.assertEqual(1, warlock_actions[DULL_THE_MIND])
        self.assertEqual(1, warlock_actions[DULL_THE_BODY])
        self.assertEqual(1, warlock_actions[SHATTER_WILL])

    def test_reconstructed_assassin_keeps_the_bounded_warlock_policy_trace(self) -> None:
        result = run_verified_duel(
            wonderbane_sundancer_vs_deflock(
                starting_distance=15.0,
                max_ticks=2_400,
                seed=1,
                assassin_starts_stealthed=True,
            )
        ).duel
        assassin, warlock = result.combatants
        assassin_actions = {item.action_key.split("@")[0]: item.count for item in assassin.actions}
        warlock_actions = {item.action_key.split("@")[0]: item.count for item in warlock.actions}

        self.assertNotIn(SILENCE, assassin_actions)
        self.assertEqual(1, warlock_actions[SHATTER_WILL])
        self.assertNotIn(MIND_SNARE, warlock_actions)
        self.assertEqual(17, warlock_actions[NEEDS_OF_THE_ONE])
        self.assertEqual(0.0, assassin.final_mana)

    def test_complete_matchup_uses_triggers_and_complete_sheet_attack_metrics(self) -> None:
        config = wonderbane_sundancer_vs_deflock(
            starting_distance=15.0,
            max_ticks=500,
            seed=14,
            assassin_starts_stealthed=True,
        )

        result = run_verified_duel(config).duel

        assassin, warlock = result.combatants
        actions = {item.action_key.split("@")[0] for item in assassin.actions}
        triggers = {item.trigger_key for item in assassin.triggers}
        self.assertIn(BACKSTAB, actions)
        self.assertTrue(any(action.startswith("shadowbane.stance.") for action in actions))
        self.assertIn("backstab_armed", triggers)
        self.assertGreater(assassin.attacks_attempted, 0)
        self.assertGreater(warlock.attacks_attempted, 0)
        self.assertEqual(
            assassin.attacks_attempted,
            assassin.weapon_hits + assassin.weapon_misses,
        )
        self.assertEqual(0, assassin.rejected_actions)
        self.assertEqual(0, warlock.rejected_actions)

    def test_matrix_crosses_distance_and_opener_with_reproducible_batches(self) -> None:
        first = wonderbane_sundancer_deflock_matrix(
            starting_distances=(6.0, 40.0),
            assassin_stealth_openers=(False, True),
            episodes=2,
            max_ticks=30,
            seed_start=9,
        )
        second = wonderbane_sundancer_deflock_matrix(
            starting_distances=(6.0, 40.0),
            assassin_stealth_openers=(False, True),
            episodes=2,
            max_ticks=30,
            seed_start=9,
        )

        self.assertEqual(first, second)
        self.assertEqual(4, len(first))
        self.assertEqual({False, True}, {cell.assassin_starts_stealthed for cell in first})
        self.assertTrue(all(cell.batch.episodes == 2 for cell in first))

    def test_guide_duel_cli_emits_bundled_matrix_without_profile_files(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(
                (
                    "--scenario",
                    "wonderbane-guide-duel",
                    "--matrix",
                    "--distances",
                    "6,15",
                    "--episodes",
                    "2",
                    "--max-ticks",
                    "20",
                    "--assassin-stealthed",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual(2, len(payload))
        self.assertTrue(all(cell["assassin_starts_stealthed"] for cell in payload))
        self.assertTrue(all(cell["batch"]["episodes"] == 2 for cell in payload))


if __name__ == "__main__":
    unittest.main()
