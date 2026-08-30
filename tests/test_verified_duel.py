import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from shadowbane_lab.combat import (
    CombatStance,
    CompatibilityStatus,
    StanceModifiers,
    StanceProfile,
)
from shadowbane_lab.combat.compiler import (
    CombatCompilePolicy,
    CombatReadinessError,
    compile_combatant,
)
from shadowbane_lab.combat.loader import (
    CombatProfileLoadError,
    combat_profile_dict,
    encode_combat_profile,
    load_combat_profile_text,
)
from shadowbane_lab.rollouts import (
    VerifiedCombatantConfig,
    VerifiedDuelConfig,
    run_verified_duel,
    run_verified_duel_batch,
)
from shadowbane_lab.rollouts.__main__ import main
from shadowbane_lab.rulesets import CharacterBuild, load_shadowbane_vertical_slice
from tests.test_combat_compiler import _build, _sheet

MIND_STRIKE = "shadowbane.warlock.mind_strike"
PSYCHIC_HEALING = "shadowbane.warlock.psychic_healing"


def _profile_payload(sheet, build: CharacterBuild) -> dict[str, object]:
    return combat_profile_dict(sheet, build)


def _warlock_profile():
    sheet = replace(
        _sheet(),
        sheet_id="human-warlock-59",
        profession="warlock",
        strength=70,
        dexterity=130,
        intelligence=180,
        spirit=150,
        maximum_health=1_000.0,
        maximum_mana=1_400.0,
        power_focus_values=((MIND_STRIKE, 120.0), (PSYCHIC_HEALING, 120.0)),
    )
    build = CharacterBuild(
        profession="warlock",
        level=59,
        skill_ranks=(("warlockry", 200),),
        power_ranks=((MIND_STRIKE, 40), (PSYCHIC_HEALING, 40)),
        enabled_power_keys=(MIND_STRIKE, PSYCHIC_HEALING),
    )
    return sheet, build


class CombatProfileLoaderTests(unittest.TestCase):
    def test_bundled_example_parses_but_stays_unverified(self) -> None:
        path = Path("configs/combat/complete-sheet-v1.example.json")
        sheet, build = load_combat_profile_text(path.read_text(encoding="utf-8"))

        self.assertIs(CompatibilityStatus.UNVERIFIED, sheet.compatibility)
        with self.assertRaises(CombatReadinessError):
            compile_combatant(sheet, build, load_shadowbane_vertical_slice())

    def test_complete_profile_round_trips_through_strict_json_boundary(self) -> None:
        sheet, build = _sheet(), _build()

        loaded_sheet, loaded_build = load_combat_profile_text(encode_combat_profile(sheet, build))

        self.assertEqual(sheet, loaded_sheet)
        self.assertEqual(build, loaded_build)

    def test_optional_off_hand_weapon_round_trips_without_breaking_v1_profiles(self) -> None:
        main_hand = replace(_sheet().weapon, dual_wielding=True)
        assert main_hand is not None
        sheet = replace(
            _sheet(),
            weapon=main_hand,
            off_hand_weapon=replace(main_hand, weapon_key="off-hand"),
        )

        loaded_sheet, loaded_build = load_combat_profile_text(
            encode_combat_profile(sheet, _build())
        )

        self.assertEqual(sheet, loaded_sheet)
        self.assertEqual(_build(), loaded_build)

    def test_source_pinned_stance_profiles_round_trip_through_strict_boundary(self) -> None:
        sheet = replace(
            _sheet(),
            stance_profiles=(
                StanceProfile(
                    profile_key="rogue_assassin",
                    stance=CombatStance.DEFENSIVE,
                    rank=20,
                    source_id="morloch-stances",
                    source_revision="fixture-1",
                    modifiers=StanceModifiers(
                        attack_percent=-0.11,
                        defense_percent=0.17,
                        damage_dealt_percent=-0.07,
                        stamina_recovery_percent=0.24,
                    ),
                ),
            ),
        )

        loaded_sheet, loaded_build = load_combat_profile_text(
            encode_combat_profile(sheet, _build())
        )

        self.assertEqual(sheet, loaded_sheet)
        self.assertEqual(_build(), loaded_build)

    def test_unknown_profile_field_is_rejected(self) -> None:
        payload = _profile_payload(_sheet(), _build())
        payload["sheet"]["guessed_damage"] = 9000  # type: ignore[index]

        with self.assertRaisesRegex(CombatProfileLoadError, "unsupported fields"):
            load_combat_profile_text(json.dumps(payload))

    def test_unknown_resistance_channel_is_rejected_at_profile_boundary(self) -> None:
        payload = _profile_payload(_sheet(), _build())
        payload["sheet"]["resistances"]["physical"] = 0  # type: ignore[index]

        with self.assertRaisesRegex(CombatProfileLoadError, "unknown resistance type"):
            load_combat_profile_text(json.dumps(payload))


