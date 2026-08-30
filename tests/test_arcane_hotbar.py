import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from shadowbane_lab.cli import main
from shadowbane_lab.client_input import (
    ArcaneHotbarLoadError,
    KeyActivation,
    load_arcane_hotbar,
    load_arcane_hotbar_text,
)


def _hotbar_set(*, f1: str | None = None, f2: str | None = None) -> str:
    powers = {0: f1, 1: f2}
    records = []
    for slot_index in range(12):
        power_name = powers.get(slot_index)
        item_type = "PowerHotButtonInfo" if power_name else "EMPTY"
        records.append(f"BEGINHBI {slot_index} {item_type}")
        if power_name:
            records.append(f'POWERNAME= "{power_name}"')
        records.append("ENDHBI")
    return "BEGINSET\n" + "\n".join(records) + "\nENDSET"


_CAPTURED_HOTBAR = (
    "IGNORED= TRUE\n"
    "BEGINHOTBAR\n"
    "CURRENTSET= 0\n"
    + _hotbar_set(f1="ROG-001", f2="ASS-013")
    + "\n"
    + _hotbar_set()
    + "\nENDHOTBAR\n"
    "IGNORED= FALSE\n"
)


class ArcaneHotbarTests(unittest.TestCase):
    def test_parses_f1_through_f12_power_assignments(self) -> None:
        table = load_arcane_hotbar_text(_CAPTURED_HOTBAR)

        self.assertEqual(0, table.current_set_index)
        self.assertEqual(2, len(table.sets))
        self.assertEqual("ROG-001", table.current_set.slots[0].power_name)
        self.assertEqual("ASS-013", table.current_set.slots[1].power_name)
        self.assertEqual("f1", table.current_set.slots[0].activation_key)
        self.assertEqual("f12", table.current_set.slots[11].activation_key)
        self.assertEqual(KeyActivation("f2"), table.current_set.slots[1].activation)
        self.assertEqual(
            (table.current_set.slots[1],),
            table.current_slots_for_power("ASS-013"),
        )

    def test_loads_utf8_bom_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SCREEN_GAME_character.cfg"
            path.write_text(_CAPTURED_HOTBAR, encoding="utf-8-sig")

            table = load_arcane_hotbar(path)

        self.assertEqual("ROG-001", table.current_set.slots[0].power_name)

    def test_rejects_missing_and_unterminated_hotbar(self) -> None:
        with self.assertRaisesRegex(ArcaneHotbarLoadError, "does not contain"):
            load_arcane_hotbar_text("CURRENTSET= 0")
        with self.assertRaisesRegex(ArcaneHotbarLoadError, "not terminated"):
            load_arcane_hotbar_text("BEGINHOTBAR\nCURRENTSET= 0")

    def test_rejects_missing_slot_in_set(self) -> None:
        malformed = _CAPTURED_HOTBAR.replace("BEGINHBI 11 EMPTY\nENDHBI\nENDSET", "ENDSET", 1)

        with self.assertRaisesRegex(ArcaneHotbarLoadError, "slots 0 through 11"):
            load_arcane_hotbar_text(malformed)

    def test_rejects_power_slot_without_power_name(self) -> None:
        malformed = _CAPTURED_HOTBAR.replace('POWERNAME= "ROG-001"\n', "", 1)

        with self.assertRaisesRegex(ArcaneHotbarLoadError, "require POWERNAME"):
            load_arcane_hotbar_text(malformed)

    def test_rejects_current_set_outside_available_sets(self) -> None:
        malformed = _CAPTURED_HOTBAR.replace("CURRENTSET= 0", "CURRENTSET= 2", 1)

        with self.assertRaisesRegex(ArcaneHotbarLoadError, "available hotbar set"):
            load_arcane_hotbar_text(malformed)

    def test_cli_reports_all_function_key_slots_and_active_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SCREEN_GAME_character.cfg"
            path.write_text(_CAPTURED_HOTBAR, encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(("client", "inspect-hotbar", str(path), "--json"))

        payload = json.loads(output.getvalue())
        current_set = payload["sets"][0]
        self.assertEqual(0, result)
        self.assertTrue(current_set["active"])
        self.assertEqual("f1", current_set["slots"][0]["activation_key"])
        self.assertEqual("ROG-001", current_set["slots"][0]["power_name"])
        self.assertEqual("ASS-013", current_set["slots"][1]["power_name"])
        self.assertEqual("f12", current_set["slots"][11]["activation_key"])


if __name__ == "__main__":
    unittest.main()
