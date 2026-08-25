import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from shadowbane_lab.cli import main
from shadowbane_lab.client_input import StaticWindowInspector, WindowBounds
from shadowbane_lab.client_observation import (
    ClientObservationProfile,
    ClientPixelRegion,
    ClientTargetObserver,
    ObservationDetectionError,
    PyAutoGuiFrameCapture,
    RedPixelThreshold,
    RgbFrame,
    StaticFrameCapture,
    TargetHealthBarCalibration,
    TargetHealthBarDetector,
    load_observation_calibration,
    load_observation_calibration_text,
)
from tests.test_client_input_compiler import _load_profile
from tests.test_client_input_executor import _valid_snapshot


def _observation_profile(
    *,
    client_profile_id: str = "client-1",
    maximum_stray_columns: int = 1,
) -> ClientObservationProfile:
    return ClientObservationProfile(
        profile_id="target-frame-test",
        client_profile_id=client_profile_id,
        target_health_bar=TargetHealthBarCalibration(
            region=ClientPixelRegion(left=1, top=1, width=4, height=3),
            red_threshold=RedPixelThreshold(
                minimum_red=100,
                red_to_green_ratio=1.8,
                red_to_blue_ratio=1.8,
            ),
            minimum_red_pixels_per_column=2,
            minimum_present_columns=1,
            maximum_stray_columns=maximum_stray_columns,
        ),
    )


def _frame(*, red_columns: tuple[int, ...] = (), red_rows: int = 3) -> RgbFrame:
    width = 6
    height = 5
    pixels = bytearray([24, 24, 24] * width * height)
    for local_x in red_columns:
        for local_y in range(red_rows):
            x = 1 + local_x
            y = 1 + local_y
            offset = (y * width + x) * 3
            pixels[offset : offset + 3] = bytes((150, 20, 20))
    return RgbFrame(width=width, height=height, pixels=bytes(pixels))


def _client_profile():
    profile = _load_profile()
    return replace(
        profile,
        profile_id="client-1",
        target=replace(
            profile.target,
            reference_width=6,
            reference_height=5,
            size_tolerance_px=0,
        ),
    )


class TargetHealthBarDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = TargetHealthBarDetector(
            _observation_profile(),
            expected_width=6,
            expected_height=5,
        )

    def test_empty_health_strip_reports_no_target(self) -> None:
        observation = self.detector.observe(_frame())

        self.assertFalse(observation.target_present)
        self.assertIsNone(observation.health_fraction)
        self.assertEqual(0, observation.leading_filled_columns)
        self.assertEqual(0, observation.red_pixel_count)

    def test_full_left_anchored_strip_reports_full_health(self) -> None:
        observation = self.detector.observe(_frame(red_columns=(0, 1, 2, 3)))

        self.assertTrue(observation.target_present)
        self.assertEqual(1.0, observation.health_fraction)
        self.assertEqual(4, observation.leading_filled_columns)
        self.assertEqual(12, observation.red_pixel_count)

    def test_partial_left_anchored_strip_reports_fraction(self) -> None:
        observation = self.detector.observe(_frame(red_columns=(0, 1)))

        self.assertTrue(observation.target_present)
        self.assertEqual(0.5, observation.health_fraction)
        self.assertEqual(2, observation.leading_filled_columns)
        self.assertEqual(0, observation.stray_filled_columns)

    def test_sparse_red_noise_does_not_form_filled_columns(self) -> None:
        observation = self.detector.observe(
            _frame(red_columns=(0, 1, 2, 3), red_rows=1)
        )

        self.assertFalse(observation.target_present)
        self.assertEqual(0, observation.total_filled_columns)
        self.assertEqual(4, observation.red_pixel_count)

    def test_non_contiguous_fill_fails_closed(self) -> None:
        detector = TargetHealthBarDetector(
            _observation_profile(maximum_stray_columns=0),
            expected_width=6,
            expected_height=5,
        )

        with self.assertRaisesRegex(ObservationDetectionError, "left-anchored"):
            detector.observe(_frame(red_columns=(0, 2)))

    def test_mismatched_frame_dimensions_fail_closed(self) -> None:
        frame = RgbFrame(width=1, height=1, pixels=bytes((0, 0, 0)))

        with self.assertRaisesRegex(ObservationDetectionError, "dimensions"):
            self.detector.observe(frame)


