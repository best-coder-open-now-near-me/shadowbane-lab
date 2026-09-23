import os
import unittest

from shadowbane_lab.client_input import (
    WORLD_MAP_ACTION_TEST_INPUT_TAG,
    AbsolutePoint,
    ClickInvocation,
    DragInvocation,
    MouseButton,
    WindowsTaggedPointerButtonSender,
    WorldMapTestInputBackend,
)


class FakePyAutoGui:
    FAILSAFE = False

    def __init__(self) -> None:
        self.moves: list[tuple[int, int]] = []

    def moveTo(self, x: int, y: int) -> None:
        self.moves.append((x, y))


class RecordingSender:
    def __init__(self) -> None:
        self.clicks: list[tuple[MouseButton, int]] = []

    def click(self, button: MouseButton, *, tag: int) -> None:
        self.clicks.append((button, tag))


class ScriptedUser32:
    def __init__(self, results: list[int]) -> None:
        self.results = list(results)
        self.counts: list[int] = []

    def SendInput(self, count: int, _inputs: object, _size: int) -> int:
        self.counts.append(count)
        return self.results.pop(0)


class WorldMapTestInputBackendTests(unittest.TestCase):
    def test_moves_with_failsafe_then_emits_one_tagged_right_click(self) -> None:
        pyautogui = FakePyAutoGui()
        sender = RecordingSender()
        backend = WorldMapTestInputBackend(pyautogui, sender)

        backend.click(
            ClickInvocation(
                point=AbsolutePoint(500, 300),
                button=MouseButton.RIGHT,
            )
        )

        self.assertTrue(pyautogui.FAILSAFE)
        self.assertEqual([(500, 300)], pyautogui.moves)
        self.assertEqual(
            [(MouseButton.RIGHT, WORLD_MAP_ACTION_TEST_INPUT_TAG)],
            sender.clicks,
        )

    def test_rejects_any_input_outside_the_single_click_contract(self) -> None:
        backend = WorldMapTestInputBackend(FakePyAutoGui(), RecordingSender())

        with self.assertRaisesRegex(ValueError, "one right click"):
            backend.click(
                ClickInvocation(
                    point=AbsolutePoint(500, 300),
                    button=MouseButton.LEFT,
                )
            )
        with self.assertRaisesRegex(RuntimeError, "cannot dispatch drags"):
            backend.drag(
                DragInvocation(
                    start=AbsolutePoint(1, 1),
                    end=AbsolutePoint(2, 2),
                    duration_ms=10,
                    button=MouseButton.RIGHT,
                )
            )


@unittest.skipUnless(os.name == "nt", "Windows SendInput contract")
class WindowsTaggedPointerButtonSenderTests(unittest.TestCase):
    def test_partial_batch_attempts_button_up_cleanup(self) -> None:
        sender = WindowsTaggedPointerButtonSender()
        user32 = ScriptedUser32([1, 1])
        sender._user32 = user32  # type: ignore[attr-defined]

        with self.assertRaisesRegex(OSError, "inserted 1 of 2 events"):
            sender.click(
                MouseButton.RIGHT,
                tag=WORLD_MAP_ACTION_TEST_INPUT_TAG,
            )

        self.assertEqual([2, 1], user32.counts)

    def test_partial_batch_reports_failed_button_up_cleanup(self) -> None:
        sender = WindowsTaggedPointerButtonSender()
        user32 = ScriptedUser32([1, 0])
        sender._user32 = user32  # type: ignore[attr-defined]

        with self.assertRaisesRegex(OSError, "button-up cleanup failed"):
            sender.click(
                MouseButton.RIGHT,
                tag=WORLD_MAP_ACTION_TEST_INPUT_TAG,
            )

        self.assertEqual([2, 1], user32.counts)


if __name__ == "__main__":
    unittest.main()
