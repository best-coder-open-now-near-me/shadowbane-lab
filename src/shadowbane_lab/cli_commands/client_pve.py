"""Pve client command implementations."""

from __future__ import annotations

import json
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path

from shadowbane_lab.client_input import (
    ActionInputMapping,
    ArcaneClientPower,
    ArcaneHotbarLoadError,
    CalibrationLoadError,
    ClientInputAdapter,
    DecisionInputCompiler,
    ForegroundWindowGuard,
    GuardedInputExecutor,
    MouseButton,
    PyAutoGuiBackend,
    StaticBindingPointResolver,
    StopSignal,
    WindowGuardError,
    WindowsForegroundWindowInspector,
    WindowsHotkeyEmergencyStop,
    load_arcane_hotbar,
    load_calibration,
)
from shadowbane_lab.client_input.character_config import open_active_character_config
from shadowbane_lab.client_observation import (
    NativeCharacterPopulationError,
    NativeCharacterPopulationProfileLoadError,
    NativeCombatLogReader,
    NativeHealthProfileLoadError,
    NativeMessageHudError,
    NativeMessageHudProfileLoadError,
    NativePlayerPositionError,
    NativePlayerVitalsError,
    NativePositionProfileLoadError,
    NativeTargetActionError,
    NativeTargetActionProfileLoadError,
    NativeTargetHealthError,
    NativeTargetIdentityError,
    NativeTargetIdentityProfileLoadError,
    NativeTargetPositionError,
    NativeTargetPositionProfileLoadError,
    NativeVitalsProfileLoadError,
    load_bundled_native_character_population_profile,
    load_bundled_native_health_profile,
    load_bundled_native_message_hud_profile,
    load_bundled_native_position_profile,
    load_bundled_native_target_action_profile,
    load_bundled_native_target_identity_profile,
    load_bundled_native_target_position_profile,
    load_bundled_native_vitals_profile,
    load_bundled_native_zone_profile,
    load_native_character_population_profile,
    load_native_health_profile,
    load_native_message_hud_profile,
    load_native_position_profile,
    load_native_target_action_profile,
    load_native_target_identity_profile,
    load_native_target_position_profile,
    load_native_vitals_profile,
    open_windows_native_character_population_reader,
    open_windows_native_current_zone_reader,
    open_windows_native_message_hud_reader,
    open_windows_native_player_position_reader,
    open_windows_native_player_vitals_reader,
    open_windows_native_target_action_reader,
    open_windows_native_target_health_reader,
    open_windows_native_target_identity_reader,
    open_windows_native_target_position_reader,
)
from shadowbane_lab.navigation_inspector.session import (
    ObservedPositionSource,
    optional_session,
    pve_trace_sink,
)
from shadowbane_lab.pve import (
    PVE_TRACE_SCHEMA_VERSION,
    ClientPvEIntentDispatcher,
    EmptyCombatLogSource,
    PvEApproachController,
    PvECombatCalibrationError,
    PvEController,
    PvEControllerConfig,
    PvEIntent,
    PvERunner,
    PvETraceEvidenceError,
    PvETraceJournal,
    compile_pve_combat_calibration_files,
    save_pve_combat_calibration,
    save_pve_trace_evidence,
)
from shadowbane_lab.travel import (
    ClientTravelDecisionDispatcher,
    SparseNavigationMap,
    WeightedAStarPlanner,
    load_active_zone_terrain_navigation,
)

from .client_runtime import (
    _require_window_process_id,
    _wait_for_guarded_client,
)
from .common import _error


