import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from shadowbane_lab.cli import main
from shadowbane_lab.client_input import (
    ArcaneClientAction,
    ArcaneHotkeyLoadError,
    HotkeyActivation,
    KeyActivation,
    load_arcane_hotkeys,
    load_arcane_hotkeys_text,
)

_CAPTURED_TARGET_BINDINGS = """
IGNORED= TRUE
BEGINHOTKEYS
    KEY= "SemiColon" FALSE FALSE FALSE 188 0 0 ""
    KEY= "Apostrophe" FALSE FALSE FALSE 189 0 0 ""
    KEY= "A" FALSE TRUE FALSE 1551 0 0 ""
    KEY= "F5" TRUE FALSE TRUE 25 0 0 ""
ENDHOTKEYS
IGNORED= FALSE
"""


class ArcaneHotkeyTests(unittest.TestCase):
    def test_world_map_action_matches_captured_arcane_pref_message(self) -> None:
        self.assertEqual(48, ArcaneClientAction.WORLD_MAP)

    def test_parses_captured_mob_cycle_bindings_losslessly(self) -> None:
        table = load_arcane_hotkeys_text(_CAPTURED_TARGET_BINDINGS)

        next_mob = table.bindings_for(ArcaneClientAction.TARGET_NEXT_MOB)
        previous_mob = table.bindings_for(ArcaneClientAction.TARGET_PREVIOUS_MOB)

        self.assertEqual((";",), next_mob[0].input_keys)
        self.assertEqual(("'",), previous_mob[0].input_keys)
        self.assertEqual(KeyActivation(";"), next_mob[0].activation)
        self.assertEqual(188, next_mob[0].action_code)
        self.assertEqual(0, next_mob[0].parameter_one)

    def test_preserves_modifier_order_for_guarded_hotkeys(self) -> None:
        table = load_arcane_hotkeys_text(_CAPTURED_TARGET_BINDINGS)

        binding = table.bindings_for(25)[0]

        self.assertEqual(("shift", "alt", "f5"), binding.input_keys)
        self.assertEqual(HotkeyActivation(("shift", "alt", "f5")), binding.activation)

    def test_reports_clear_target_as_unbound_when_no_action_102_record_exists(self) -> None:
        table = load_arcane_hotkeys_text(_CAPTURED_TARGET_BINDINGS)

        self.assertEqual((), table.bindings_for(ArcaneClientAction.CLEAR_TARGET))

    def test_loads_utf8_bom_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ArcanePref.cfg"
            path.write_text(_CAPTURED_TARGET_BINDINGS, encoding="utf-8-sig")

            table = load_arcane_hotkeys(path)

        self.assertEqual(4, len(table.bindings))

    def test_rejects_malformed_record_inside_table(self) -> None:
        text = "BEGINHOTKEYS\nKEY= broken\nENDHOTKEYS\n"

        with self.assertRaisesRegex(ArcaneHotkeyLoadError, "malformed.*line 2"):
            load_arcane_hotkeys_text(text)

    def test_rejects_duplicate_key_chords(self) -> None:
        text = """
BEGINHOTKEYS
KEY= "F4" FALSE FALSE FALSE 188 0 0 ""
KEY= "F4" FALSE FALSE FALSE 189 0 0 ""
ENDHOTKEYS
"""

        with self.assertRaisesRegex(ArcaneHotkeyLoadError, "one key chord"):
            load_arcane_hotkeys_text(text)

    def test_rejects_missing_or_unterminated_table(self) -> None:
        with self.assertRaisesRegex(ArcaneHotkeyLoadError, "does not contain"):
            load_arcane_hotkeys_text("KEY= nothing")
        with self.assertRaisesRegex(ArcaneHotkeyLoadError, "not terminated"):
            load_arcane_hotkeys_text("BEGINHOTKEYS\n")

    def test_rejects_key_names_that_input_backend_cannot_represent(self) -> None:
        text = """
BEGINHOTKEYS
    KEY= "Mystery Key" FALSE FALSE FALSE 188 0 0 ""
ENDHOTKEYS
"""

        with self.assertRaisesRegex(ArcaneHotkeyLoadError, "unsupported"):
            load_arcane_hotkeys_text(text)

    def test_cli_reports_verified_target_actions_and_unbound_clear(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ArcanePref.cfg"
            path.write_text(_CAPTURED_TARGET_BINDINGS, encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(("client", "inspect-hotkeys", str(path), "--json"))

        payload = json.loads(output.getvalue())
        actions = {
            item["semantic_action"]: item for item in payload["target_actions"]
        }
        self.assertEqual(0, result)
        self.assertEqual(
            [";"],
            actions["client.pve.target_next_mobile"]["bindings"][0]["input_keys"],
        )
        self.assertEqual(
            ["'"],
            actions["client.pve.target_previous_mobile"]["bindings"][0]["input_keys"],
        )
        self.assertFalse(actions["client.pve.clear_selection"]["bound"])


if __name__ == "__main__":
    unittest.main()
