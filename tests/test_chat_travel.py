import unittest

from shadowbane_lab.client_input import (
    AnyStopSignal,
    EventEmergencyStop,
    ForegroundWindowGuard,
    StaticWindowInspector,
)
from shadowbane_lab.travel import GoChatCommandAssembler, WindowsGoChatCommandListener
from tests.test_client_input_compiler import _load_profile
from tests.test_client_input_executor import _valid_snapshot


class GoChatCommandAssemblerTests(unittest.TestCase):
    def test_submits_go_command_between_chat_enter_events(self) -> None:
        assembler = GoChatCommandAssembler()

        opened = assembler.handle_enter()
        for character in "/go 120000 60000":
            assembler.handle_character(character)
        submitted = assembler.handle_enter()

        self.assertTrue(opened.interaction_started)
        self.assertEqual("/go 120000 60000", submitted.submitted_command)
        self.assertFalse(assembler.line_active)

    def test_slash_can_start_a_command_after_clicking_the_chat_line(self) -> None:
        assembler = GoChatCommandAssembler()

        started = assembler.handle_character("/")
        for character in "go":
            assembler.handle_character(character)
        submitted = assembler.handle_enter()

        self.assertTrue(started.interaction_started)
        self.assertEqual("/go", submitted.submitted_command)

    def test_submits_stop_command_and_allows_trailing_spaces(self) -> None:
        assembler = GoChatCommandAssembler()
        assembler.handle_enter()
        for character in "/stop  ":
            assembler.handle_character(character)

        self.assertEqual("/stop  ", assembler.handle_enter().submitted_command)

    def test_discards_stop_command_with_arguments(self) -> None:
        assembler = GoChatCommandAssembler()
        assembler.handle_enter()
        for character in "/stop now":
            assembler.handle_character(character)

        self.assertIsNone(assembler.retained_text)
        self.assertIsNone(assembler.handle_enter().submitted_command)

    def test_discards_ordinary_chat_and_other_slash_commands(self) -> None:
        assembler = GoChatCommandAssembler()

        assembler.handle_enter()
        for character in "hello world":
            assembler.handle_character(character)
        self.assertIsNone(assembler.retained_text)
        self.assertIsNone(assembler.handle_enter().submitted_command)

        assembler.handle_enter()
        for character in "/guild secret text":
            assembler.handle_character(character)
        self.assertIsNone(assembler.retained_text)
        self.assertIsNone(assembler.handle_enter().submitted_command)

    def test_backspace_preserves_a_corrected_go_prefix(self) -> None:
        assembler = GoChatCommandAssembler()
        assembler.handle_enter()
        for character in "/g":
            assembler.handle_character(character)
        assembler.handle_backspace()
        for character in "go 1 2":
            assembler.handle_character(character)

        self.assertEqual("/go 1 2", assembler.handle_enter().submitted_command)

    def test_escape_forgets_a_partial_command(self) -> None:
        assembler = GoChatCommandAssembler()
        assembler.handle_enter()
        for character in "/go 1":
            assembler.handle_character(character)

        assembler.handle_escape()

        self.assertFalse(assembler.line_active)
        self.assertIsNone(assembler.retained_text)

    def test_windows_key_mapping_covers_go_coordinate_syntax(self) -> None:
        mapped = WindowsGoChatCommandListener._character_for

        self.assertEqual("/", mapped(0xBF, shift_down=False))
        self.assertEqual("g", mapped(0x47, shift_down=False))
        self.assertEqual("9", mapped(0x69, shift_down=False))
        self.assertEqual("-", mapped(0xBD, shift_down=False))
        self.assertEqual(".", mapped(0xBE, shift_down=False))
        self.assertEqual(",", mapped(0xBC, shift_down=False))
        self.assertEqual("=", mapped(0xBB, shift_down=False))
        self.assertEqual("!", mapped(0x31, shift_down=True))
        self.assertEqual("_", mapped(0xBD, shift_down=True))

    def test_foreground_physical_pointer_interaction_revokes_active_route(self) -> None:
        interactions: list[str] = []
        listener = WindowsGoChatCommandListener(
            ForegroundWindowGuard(_load_profile(), StaticWindowInspector(_valid_snapshot())),
            on_command=lambda _: None,
            on_interaction=lambda: interactions.append("cancel"),
        )
        listener._assembler.handle_enter()
        listener._assembler.handle_character("/")

        listener._handle_pointer_interaction()

        self.assertEqual(["cancel"], interactions)
        self.assertFalse(listener._assembler.line_active)


class AnyStopSignalTests(unittest.TestCase):
    def test_trips_when_any_member_signal_trips(self) -> None:
        first = EventEmergencyStop()
        second = EventEmergencyStop()
        combined = AnyStopSignal(first, second)

        self.assertFalse(combined.is_set())
        second.trip()
        self.assertTrue(combined.is_set())

    def test_requires_at_least_one_signal(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            AnyStopSignal()