class ClientTargetObserverTests(unittest.TestCase):
    def test_guarded_observer_captures_exact_client_bounds(self) -> None:
        client_profile = _client_profile()
        snapshot = replace(
            _valid_snapshot(),
            client_bounds=WindowBounds(left=10, top=20, width=6, height=5),
        )
        inspector = StaticWindowInspector(snapshot)
        capture = StaticFrameCapture(_frame(red_columns=(0, 1, 2)))
        observer = ClientTargetObserver(
            client_profile,
            _observation_profile(),
            inspector,
            capture,
        )

        observation = observer.observe()

        self.assertEqual(0.75, observation.health_fraction)
        self.assertEqual(1, inspector.inspection_count)
        self.assertEqual([snapshot.client_bounds], capture.bounds)

    def test_observation_profile_must_pair_with_client_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not target"):
            ClientTargetObserver(
                _client_profile(),
                _observation_profile(client_profile_id="different-client"),
                StaticWindowInspector(_valid_snapshot()),
                StaticFrameCapture(_frame()),
            )


class ObservationCalibrationTests(unittest.TestCase):
    def test_bundled_wonderbane_profile_contains_measured_strip(self) -> None:
        profile = load_observation_calibration(
            Path(__file__).parents[1]
            / "configs"
            / "wonderbane-1920x955.observation.json"
        )

        self.assertEqual("wonderbane-vm-1920x955", profile.client_profile_id)
        self.assertEqual(ClientPixelRegion(340, 3, 122, 10), profile.target_health_bar.region)

    def test_invalid_json_fails_with_calibration_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            load_observation_calibration_text("{")


class FakeImage:
    mode = "RGB"
    size = (2, 1)

    def convert(self, mode: str):
        if mode != "RGB":
            raise AssertionError(mode)
        return self

    def tobytes(self) -> bytes:
        return bytes((1, 2, 3, 4, 5, 6))


class FakePyAutoGui:
    def __init__(self) -> None:
        self.regions: list[tuple[int, int, int, int]] = []

    def screenshot(self, *, region: tuple[int, int, int, int]) -> FakeImage:
        self.regions.append(region)
        return FakeImage()


class PyAutoGuiFrameCaptureTests(unittest.TestCase):
    def test_capture_returns_rgb_bytes_for_guarded_region(self) -> None:
        fake = FakePyAutoGui()
        capture = PyAutoGuiFrameCapture(fake)

        frame = capture.capture(WindowBounds(left=10, top=20, width=2, height=1))

        self.assertEqual([(10, 20, 2, 1)], fake.regions)
        self.assertEqual((2, 1), (frame.width, frame.height))
        self.assertEqual((4, 5, 6), frame.rgb_at(1, 0))


class TargetObservationCliTests(unittest.TestCase):
    def test_live_observation_command_emits_machine_readable_health(self) -> None:
        output = io.StringIO()
        client_profile = _client_profile()
        observation_profile = _observation_profile()
        snapshot = replace(
            _valid_snapshot(),
            client_bounds=WindowBounds(left=10, top=20, width=6, height=5),
        )
        with (
            patch("shadowbane_lab.cli.load_calibration", return_value=client_profile),
            patch(
                "shadowbane_lab.cli.load_observation_calibration",
                return_value=observation_profile,
            ),
            patch(
                "shadowbane_lab.cli.WindowsForegroundWindowInspector",
                return_value=StaticWindowInspector(snapshot),
            ),
            patch(
                "shadowbane_lab.cli.PyAutoGuiFrameCapture",
                return_value=StaticFrameCapture(_frame(red_columns=(0, 1, 2))),
            ),
            redirect_stdout(output),
        ):
            result = main(
                (
                    "client",
                    "observe-target",
                    "--client-profile",
                    "client.json",
                    "--observation-profile",
                    "observation.json",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["target_present"])
        self.assertEqual(0.75, payload["health_fraction"])
        self.assertEqual(3, payload["leading_filled_columns"])


if __name__ == "__main__":
    unittest.main()
