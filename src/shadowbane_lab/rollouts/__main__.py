"""Command-line entry point for progression-bracket duel rollouts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from shadowbane_lab.combat import CompatibilityStatus
from shadowbane_lab.combat.compiler import CombatCompilePolicy
from shadowbane_lab.combat.loader import load_combat_profile
from shadowbane_lab.progression import (
    irekei_proc_assassin_roadmap,
    load_wonderbane_irekei_proc_profile,
)
from shadowbane_lab.pve import load_pve_combat_calibration
from shadowbane_lab.rollouts import (
    SmartCampResult,
    VerifiedCombatantConfig,
    VerifiedDuelConfig,
    apply_pve_combat_calibration,
    frost_walker_observed_config,
    irekei_proc_assassin_smart_camp_config,
    matched_progression_duels,
    progression_duel_matrix,
    run_nearby_mob_simulation,
    run_pure_pve_batch,
    run_smart_camp,
    run_smart_camp_batch,
    run_verified_duel,
    run_verified_duel_batch,
    wonderbane_deflock_vs_druid,
    wonderbane_druid_matchup_matrix,
    wonderbane_sundancer_deflock_matrix,
    wonderbane_sundancer_vs_deflock,
    wonderbane_sundancer_vs_druid,
)


def _integers(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc
    if not result:
        raise argparse.ArgumentTypeError("expected at least one integer")
    return result


def _numbers(value: str) -> tuple[float, ...]:
    try:
        result = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated numbers") from exc
    if not result:
        raise argparse.ArgumentTypeError("expected at least one number")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m shadowbane_lab.rollouts")
    parser.add_argument(
        "--scenario",
        choices=(
            "duels",
            "verified-duel",
            "wonderbane-guide-duel",
            "wonderbane-druid-duels",
            "frost-walker",
            "pure-frost-walker",
            "irekei-proc",
            "smart-camp",
        ),
        default="duels",
    )
    parser.add_argument("--level", type=int, default=59)
    parser.add_argument("--levels", type=_integers, default=(10, 15, 18, 22, 26, 40))
    parser.add_argument("--ranks", type=_integers, default=(0, 20, 40))
    parser.add_argument("--distance", type=float, default=15.0)
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--distances", type=_numbers, default=(15.0, 60.0, 110.0))
    parser.add_argument("--seeds", type=_integers)
    parser.add_argument("--max-ticks", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--episodes", type=int, default=1_000)
    parser.add_argument(
        "--pve-calibration",
        type=Path,
        help="live PvE calibration artifact applied to the smart-camp scenario",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--left-profile", type=Path)
    parser.add_argument("--right-profile", type=Path)
    parser.add_argument("--accept-source-revision", action="store_true")
    parser.add_argument("--accept-ruleset-overrides", action="store_true")
    parser.add_argument("--assassin-stealthed", action="store_true")
    parser.add_argument(
        "--druid-opponent",
        choices=("assassin", "warlock"),
        default="assassin",
    )
    arguments = parser.parse_args(argv)
    if arguments.pve_calibration is not None and arguments.scenario != "smart-camp":
        parser.error("--pve-calibration is supported only by --scenario smart-camp")
    if arguments.matrix and arguments.scenario not in (
        "duels",
        "wonderbane-guide-duel",
        "wonderbane-druid-duels",
    ):
        parser.error("--matrix is supported only by duel scenarios")
    if arguments.scenario == "wonderbane-druid-duels":
        if arguments.left_profile is not None or arguments.right_profile is not None:
            parser.error("wonderbane-druid-duels uses its bundled guide profiles")
        if arguments.matrix:
            cells = wonderbane_druid_matchup_matrix(
                starting_distances=arguments.distances,
                assassin_stealth_openers=(False, True),
                episodes=arguments.episodes,
                max_ticks=arguments.max_ticks,
                seed_start=arguments.seed,
            )
            if arguments.json:
                print(
                    json.dumps(
                        [cell.as_dict() for cell in cells],
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print("opponent  range  hidden  episodes  opponent-wins  D-wins  draws")
                for cell in cells:
                    wins = {item.entity_id: item.wins for item in cell.batch.combatants}
                    hidden = (
                        "n/a"
                        if cell.assassin_starts_stealthed is None
                        else str(cell.assassin_starts_stealthed)
                    )
                    print(
                        f"{cell.opponent:<8}  {cell.starting_distance:>5.1f}  "
                        f"{hidden:>6}  {cell.batch.episodes:>8}  "
                        f"{wins[cell.opponent]:>13}  {wins['druid']:>6}  "
                        f"{cell.batch.draws:>5}"
                    )
            return 0
        if arguments.druid_opponent == "assassin":
            config = wonderbane_sundancer_vs_druid(
                starting_distance=arguments.distance,
                max_ticks=arguments.max_ticks,
                seed=arguments.seed,
                assassin_starts_stealthed=arguments.assassin_stealthed,
            )
        else:
            config = wonderbane_deflock_vs_druid(
                starting_distance=arguments.distance,
                max_ticks=arguments.max_ticks,
                seed=arguments.seed,
            )
        result = (
            run_verified_duel(config)
            if arguments.episodes == 1
            else run_verified_duel_batch(
                config,
                episodes=arguments.episodes,
                seed_start=arguments.seed,
            )
        )
        if arguments.json:
            print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        elif arguments.episodes == 1:
            duel = result.duel
            print(
                f"WonderBane Druid duel: opponent={arguments.druid_opponent}; "
                f"winner={duel.winner_entity_id or 'draw'}; "
                f"reason={duel.reason.value}; ticks={duel.ticks}"
            )
            for combatant in duel.combatants:
                print(
                    f"{combatant.entity_id}: health={combatant.final_health:.1f}; "
                    f"mana={combatant.final_mana:.1f}; damage={combatant.damage_dealt:.1f}"
                )
        else:
            wins = {item.entity_id: item.wins for item in result.combatants}
            print(
                f"WonderBane Druid batch: episodes={result.episodes}; "
                f"{arguments.druid_opponent}_wins={wins[arguments.druid_opponent]}; "
                f"druid_wins={wins['druid']}; draws={result.draws}; "
                f"mean_ticks={result.mean_ticks:.1f}"
            )
        return 0
    if arguments.scenario == "wonderbane-guide-duel":
        if arguments.left_profile is not None or arguments.right_profile is not None:
            parser.error("wonderbane-guide-duel uses its bundled guide profiles")
        if arguments.matrix:
            cells = wonderbane_sundancer_deflock_matrix(
                starting_distances=arguments.distances,
                assassin_stealth_openers=(arguments.assassin_stealthed,),
                episodes=arguments.episodes,
                max_ticks=arguments.max_ticks,
                seed_start=arguments.seed,
            )
            if arguments.json:
                print(
                    json.dumps(
                        [cell.as_dict() for cell in cells],
                        indent=2,
                        sort_keys=True,
                    )
                )
            else:
                print("range  hidden  episodes  A-wins  W-wins  draws  mean_ticks")
                for cell in cells:
                    wins = {item.entity_id: item.wins for item in cell.batch.combatants}
                    print(
                        f"{cell.starting_distance:>5.1f}  "
                        f"{str(cell.assassin_starts_stealthed):>6}  "
                        f"{cell.batch.episodes:>8}  {wins['assassin']:>6}  "
                        f"{wins['warlock']:>6}  {cell.batch.draws:>5}  "
                        f"{cell.batch.mean_ticks:>10.1f}"
                    )
            return 0
        config = wonderbane_sundancer_vs_deflock(
            starting_distance=arguments.distance,
            max_ticks=arguments.max_ticks,
            seed=arguments.seed,
            assassin_starts_stealthed=arguments.assassin_stealthed,
        )
        result = (
            run_verified_duel(config)
            if arguments.episodes == 1
            else run_verified_duel_batch(
                config,
                episodes=arguments.episodes,
                seed_start=arguments.seed,
            )
        )
        if arguments.json:
            print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        elif arguments.episodes == 1:
            duel = result.duel
            print(
                f"WonderBane guide duel: winner={duel.winner_entity_id or 'draw'}; "
                f"reason={duel.reason.value}; ticks={duel.ticks}; "
                f"hidden={arguments.assassin_stealthed}"
            )
            for combatant in duel.combatants:
                print(
                    f"{combatant.entity_id}: health={combatant.final_health:.1f}; "
                    f"mana={combatant.final_mana:.1f}; damage={combatant.damage_dealt:.1f}"
                )
        else:
            wins = {item.entity_id: item.wins for item in result.combatants}
            print(
                f"WonderBane guide batch: episodes={result.episodes}; "
                f"assassin_wins={wins['assassin']}; warlock_wins={wins['warlock']}; "
                f"draws={result.draws}; mean_ticks={result.mean_ticks:.1f}"
            )
        return 0
    if arguments.scenario == "verified-duel":
        if arguments.left_profile is None or arguments.right_profile is None:
            parser.error("verified-duel requires --left-profile and --right-profile")
        left_sheet, left_build = load_combat_profile(arguments.left_profile)
        right_sheet, right_build = load_combat_profile(arguments.right_profile)
        accepted = [CompatibilityStatus.LIVE_VERIFIED]
        if arguments.accept_source_revision:
            accepted.append(CompatibilityStatus.SOURCE_REVISION_ACCEPTED)
        config = VerifiedDuelConfig(
            left=VerifiedCombatantConfig(
                "left",
                "left",
                left_sheet,
                left_build,
            ),
            right=VerifiedCombatantConfig(
                "right",
                "right",
                right_sheet,
                right_build,
            ),
            compile_policy=CombatCompilePolicy(
                accepted_compatibility=tuple(accepted),
                allow_ruleset_overrides=arguments.accept_ruleset_overrides,
            ),
            starting_distance=arguments.distance,
            max_ticks=arguments.max_ticks,
            seed=arguments.seed,
        )
        result = (
            run_verified_duel(config)
            if arguments.episodes == 1
            else run_verified_duel_batch(
                config,
                episodes=arguments.episodes,
                seed_start=arguments.seed,
            )
        )
        if arguments.json:
            print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        elif arguments.episodes != 1:
            print(
                f"complete-sheet batch: episodes={result.episodes}; "
                f"draws={result.draws}; mean_ticks={result.mean_ticks:.1f}; "
                f"formula={result.formula_revision[:12]}"
            )
            for combatant in result.combatants:
                print(
                    f"{combatant.entity_id}: wins={combatant.wins}; "
                    f"mean_health={combatant.mean_final_health:.1f}; "
                    f"mean_damage={combatant.mean_damage_dealt:.1f}"
                )
        else:
            duel = result.duel
            print(
                f"complete-sheet duel: winner={duel.winner_entity_id or 'draw'}; "
                f"reason={duel.reason.value}; ticks={duel.ticks}; "
                f"formula={result.formula_revision[:12]}"
            )
            for combatant in duel.combatants:
                print(
                    f"{combatant.entity_id}: health={combatant.final_health:.1f}; "
                    f"mana={combatant.final_mana:.1f}; damage={combatant.damage_dealt:.1f}"
                )
        return 0
    if arguments.scenario == "smart-camp":
        config = irekei_proc_assassin_smart_camp_config(
            seed=arguments.seed,
            max_ticks=arguments.max_ticks,
        )
        if arguments.pve_calibration is not None:
            config = apply_pve_combat_calibration(
                config,
                load_pve_combat_calibration(arguments.pve_calibration),
            )
        result = (
            run_smart_camp(config)
            if arguments.episodes == 1
            else run_smart_camp_batch(
                config,
                episodes=arguments.episodes,
                seed_start=arguments.seed,
            )
        )
        if arguments.json:
            payload = (
                result.as_dict(include_choices=True)
                if isinstance(result, SmartCampResult)
                else result.as_dict()
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            if isinstance(result, SmartCampResult):
                print(
                    f"{result.profile_id}: {result.reason.value}; "
                    f"kills={result.mobs_killed}/{result.mobs_total}; "
                    f"health={result.player_final_health:.1f}; "
                    f"time={result.sim_time_ms}ms"
                )
                print(f"Targets: {list(result.target_sequence)}")
            else:
                mean_time = (
                    "n/a"
                    if result.mean_clear_time_ms is None
                    else f"{result.mean_clear_time_ms:.1f}ms"
                )
                print(
                    f"{result.profile_id}: {result.camps_cleared}/{result.episodes} "
                    f"camps cleared; mean time={mean_time}; "
                    f"mean health={result.mean_remaining_health:.1f}"
                )
            print(f"Actions: {dict(result.action_counts)}")
            print(f"Procs: {[item.as_dict() for item in result.proc_outcomes]}")
        return 0

    if arguments.scenario == "irekei-proc":
        roadmap = irekei_proc_assassin_roadmap(
            load_wonderbane_irekei_proc_profile(),
            level=arguments.level,
        )
        if arguments.json:
            print(json.dumps(roadmap.as_dict(), indent=2, sort_keys=True))
        else:
            print(
                f"Irekei Rogue Assassin level {roadmap.level}: "
                f"{roadmap.training_points_now} trains now, "
                f"{roadmap.training_points_at_75 - roadmap.training_points_now} still to earn"
            )
            print(f"Disciplines now: {', '.join(roadmap.disciplines_now)}")
            print(f"Third discipline at 70: {roadmap.third_discipline_at_70}")
            for candidate in roadmap.candidates:
                print(
                    f"{candidate.name}: ATR={candidate.attack_rating:.1f}, "
                    f"base DEF={candidate.baseline_defense}, "
                    f"proc DPS={candidate.procs.expected_proc_damage_per_second:.2f}"
                )
        return 0

    if arguments.scenario == "pure-frost-walker":
        result = run_pure_pve_batch(
            frost_walker_observed_config(max_ticks=arguments.max_ticks),
            episodes=arguments.episodes,
            seed_start=arguments.seed,
        )
        if arguments.json:
            print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        else:
            mean_ttk = (
                "n/a" if result.mean_kill_time_ms is None else f"{result.mean_kill_time_ms:.1f}ms"
            )
            mean_attacks = (
                "n/a"
                if result.mean_attacks_to_kill is None
                else f"{result.mean_attacks_to_kill:.3f}"
            )
            print(
                f"{result.profile_id}: {result.kills}/{result.episodes} kills; "
                f"mean TTK={mean_ttk}; mean attacks={mean_attacks}"
            )
            print(f"Attacks-to-kill: {[item.as_dict() for item in result.attacks_to_kill]}")
            print(f"Damage rolls: {[item.as_dict() for item in result.damage_rolls]}")
        return 0

    if arguments.scenario == "frost-walker":
        result = run_nearby_mob_simulation(
            frost_walker_observed_config(
                seed=arguments.seed,
                max_ticks=arguments.max_ticks,
            )
        )
        if arguments.json:
            print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        else:
            print(
                f"{result.profile_id}: {result.terminal_reason}; "
                f"kills={result.kills}, attacks={list(result.attack_rolls)}, "
                f"time={result.sim_time_ms}ms"
            )
            print("Assumptions:")
            for assumption in result.assumptions:
                print(f"- {assumption}")
        return 0

    if arguments.matrix:
        cells = progression_duel_matrix(
            levels=arguments.levels,
            power_ranks=arguments.ranks,
            starting_distances=arguments.distances,
            seeds=arguments.seeds or (arguments.seed,),
            max_ticks=arguments.max_ticks,
        )
        if arguments.json:
            print(
                json.dumps(
                    [cell.as_dict() for cell in cells],
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        print("Focus prerequisites are assumed satisfied; each rank is an explicit bracket.")
        print("level  rank  range  A-wins  W-wins  draws  limits  mean_ticks  traces")
        for cell in cells:
            print(
                f"{cell.level:>5}  {cell.power_rank:>4}  "
                f"{cell.starting_distance:>5.1f}  {cell.assassin_wins:>6}  "
                f"{cell.warlock_wins:>6}  {cell.draws:>5}  {cell.time_limits:>6}  "
                f"{cell.mean_ticks:>10.1f}  {cell.unique_trace_count:>6}"
            )
        return 0

    results = matched_progression_duels(
        levels=arguments.levels,
        power_ranks=arguments.ranks,
        starting_distance=arguments.distance,
        max_ticks=arguments.max_ticks,
        seed=arguments.seed,
    )
    if arguments.json:
        print(
            json.dumps(
                [
                    {"level": level, "power_rank": rank, **result.as_dict()}
                    for level, rank, result in results
                ],
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    print("Focus prerequisites are assumed satisfied; power rank is an explicit bracket.")
    print("level  rank  winner     ticks  assassin_hp  warlock_hp  cancelled")
    for level, rank, result in results:
        winner = result.winner_entity_id or "draw"
        assassin, warlock = result.combatants
        print(
            f"{level:>5}  {rank:>4}  {winner:<9}  {result.ticks:>5}  "
            f"{assassin.final_health:>11.1f}  {warlock.final_health:>10.1f}  "
            f"{result.cancelled_scheduled_items:>9}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
