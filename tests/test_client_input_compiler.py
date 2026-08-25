import json
import unittest
from dataclasses import replace

from shadowbane_lab.client_input import (
    AbsolutePoint,
    CalibrationLoadError,
    ClickCommand,
    DecisionInputCompiler,
    DragCommand,
    InputCompilationError,
    KeyPressCommand,
    NormalizedPoint,
    StaticBindingPointResolver,
    WaitCommand,
    WindowBounds,
    load_calibration_text,
)
from shadowbane_lab.protocol import ActionBinding, TargetKind, Vector2
from tests.fixtures import protocol_exchange


def _calibration_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "profile_id": "wonderbane-local-windowed",
        "target": {
            "executable_names": ["Shadowbane.exe"],
            "title_pattern": ".*WonderBane.*",
            "reference_width": 1280,
            "reference_height": 720,
            "dpi_scale": 1.0,
            "size_tolerance_px": 4,
            "dpi_tolerance": 0.05,
        },
        "actions": [
            {
                "action_key": "shadowbane.assassin.shadow_bolt",
                "activation": {"type": "key", "key": "3"},
                "target_order": "before_activation",
                "post_activation_delay_ms": 125,
            },
            {
                "action_key": "shadowbane.assassin.self_heal",
                "activation": {"type": "key", "key": "4"},
                "target_order": "none",
                "post_activation_delay_ms": 0,
            },
            {
                "action_key": "shadowbane.assassin.levitation",
                "activation": {
                    "type": "click",
                    "point": {"x": 0.75, "y": 0.92},
                    "button": "left",
                },
                "target_order": "none",
                "post_activation_delay_ms": 0,
            },
        ],
        "movement": {
            "action_key": "shadowbane.move",
            "center": {"x": 0.5, "y": 0.5},
            "horizontal_radius": 0.25,
            "vertical_radius": 0.2,
            "button": "left",
        },
        "camera": {
            "anchor": {"x": 0.5, "y": 0.5},
            "maximum_horizontal_delta": 0.2,
            "maximum_vertical_delta": 0.15,
            "duration_ms": 1000,
            "button": "left",
        },
    }


def _load_profile():
    return load_calibration_text(json.dumps(_calibration_data()))


class CalibrationTests(unittest.TestCase):
    def test_loads_strict_versioned_profile(self) -> None:
        profile = _load_profile()

        self.assertEqual("wonderbane-local-windowed", profile.profile_id)
        self.assertEqual(("Shadowbane.exe",), profile.target.executable_names)
        self.assertEqual(3, len(profile.actions))

    def test_missing_required_field_fails_closed(self) -> None:
        data = _calibration_data()
        del data["camera"]

        with self.assertRaisesRegex(CalibrationLoadError, "missing required field: camera"):
            load_calibration_text(json.dumps(data))

    def test_out_of_bounds_camera_calibration_fails_closed(self) -> None:
        data = _calibration_data()
        camera = data["camera"]
        assert isinstance(camera, dict)
        camera["maximum_horizontal_delta"] = 0.75

        with self.assertRaisesRegex(CalibrationLoadError, "camera drag range"):
            load_calibration_text(json.dumps(data))


class DecisionInputCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.decision = protocol_exchange()[2]
        self.compiler = DecisionInputCompiler(
            _load_profile(),
            StaticBindingPointResolver({"enemy-7": NormalizedPoint(0.62, 0.43)}),
        )

    def test_targeted_decision_maps_to_target_activation_and_wait(self) -> None:
        plan = self.compiler.compile(self.decision)

        self.assertEqual(self.decision.correlation_id, plan.correlation_id)
        self.assertEqual(
            (
                ClickCommand(NormalizedPoint(0.62, 0.43)),
                KeyPressCommand("3"),
                WaitCommand(125),
            ),
            plan.commands,
        )

    def test_self_decision_maps_directly_to_activation(self) -> None:
        decision = replace(
            self.decision,
            action_key="shadowbane.assassin.self_heal",
            binding=ActionBinding(
                actor_id=self.decision.agent_id,
                target_kind=TargetKind.SELF,
            ),
        )

        plan = self.compiler.compile(decision)

        self.assertEqual((KeyPressCommand("4"),), plan.commands)

    def test_movement_direction_maps_to_directional_click(self) -> None:
        decision = replace(
            self.decision,
            action_key="shadowbane.move",
            binding=ActionBinding(
                actor_id=self.decision.agent_id,
                target_kind=TargetKind.DIRECTION,
                direction=Vector2(3.0, 4.0),
            ),
        )

        plan = self.compiler.compile(decision)

        self.assertEqual((ClickCommand(NormalizedPoint(0.65, 0.66)),), plan.commands)

    def test_camera_drag_maps_to_calibrated_drag(self) -> None:
        plan = self.compiler.compile_camera_drag(
            correlation_id="camera-adjustment-1",
            horizontal=0.5,
            vertical=-1.0,
        )

        self.assertEqual("client.camera.rotate", plan.action_key)
        self.assertEqual(
            (
                DragCommand(
                    start=NormalizedPoint(0.5, 0.5),
                    end=NormalizedPoint(0.6, 0.35),
                    duration_ms=1000,
                ),
            ),
            plan.commands,
        )

    def test_unknown_action_fails_closed(self) -> None:
        decision = replace(self.decision, action_key="shadowbane.unknown")

        with self.assertRaisesRegex(InputCompilationError, "no mapping"):
            self.compiler.compile(decision)

    def test_missing_resolved_target_fails_closed(self) -> None:
        compiler = DecisionInputCompiler(_load_profile(), StaticBindingPointResolver())

        with self.assertRaisesRegex(InputCompilationError, "no calibrated client point"):
            compiler.compile(self.decision)

    def test_zero_movement_direction_fails_closed(self) -> None:
        decision = replace(
            self.decision,
            action_key="shadowbane.move",
            binding=ActionBinding(
                actor_id=self.decision.agent_id,
                target_kind=TargetKind.DIRECTION,
                direction=Vector2(0.0, 0.0),
            ),
        )

        with self.assertRaisesRegex(InputCompilationError, "must not be zero"):
            self.compiler.compile(decision)


class WindowBoundsTests(unittest.TestCase):
    def test_resolves_normalized_points_inside_offset_window(self) -> None:
        bounds = WindowBounds(left=100, top=50, width=1280, height=720)

        point = bounds.resolve(NormalizedPoint(0.5, 0.5))

        self.assertEqual(AbsolutePoint(740, 410), point)
        self.assertTrue(bounds.contains(point))
        self.assertFalse(bounds.contains(AbsolutePoint(1380, 770)))


if __name__ == "__main__":
    unittest.main()
