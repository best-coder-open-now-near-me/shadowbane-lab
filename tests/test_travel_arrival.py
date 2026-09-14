from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_client_input_compiler import protocol_exchange

from shadowbane_lab.client_input import DecisionInputCompiler, StaticBindingPointResolver
from shadowbane_lab.client_input.calibration import load_calibration
from shadowbane_lab.client_input.compiler import InputCompilationError
from shadowbane_lab.client_input.minimap import MinimapDestinationResolver
from shadowbane_lab.client_input.stop import EventEmergencyStop
from shadowbane_lab.client_observation import NativePlayerPositionObservation
from shadowbane_lab.client_observation.native_minimap import NativeMinimapObservation
from shadowbane_lab.protocol import ActionBinding, TargetKind, Vector2
from shadowbane_lab.travel.arrival import observe_arrival
from shadowbane_lab.travel.model import TravelDestination


class Clock:
    now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, delay):
        self.now += delay


class Positions:
    process_id = 8652

    def __init__(self, values):
        self.values = iter(values)

    def observe(self):
        return NativePlayerPositionObservation(next(self.values), 1000, 28)


def test_stationary_arrival_includes_the_deceleration_trail():
    clock = Clock()
    samples = []
    result = observe_arrival(
        Positions([1097, 1099, 1100, 1100.01, 1100, 1100.02]),
        TravelDestination(1100, 1000, 5),
        stop_signal=EventEmergencyStop(),
        observer=samples.append,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert result.confirmed and result.position.lt == 1100.02
    assert len(samples) == 6 and clock.now >= 1.0


@pytest.mark.parametrize(
    "positions",
    [
        [1100, 1110] + [1120] * 30,  # passing through the arrival radius is not arrival
        [
            1100 + i * 0.2 for i in range(30)
        ],  # cumulative drift cannot reset the envelope per sample
    ],
)
def test_continued_motion_does_not_report_arrival(positions):
    clock = Clock()
    result = observe_arrival(
        Positions(positions),
        TravelDestination(1100, 1000, 5),
        stop_signal=EventEmergencyStop(),
        clock=clock,
        sleeper=clock.sleep,
    )
    assert not result.confirmed and result.reason == "arrival_not_settled"


def test_missing_position_and_cancellation_never_report_arrival():
    clock = Clock()
    stop = EventEmergencyStop()
    result = observe_arrival(
        Positions([]),
        TravelDestination(1100, 1000, 5),
        stop_signal=stop,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert not result.confirmed and result.reason.startswith("arrival_observation_failure")
    stop.trip()
    result = observe_arrival(
        Positions([]),
        TravelDestination(1100, 1000, 5),
        stop_signal=stop,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert not result.confirmed and result.reason == "emergency_stop"


def test_optional_diagnostics_cannot_block_real_arrival():
    clock = Clock()

    def broken(_):
        raise RuntimeError("display disconnected")

    result = observe_arrival(
        Positions([1100] * 5),
        TravelDestination(1100, 1000, 5),
        stop_signal=EventEmergencyStop(),
        observer=broken,
        clock=clock,
        sleeper=clock.sleep,
    )
    assert result.confirmed


def test_world_destination_compiles_nearby_even_with_a_different_calibrated_center():
    profile = load_calibration(Path("configs/wonderbane-travel.template.json"))
    projection = NativeMinimapObservation(1713, 17, 1917, 221, 0.270260877)
    reader = SimpleNamespace(process_id=8652, observe=lambda: projection)
    # The extra native sample is fresh: the controller's original position is irrelevant.
    positions = Positions([1005])
    resolver = MinimapDestinationResolver(profile, reader, positions)
    decision = replace(
        protocol_exchange()[2],
        action_key=profile.movement.action_key,
        binding=ActionBinding(
            actor_id=protocol_exchange()[2].agent_id,
            target_kind=TargetKind.POSITION,
            position=Vector2(1045, 1000),
        ),
    )
    compiler = DecisionInputCompiler(
        profile, StaticBindingPointResolver(), movement_resolver=resolver
    )
    point = compiler.compile(decision).commands[0].point
    assert round(point.x * (profile.target.reference_width - 1)) == 1826
    assert round(point.y * (profile.target.reference_height - 1)) == 119
    with pytest.raises(InputCompilationError, match="verified live projection"):
        DecisionInputCompiler(profile, StaticBindingPointResolver()).compile(decision)


def test_mismatched_reader_or_changed_projection_rejects_click():
    profile = load_calibration(Path("configs/wonderbane-travel.template.json"))
    p = NativeMinimapObservation(1713, 17, 1917, 221, 0.27)
    with pytest.raises(ValueError, match="same client"):
        MinimapDestinationResolver(profile, SimpleNamespace(process_id=7), Positions([1000]))
    values = iter((p, replace(p, pixels_per_world_unit=0.54)))
    resolver = MinimapDestinationResolver(
        profile, SimpleNamespace(process_id=8652, observe=lambda: next(values)), Positions([1000])
    )
    decision = replace(
        protocol_exchange()[2],
        action_key=profile.movement.action_key,
        binding=ActionBinding(
            actor_id=protocol_exchange()[2].agent_id,
            target_kind=TargetKind.POSITION,
            position=Vector2(1045, 1000),
        ),
    )
    with pytest.raises(InputCompilationError, match="changed before"):
        resolver.resolve(decision)


def test_coarse_zoom_rejects_a_click_before_reading_position():
    profile = load_calibration(Path("configs/wonderbane-travel.template.json"))
    p = NativeMinimapObservation(1713, 17, 1917, 221, 0.01)
    resolver = MinimapDestinationResolver(
        profile, SimpleNamespace(process_id=8652, observe=lambda: p), Positions([])
    )
    decision = replace(
        protocol_exchange()[2],
        action_key=profile.movement.action_key,
        binding=ActionBinding(
            actor_id=protocol_exchange()[2].agent_id,
            target_kind=TargetKind.POSITION,
            position=Vector2(1045, 1000),
        ),
    )
    with pytest.raises(InputCompilationError, match="too coarse"):
        resolver.resolve(decision)