class VerifiedDuelTests(unittest.TestCase):
    def test_bundled_level_75_source_scenario_profiles_compile_and_run(self) -> None:
        assassin_sheet, assassin_build = load_combat_profile_text(
            Path("configs/combat/irekei-proc-assassin-75.source.json").read_text(encoding="utf-8")
        )
        warlock_sheet, warlock_build = load_combat_profile_text(
            Path("configs/combat/nephilim-resist-warlock-75.source.json").read_text(
                encoding="utf-8"
            )
        )
        policy = CombatCompilePolicy(
            accepted_compatibility=(CompatibilityStatus.SOURCE_REVISION_ACCEPTED,),
            allow_ruleset_overrides=True,
        )
        config = VerifiedDuelConfig(
            left=VerifiedCombatantConfig("assassin", "assassin", assassin_sheet, assassin_build),
            right=VerifiedCombatantConfig("warlock", "warlock", warlock_sheet, warlock_build),
            compile_policy=policy,
            max_ticks=1_000,
            seed=3,
        )

        result = run_verified_duel_batch(config, episodes=3)
        single = run_verified_duel(config).duel

        self.assertEqual(3, result.episodes)
        self.assertEqual(
            3,
            result.draws + sum(item.wins for item in result.combatants),
        )
        self.assertEqual(
            0,
            sum(item.total_rejected_actions for item in result.combatants),
        )
        actions = {
            action.action_key for combatant in single.combatants for action in combatant.actions
        }
        self.assertIn(
            "shadowbane.assassin.steal_breath@irekei-proc-assassin-75-source-v1",
            actions,
        )
        self.assertIn(
            "shadowbane.warlock.psychic_shield@nephilim-resist-warlock-75-source-v1",
            actions,
        )

    def test_complete_sheet_duel_is_reproducible_and_carries_acceptance_metadata(self) -> None:
        assassin_sheet, assassin_build = _sheet(), _build()
        warlock_sheet, warlock_build = _warlock_profile()
        config = VerifiedDuelConfig(
            left=VerifiedCombatantConfig("assassin", "assassin", assassin_sheet, assassin_build),
            right=VerifiedCombatantConfig("warlock", "warlock", warlock_sheet, warlock_build),
            compile_policy=CombatCompilePolicy(
                accepted_compatibility=(CompatibilityStatus.SOURCE_REVISION_ACCEPTED,),
                allow_ruleset_overrides=True,
            ),
            max_ticks=1_000,
            seed=17,
        )

        first = run_verified_duel(config)
        second = run_verified_duel(config)

        self.assertEqual(first, second)
        self.assertGreater(first.duel.total_events, 0)
        self.assertEqual("complete_combat_sheet", first.as_dict()["mode"])
        self.assertTrue(first.ruleset_overrides_accepted)
        self.assertEqual(2, len(first.sheet_acceptance))
        self.assertIn(first.duel.winner_entity_id, {"assassin", "warlock", None})

    def test_batch_streams_contiguous_seeds_into_reproducible_aggregates(self) -> None:
        assassin_sheet, assassin_build = _sheet(), _build()
        warlock_sheet, warlock_build = _warlock_profile()
        config = VerifiedDuelConfig(
            left=VerifiedCombatantConfig("assassin", "assassin", assassin_sheet, assassin_build),
            right=VerifiedCombatantConfig("warlock", "warlock", warlock_sheet, warlock_build),
            compile_policy=CombatCompilePolicy(
                accepted_compatibility=(CompatibilityStatus.SOURCE_REVISION_ACCEPTED,),
                allow_ruleset_overrides=True,
            ),
            max_ticks=1_000,
            seed=17,
        )

        first = run_verified_duel_batch(config, episodes=12)
        second = run_verified_duel_batch(config, episodes=12)

        self.assertEqual(first, second)
        self.assertEqual(12, first.episodes)
        self.assertEqual(
            12,
            first.draws + sum(item.wins for item in first.combatants),
        )
        self.assertEqual(0, sum(item.total_rejected_actions for item in first.combatants))
        self.assertEqual("complete_combat_sheet_batch", first.as_dict()["mode"])

    def test_verified_duel_cli_loads_profiles_and_emits_batch_json(self) -> None:
        assassin_sheet, assassin_build = _sheet(), _build()
        warlock_sheet, warlock_build = _warlock_profile()
        with TemporaryDirectory() as directory:
            left = Path(directory) / "assassin.json"
            right = Path(directory) / "warlock.json"
            left.write_text(
                json.dumps(_profile_payload(assassin_sheet, assassin_build)),
                encoding="utf-8",
            )
            right.write_text(
                json.dumps(_profile_payload(warlock_sheet, warlock_build)),
                encoding="utf-8",
            )
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(
                    (
                        "--scenario",
                        "verified-duel",
                        "--left-profile",
                        str(left),
                        "--right-profile",
                        str(right),
                        "--episodes",
                        "3",
                        "--seed",
                        "11",
                        "--accept-source-revision",
                        "--accept-ruleset-overrides",
                        "--json",
                    )
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("complete_combat_sheet_batch", payload["mode"])
        self.assertEqual(3, payload["episodes"])
        self.assertEqual(11, payload["seed_start"])

    def test_same_sheet_id_is_rejected_before_catalog_key_collision(self) -> None:
        warlock_sheet, warlock_build = _warlock_profile()
        warlock_sheet = replace(warlock_sheet, sheet_id=_sheet().sheet_id)

        with self.assertRaisesRegex(ValueError, "distinct sheet ids"):
            VerifiedDuelConfig(
                left=VerifiedCombatantConfig("assassin", "a", _sheet(), _build()),
                right=VerifiedCombatantConfig("warlock", "b", warlock_sheet, warlock_build),
            )


if __name__ == "__main__":
    unittest.main()
