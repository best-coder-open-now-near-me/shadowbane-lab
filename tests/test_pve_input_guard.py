from dataclasses import replace
from types import SimpleNamespace

import pytest

from shadowbane_lab.client_input import (
    EventEmergencyStop,
    ForegroundWindowGuard,
    GuardedInputExecutor,
    InputExecutionError,
    RecordingInputBackend,
    StaticWindowInspector,
)
from shadowbane_lab.client_input.model import InputPlan, KeyPressCommand
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import NativeCharacterKind
from shadowbane_lab.pve.input_guard import NativePvEInputGuard, PvEInputGuardError
from tests.test_client_input_compiler import _load_profile
from tests.test_client_input_executor import _valid_snapshot
from tests.test_pve_tracked_consumers import ACTOR, BOUND, character, observation, tracked


@pytest.fixture
def fixture():
    state = SimpleNamespace(
        population=observation(selected="bound").population, target=tracked(), pending=False
    )

    class Reader:
        process_id = 4320

        def observe(self):
            return state.population

    reader = Reader()
    guard = NativePvEInputGuard(
        reader, target=lambda: state.target, cleanup_pending=lambda: state.pending
    )
    return state, reader, guard


@pytest.mark.parametrize(
    "change", ["selection", "absent", "reused", "dead", "protected", "actor", "process", "pending"]
)
def test_changed_binding_rejects_before_input(fixture, change):
    state, reader, guard = fixture
    if change == "selection":
        state.population = replace(state.population, selected_target_token="other")
    elif change == "absent":
        state.population = replace(state.population, characters=())
    elif change == "actor":
        state.population = replace(state.population, local_player_object_key=NativeObjectKey(10, 8))
    elif change == "process":
        reader.process_id += 1
    elif change == "pending":
        state.pending = True
    else:
        value = (
            character(object_key=NativeObjectKey(20, 8))
            if change == "reused"
            else character(
                current_health=0 if change == "dead" else 10, merchant=change == "protected"
            )
        )
        state.population = replace(state.population, characters=(value,))
    with pytest.raises(PvEInputGuardError):
        guard.require_current()


def test_current_binding_and_unbound_acquisition_are_allowed(fixture):
    state, reader, guard = fixture
    guard.require_current()
    state.target = None
    state.population = replace(state.population, selected_target_token="other")
    guard.require_current()
    assert state.population.local_player_object_key == ACTOR
    assert tracked().object_key == BOUND


def test_actor_change_during_guard_construction_is_rejected():
    class Reader:
        process_id = 1

        def observe(self):
            self.process_id = 2
            return observation().population

    with pytest.raises(PvEInputGuardError, match="process changed during"):
        NativePvEInputGuard(Reader(), target=lambda: None, cleanup_pending=lambda: False)


def test_cleanup_beginning_during_read_rejects(fixture):
    state, reader, guard = fixture

    def observe():
        state.pending = True
        return state.population

    reader.observe = observe
    with pytest.raises(PvEInputGuardError, match="engagement changed"):
        guard.require_current()


def test_rate_limit_selection_change_blocks_second_actual_command(fixture):
    state, reader, object_guard = fixture
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds
        state.population = replace(state.population, selected_target_token="other")

    backend = RecordingInputBackend()
    executor = GuardedInputExecutor(
        guard=ForegroundWindowGuard(_load_profile(), StaticWindowInspector(_valid_snapshot())),
        backend=backend,
        stop_signal=EventEmergencyStop(),
        input_precondition=object_guard.require_current,
        minimum_input_interval_ms=25,
        clock=lambda: now[0],
        sleeper=sleep,
    )
    plan = InputPlan(
        correlation_id="test",
        action_key="attack",
        commands=(KeyPressCommand("a"), KeyPressCommand("b")),
    )
    with pytest.raises(InputExecutionError, match="selected target no longer") as failure:
        executor.execute(plan)
    assert failure.value.commands_completed == 1
    assert len(backend.invocations) == 1


@pytest.mark.parametrize(
    "kind", [NativeCharacterKind.PLAYER, NativeCharacterKind.PET, NativeCharacterKind.UNKNOWN]
)
def test_non_npc_never_enters_ordinary_input(fixture, kind):
    state, _, guard = fixture
    state.population = replace(state.population, characters=(character(character_kind=kind),))
    with pytest.raises(PvEInputGuardError, match="not an NPC"):
        guard.require_current()