def _run_pve(
    *,
    client_profile_path: Path,
    combat_log_path: Path | None,
    hotbar_config_path: Path | None,
    native_health_profile_path: Path | None,
    native_vitals_profile_path: Path | None,
    native_position_profile_path: Path | None,
    native_target_position_profile_path: Path | None,
    native_target_action_profile_path: Path | None,
    navigation_cache_directory: Path | None,
    max_kills: int,
    max_seconds: float,
    wait_for_client_seconds: float,
    poll_ms: int,
    policy: str,
    live: bool,
    as_json: bool,
    evidence_output_path: Path | None = None,
    combat_source: str | None = None,
    native_message_hud_profile_path: Path | None = None,
    native_target_identity_profile_path: Path | None = None,
    max_encounter_seconds: float = 120.0,
    recovery_timeout_seconds: float = 30.0,
    recovery_health_fraction: float = 0.75,
    recovery_mana_fraction: float = 0.15,
    recovery_stamina_fraction: float = 0.25,
    stop_signal: StopSignal | None = None,
    client_process_id: int | None = None,
    continuous: bool = False,
    camp_radius: float = 120.0,
    retained_trace_steps: int = 2_000,
    native_character_population_profile_path: Path | None = None,
    navigation_map: SparseNavigationMap | None = None,
) -> int:
    if not live:
        return _error("PvE execution requires the explicit --live flag", as_json=as_json)
    if isinstance(max_kills, bool) or not 1 <= max_kills <= 10:
        return _error("max-kills must be in [1, 10]", as_json=as_json)
    if not isinstance(continuous, bool):
        return _error("continuous must be a boolean", as_json=as_json)
    if not 20.0 <= camp_radius <= 1_000.0:
        return _error("camp-radius must be in [20, 1000]", as_json=as_json)
    if isinstance(retained_trace_steps, bool) or not 100 <= retained_trace_steps <= 100_000:
        return _error(
            "retained-trace-steps must be in [100, 100000]",
            as_json=as_json,
        )
    if continuous and evidence_output_path is None:
        return _error(
            "continuous PvE requires --evidence-output for its durable journal",
            as_json=as_json,
        )
    if not 1.0 <= max_seconds <= 900.0:
        return _error("max-seconds must be in [1, 900]", as_json=as_json)
    if not 5.0 <= max_encounter_seconds <= 300.0:
        return _error("max-encounter-seconds must be in [5, 300]", as_json=as_json)
    if not 1.0 <= recovery_timeout_seconds <= 300.0:
        return _error("recovery-timeout-seconds must be in [1, 300]", as_json=as_json)
    for value, field_name in (
        (recovery_health_fraction, "recovery-health-fraction"),
        (recovery_mana_fraction, "recovery-mana-fraction"),
        (recovery_stamina_fraction, "recovery-stamina-fraction"),
    ):
        if not 0.0 <= value <= 1.0:
            return _error(f"{field_name} must be in [0, 1]", as_json=as_json)
    if 0.0 < recovery_health_fraction < 0.5:
        return _error(
            "recovery-health-fraction cannot be below the 0.5 safety threshold",
            as_json=as_json,
        )
    if not 0.0 <= wait_for_client_seconds <= 300.0:
        return _error("wait-for-client-seconds must be in [0, 300]", as_json=as_json)
    if isinstance(poll_ms, bool) or not 50 <= poll_ms <= 1_000:
        return _error("poll-ms must be in [50, 1000]", as_json=as_json)
    if policy not in ("basic", "proc-assassin"):
        return _error("policy must be basic or proc-assassin", as_json=as_json)
    resolved_combat_source = combat_source or ("log" if combat_log_path is not None else "hud")
    if resolved_combat_source not in ("state", "hud", "log"):
        return _error("combat-source must be state, hud, or log", as_json=as_json)
    if resolved_combat_source == "log":
        if combat_log_path is None:
            return _error("combat-source log requires --combat-log", as_json=as_json)
        if not combat_log_path.is_file():
            return _error(f"combat log does not exist: {combat_log_path}", as_json=as_json)
    journal_path = (
        evidence_output_path.with_name(f"{evidence_output_path.stem}.events.jsonl")
        if continuous and evidence_output_path is not None
        else None
    )
    terrain_navigation_payload: dict[str, object] = {
        "enabled": navigation_cache_directory is not None,
        "status": "not_configured",
    }
    try:
        client_profile = load_calibration(client_profile_path)
        if not client_profile.live_input_enabled:
            raise ValueError("client profile is not enabled for live input")
        if client_profile.movement.button is not MouseButton.RIGHT:
            raise ValueError("PvE approach movement must use right-click input")
        controller = PvEController(
            PvEControllerConfig(
                maximum_kills=max_kills,
                maximum_session_ms=round(max_seconds * 1000),
                engagement_timeout_ms=round(max_encounter_seconds * 1000),
                recovery_timeout_ms=round(recovery_timeout_seconds * 1000),
                minimum_recovery_health_fraction=recovery_health_fraction,
                minimum_recovery_mana_fraction=recovery_mana_fraction,
                minimum_recovery_stamina_fraction=recovery_stamina_fraction,
                accept_automatic_targets=policy == "proc-assassin",
                interrupt_intent=(
                    PvEIntent.CAST_SHADOW_TOUCH if policy == "proc-assassin" else None
                ),
                interrupt_mana_cost=55.0 if policy == "proc-assassin" else 0.0,
                interrupt_cooldown_ms=2_000 if policy == "proc-assassin" else 0,
                maximum_interrupts_per_target=1 if policy == "proc-assassin" else 0,
                automatic_attack_expected=policy == "proc-assassin",
                automatic_target_requires_combat_event=policy == "proc-assassin",
                require_target_identity=True,
                use_native_population=True,
                maximum_stalled_retargets=4 if policy == "proc-assassin" else 0,
                nearest_target_sample_count=1,
                target_sample_interval_ms=350,
                continuous=continuous,
                camp_radius=camp_radius if continuous else None,
            )
        )
        mapped_actions = {mapping.action_key for mapping in client_profile.actions}
        required_actions = {intent.value for intent in controller.required_intents}
        missing_actions = required_actions - mapped_actions
        if missing_actions:
            raise ValueError(
                f"client profile is missing PvE mappings: {', '.join(sorted(missing_actions))}"
            )
        if policy == "proc-assassin" and hotbar_config_path is not None:
            _verify_hotbar_power_mapping(
                client_profile.actions,
                hotbar_config_path,
                action_key=PvEIntent.CAST_SHADOW_TOUCH.value,
                power_name=ArcaneClientPower.SHADOW_TOUCH,
            )
        health_profile = (
            load_native_health_profile(native_health_profile_path)
            if native_health_profile_path is not None
            else load_bundled_native_health_profile()
        )
        message_hud_profile = None
        if resolved_combat_source == "hud":
            message_hud_profile = (
                load_native_message_hud_profile(native_message_hud_profile_path)
                if native_message_hud_profile_path is not None
                else load_bundled_native_message_hud_profile()
            )
        vitals_profile = (
            load_native_vitals_profile(native_vitals_profile_path)
            if native_vitals_profile_path is not None
            else load_bundled_native_vitals_profile()
        )
        position_profile = (
            load_native_position_profile(native_position_profile_path)
            if native_position_profile_path is not None
            else load_bundled_native_position_profile()
        )
        target_position_profile = (
            load_native_target_position_profile(native_target_position_profile_path)
            if native_target_position_profile_path is not None
            else load_bundled_native_target_position_profile()
        )
        target_action_profile = (
            load_native_target_action_profile(native_target_action_profile_path)
            if native_target_action_profile_path is not None
            else load_bundled_native_target_action_profile()
        )
        target_identity_profile = (
            load_native_target_identity_profile(native_target_identity_profile_path)
            if native_target_identity_profile_path is not None
            else load_bundled_native_target_identity_profile()
        )
        character_population_profile = (
            load_native_character_population_profile(native_character_population_profile_path)
            if native_character_population_profile_path is not None
            else load_bundled_native_character_population_profile()
        )
        zone_profile = (
            None if navigation_cache_directory is None else load_bundled_native_zone_profile()
        )
        if navigation_cache_directory is not None and not navigation_cache_directory.is_dir():
            raise ValueError(
                f"navigation cache directory does not exist: {navigation_cache_directory}"
            )
        native_profile_hashes = {
            health_profile.executable_sha256,
            vitals_profile.executable_sha256,
            position_profile.executable_sha256,
            target_position_profile.executable_sha256,
            target_action_profile.executable_sha256,
            target_identity_profile.executable_sha256,
            character_population_profile.executable_sha256,
        }
        if message_hud_profile is not None:
            native_profile_hashes.add(message_hud_profile.executable_sha256)
        if zone_profile is not None:
            native_profile_hashes.add(zone_profile.executable_sha256)
        if len(native_profile_hashes) != 1:
            raise ValueError("native PvE profiles target different client builds")
        inspector = WindowsForegroundWindowInspector()
        selection_guard = ForegroundWindowGuard(client_profile, inspector)
        if client_process_id is None:
            selected_window = _wait_for_guarded_client(
                selection_guard,
                wait_seconds=wait_for_client_seconds,
            )
            process_id = _require_window_process_id(selected_window)
        else:
            process_id = client_process_id
        guard = ForegroundWindowGuard(
            client_profile,
            inspector,
            expected_process_id=process_id,
        )
        if client_process_id is not None:
            _wait_for_guarded_client(guard, wait_seconds=wait_for_client_seconds)
        with ExitStack() as stack:
            character_session = None
            character_config_payload = None
            if policy == "proc-assassin":
                character_session = stack.enter_context(
                    open_active_character_config(
                        process_id=process_id,
                        explicit_path=hotbar_config_path,
                    )
                )
                hotbar_config_path = character_session.binding.config_path
                _verify_hotbar_power_mapping(
                    client_profile.actions,
                    hotbar_config_path,
                    action_key=PvEIntent.CAST_SHADOW_TOUCH.value,
                    power_name=ArcaneClientPower.SHADOW_TOUCH,
                )
                character_session.require_current()
                character_config_payload = character_session.binding.as_dict()
                guard = ForegroundWindowGuard(
                    client_profile,
                    inspector,
                    expected_process_id=process_id,
                    expected_process_started_at_100ns=(
                        character_session.binding.process_creation_filetime_utc
                    ),
                )
                guard.require_target()
            health_reader = stack.enter_context(
                open_windows_native_target_health_reader(
                    health_profile,
                    process_id=process_id,
                )
            )
            player_vitals_reader = stack.enter_context(
                open_windows_native_player_vitals_reader(
                    vitals_profile,
                    process_id=process_id,
                )
            )
            player_position_reader = stack.enter_context(
                open_windows_native_player_position_reader(
                    position_profile,
                    process_id=process_id,
                )
            )
            target_position_reader = stack.enter_context(
                open_windows_native_target_position_reader(
                    target_position_profile,
                    process_id=process_id,
                )
            )
            target_action_reader = stack.enter_context(
                open_windows_native_target_action_reader(
                    target_action_profile,
                    process_id=process_id,
                )
            )
            target_identity_reader = stack.enter_context(
                open_windows_native_target_identity_reader(
                    target_identity_profile,
                    process_id=process_id,
                )
            )
            population_reader = stack.enter_context(
                open_windows_native_character_population_reader(
                    character_population_profile,
                    process_id=process_id,
                )
            )
            active_navigation_map = navigation_map
            zone_reader = None
            if zone_profile is not None:
                assert navigation_cache_directory is not None
                zone_reader = stack.enter_context(
                    open_windows_native_current_zone_reader(
                        zone_profile,
                        process_id=process_id,
                    )
                )
                zone_observation = zone_reader.observe()
                terrain_origin = player_position_reader.observe()
                terrain_arguments = (
                    {}
                    if active_navigation_map is None
                    else {"navigation_map": active_navigation_map}
                )
                active_terrain = load_active_zone_terrain_navigation(
                    navigation_cache_directory,
                    zone_observation,
                    terrain_origin,
                    **terrain_arguments,
                )
                active_navigation_map = active_terrain.navigation_map
                terrain_seed = active_terrain.seed
                terrain_navigation_payload = {
                    "enabled": True,
                    "status": "seeded" if terrain_seed is not None else "no_height_layer",
                    "zone_name": zone_observation.name,
                    "zone_token": zone_observation.zone_token,
                }
                if terrain_seed is not None:
                    terrain_navigation_payload["seed"] = {
                        "zone_depth": terrain_seed.zone_depth,
                        "template_group_id": terrain_seed.template_group_id,
                        "template_id": terrain_seed.template_id,
                        "terrain_group_id": terrain_seed.terrain_group_id,
                        "terrain_map_id": terrain_seed.terrain_map_id,
                        "raster_width": terrain_seed.raster_width,
                        "raster_height": terrain_seed.raster_height,
                        "window_center_lt": terrain_seed.window_center_lt,
                        "window_center_lg": terrain_seed.window_center_lg,
                        "window_radius": terrain_seed.window_radius,
                        "sampled_cells": terrain_seed.sampled_cells,
                        "blocked_cells": len(terrain_seed.blocked_cells),
                        "water_cells": len(terrain_seed.water_cells),
                        "object_density_cells": len(terrain_seed.object_density_cells),
                        "object_density_layers": [
                            {
                                "layer_index": layer.layer_index,
                                "terrain_group_id": layer.terrain_group_id,
                                "terrain_map_id": layer.terrain_map_id,
                                "object_count": layer.object_count,
                                "population_capacity": layer.population_capacity,
                                "maximum_horizontal_radius": (layer.maximum_horizontal_radius),
                            }
                            for layer in terrain_seed.object_density_layers
                        ],
                        "water_sample_threshold": terrain_seed.water_sample_threshold,
                        "weighted_cells": len(terrain_seed.costs),
                    }
            if resolved_combat_source == "state":
                combat_reader = EmptyCombatLogSource()
            elif message_hud_profile is None:
                assert combat_log_path is not None
                combat_reader = NativeCombatLogReader(combat_log_path, start_at_end=True)
            else:
                combat_reader = stack.enter_context(
                    open_windows_native_message_hud_reader(
                        message_hud_profile,
                        process_id=process_id,
                        start_at_end=True,
                    )
                )
                combat_reader.attach()
            active_stop_signal = stop_signal
            if active_stop_signal is None:
                active_stop_signal = stack.enter_context(WindowsHotkeyEmergencyStop())
            reader_process_ids = {
                health_reader.process_id,
                player_vitals_reader.process_id,
                player_position_reader.process_id,
                target_position_reader.process_id,
                target_action_reader.process_id,
                target_identity_reader.process_id,
                population_reader.process_id,
            }
            if message_hud_profile is not None:
                reader_process_ids.add(combat_reader.process_id)
            if zone_reader is not None:
                reader_process_ids.add(zone_reader.process_id)
            if len(reader_process_ids) != 1:
                raise ValueError("native PvE readers resolved different client processes")
            executor = GuardedInputExecutor(
                guard=guard,
                backend=PyAutoGuiBackend(),
                stop_signal=active_stop_signal,
                input_precondition=(
                    None if character_session is None else character_session.require_current
                ),
            )
            adapter = ClientInputAdapter(
                DecisionInputCompiler(client_profile, StaticBindingPointResolver()),
                executor,
            )
            journal = (
                None
                if journal_path is None
                else stack.enter_context(
                    PvETraceJournal(
                        journal_path,
                        {
                            "run_mode": "continuous",
                            "policy": policy,
                            "process_id": process_id,
                            "executable_sha256": health_profile.executable_sha256,
                            "camp_radius": camp_radius,
                            "poll_ms": poll_ms,
                            "terrain_navigation": terrain_navigation_payload,
                            "character_config": character_config_payload,
                        },
                    )
                )
            )
            navigation_observer = stack.enter_context(
                optional_session(
                    player_position_reader.process_id, position_profile.executable_sha256
                )
            )
            inspected_position_reader = player_position_reader
            if navigation_observer is not None:
                inspected_position_reader = ObservedPositionSource(
                    player_position_reader,
                    navigation_observer,
                    zone_reader=zone_reader,
                    map_zone=None if zone_reader is None else zone_observation.zone_token,
                    provenance="sparse navigation cells; raster discontinuities; "
                    "learned blockers; "
                    "costs combine slope, water and uncertain object density",
                )
            result = PvERunner(
                controller=controller,
                health_reader=health_reader,
                player_vitals_reader=player_vitals_reader,
                player_position_reader=inspected_position_reader,
                target_position_reader=target_position_reader,
                target_action_reader=target_action_reader,
                player_action_reader=target_action_reader,
                target_identity_reader=target_identity_reader,
                population_reader=population_reader,
                combat_log_reader=combat_reader,
                dispatcher=ClientPvEIntentDispatcher(adapter),
                approach_controller=PvEApproachController(
                    navigation_map=active_navigation_map,
                    planner=WeightedAStarPlanner(observer=navigation_observer),
                ),
                movement_dispatcher=ClientTravelDecisionDispatcher(adapter),
                stop_signal=active_stop_signal,
                poll_interval_ms=poll_ms,
                maximum_retained_trace_steps=(retained_trace_steps if continuous else None),
                trace_sink=pve_trace_sink(journal, navigation_observer),
            ).run()
            if journal is not None:
                journal.finish(
                    {
                        "final_phase": result.final_phase.value,
                        "terminal_reason": result.terminal_reason,
                        "kills": result.kills,
                        "total_steps": getattr(result, "total_steps", len(result.trace)),
                    }
                )
    except (
        CalibrationLoadError,
        ArcaneHotbarLoadError,
        NativeHealthProfileLoadError,
        NativeCharacterPopulationError,
        NativeCharacterPopulationProfileLoadError,
        NativeMessageHudError,
        NativeMessageHudProfileLoadError,
        NativePlayerVitalsError,
        NativePlayerPositionError,
        NativePositionProfileLoadError,
        NativeTargetHealthError,
        NativeTargetActionError,
        NativeTargetActionProfileLoadError,
        NativeTargetIdentityError,
        NativeTargetIdentityProfileLoadError,
        NativeTargetPositionError,
        NativeTargetPositionProfileLoadError,
        NativeVitalsProfileLoadError,
        OSError,
        RuntimeError,
        UnicodeError,
        ValueError,
        WindowGuardError,
    ) as exc:
        return _error(f"PvE run failed: {exc}", as_json=as_json)

    dispatched = [
        {
            "decision_id": step.decision.decision_id,
            "at_ms": step.decision.now_ms,
            "intent": step.decision.intent.value,
            "accepted": step.input_accepted,
            "reason": step.input_reason,
        }
        for step in result.trace
        if step.decision.intent is not None
    ]
    total_steps = getattr(result, "total_steps", len(result.trace))
    trace_truncated = getattr(result, "trace_truncated", total_steps > len(result.trace))
    camp = controller.camp
    successful = result.final_phase.value == "complete" or (
        continuous and result.terminal_reason == "emergency_stop"
    )
    payload = {
        "trace_schema_version": PVE_TRACE_SCHEMA_VERSION,
        "ok": successful,
        "final_phase": result.final_phase.value,
        "terminal_reason": result.terminal_reason,
        "run_mode": "continuous" if continuous else "bounded",
        "policy": policy,
        "kills": result.kills,
        "steps": len(result.trace),
        "total_steps": total_steps,
        "trace_truncated": trace_truncated,
        "journal_path": None if journal_path is None else str(journal_path),
        "camp_lease": (
            None
            if camp is None
            else {
                "anchor_lt": camp.anchor_lt,
                "anchor_lg": camp.anchor_lg,
                "radius": camp.radius,
                "return_radius": camp.return_radius,
                "return_trigger_radius": camp.return_trigger_radius,
            }
        ),
        "farm_limits": (
            None
            if continuous
            else {
                "maximum_kills": max_kills,
                "maximum_session_seconds": max_seconds,
                "maximum_encounter_seconds": max_encounter_seconds,
                "recovery_timeout_seconds": recovery_timeout_seconds,
                "recovery_health_fraction": recovery_health_fraction,
                "recovery_mana_fraction": recovery_mana_fraction,
                "recovery_stamina_fraction": recovery_stamina_fraction,
            }
        ),
        "continuous_policy": (
            None
            if not continuous
            else {
                "camp_radius": camp_radius,
                "retained_trace_steps": retained_trace_steps,
                "encounter_timeout_seconds": max_encounter_seconds,
                "failed_targets_expire": True,
            }
        ),
        "dispatched": dispatched,
        "native_observation": {
            "process_id": process_id,
            "executable_sha256": health_profile.executable_sha256,
            "target_health_profile_id": health_profile.profile_id,
            "character_population_profile_id": character_population_profile.profile_id,
            "player_vitals_profile_id": vitals_profile.profile_id,
            "player_position_profile_id": position_profile.profile_id,
            "target_position_profile_id": target_position_profile.profile_id,
            "target_action_profile_id": target_action_profile.profile_id,
            "target_identity_profile_id": target_identity_profile.profile_id,
            "combat_source": resolved_combat_source,
            "message_hud_profile_id": (
                None if message_hud_profile is None else message_hud_profile.profile_id
            ),
        },
        "terrain_navigation": terrain_navigation_payload,
        "character_config": character_config_payload,
        "trace": [step.as_dict() for step in result.trace],
    }
    if evidence_output_path is not None:
        try:
            save_pve_trace_evidence(evidence_output_path, payload)
        except PvETraceEvidenceError as exc:
            return _error(f"PvE evidence save failed: {exc}", as_json=as_json)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"PvE phase: {result.final_phase.value}")
        print(f"Reason: {result.terminal_reason}")
        print(f"Kills: {result.kills}")
        print(f"Guarded inputs: {len(dispatched)}")
    return 0 if payload["ok"] else 2


def _calibrate_pve(
    evidence_paths: Sequence[Path],
    output_path: Path,
    *,
    as_json: bool,
) -> int:
    if any(path.absolute() == output_path.absolute() for path in evidence_paths):
        return _error(
            "PvE calibration output cannot overwrite an input evidence artifact",
            as_json=as_json,
        )
    try:
        calibration = compile_pve_combat_calibration_files(evidence_paths)
        save_pve_combat_calibration(output_path, calibration)
    except (OSError, PvECombatCalibrationError, ValueError) as exc:
        return _error(f"PvE calibration failed: {exc}", as_json=as_json)
    payload = calibration.as_dict()
    payload["output_path"] = str(output_path)
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            f"Compiled {len(calibration.source_trace_sha256s)} PvE traces into "
            f"{calibration.profile_id}."
        )
        print(f"Calibration: {output_path}")
    return 0


def _verify_hotbar_power_mapping(
    mappings: Sequence[ActionInputMapping],
    hotbar_config_path: Path | None,
    *,
    action_key: str,
    power_name: ArcaneClientPower,
) -> None:
    if hotbar_config_path is None:
        raise ValueError("proc-assassin policy requires --hotbar-config")
    hotbar = load_arcane_hotbar(hotbar_config_path)
    slots = hotbar.current_slots_for_power(power_name)
    if len(slots) != 1:
        raise ValueError(
            f"active hotbar must contain exactly one {power_name} slot; found {len(slots)}"
        )
    mapping = next(item for item in mappings if item.action_key == action_key)
    expected = slots[0].activation
    if mapping.activation != expected:
        raise ValueError(
            f"client profile maps {action_key} to {mapping.activation}, "
            f"but active hotbar maps {power_name} to {expected}"
        )
