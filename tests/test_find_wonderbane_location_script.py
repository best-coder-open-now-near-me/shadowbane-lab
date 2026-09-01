import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "find-wonderbane-location.ps1"
POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required for this script test")
class FindWonderbaneLocationScriptTests(unittest.TestCase):
    def test_composes_nested_coordinates_and_returns_worlddef_metadata(self) -> None:
        world_def = """
        WORLDNAME= Aerynth
        WORLDNUM= 1
        LENGTH= 512
        WIDTH= 384
        <BEGINZONE> 1
            # ZONE_#NAME= "Western Reach"
            CENTX= 65536
            CENTZ= -49152
            YOFFSET= 10
            YROT= 90
            <BEGINZONE> 11006
                # ZONE_#NAME= "Black Drake Swamp"
                CENTX= 100
                CENTZ= -200
                YOFFSET= 5
                MAJORRAD= 384
                MINORRAD= 256
                PEACEZONE= FALSE
                ZONELOADFILE= BlackDrakeSwamp.cfg
                WEATHER= rain
            <ENDZONE>
        <ENDZONE>
        """

        result = self._lookup(world_def, "Black Drake Swamp")

        self.assertEqual(1, len(result))
        location = result[0]
        self.assertEqual("Aerynth", location["World"])
        self.assertEqual("Western Reach", location["ParentZone"])
        self.assertEqual(["Western Reach", "Black Drake Swamp"], location["ZonePath"])
        self.assertAlmostEqual(65336, location["LT"])
        self.assertAlmostEqual(49252, location["LG"])
        self.assertEqual(11006, location["TemplateId"])
        self.assertEqual(100, location["LocalCenterX"])
        self.assertEqual(-200, location["LocalCenterZ"])
        self.assertEqual(15, location["CumulativeYOffset"])
        self.assertEqual(90, location["WorldRotationDegrees"])
        self.assertEqual(384, location["MajorRadius"])
        self.assertEqual(256, location["MinorRadius"])
        self.assertFalse(location["PeaceZone"])
        self.assertEqual("rain", location["Attributes"]["WEATHER"])

    def test_fuzzy_lookup_finds_close_spelling(self) -> None:
        world_def = """
        WORLDNAME= Aerynth
        WORLDNUM= 1
        LENGTH= 512
        WIDTH= 384
        <BEGINZONE> 11006
            # ZONE_#NAME= "Black Drake Swamp"
            CENTX= 65000
            CENTZ= -49000
        <ENDZONE>
        <BEGINZONE> 11007
            # ZONE_#NAME= "Bog of the Black Drake"
            CENTX= 66000
            CENTZ= -50000
        <ENDZONE>
        """

        result = self._lookup(world_def, "blak drak swmp")

        self.assertGreaterEqual(len(result), 1)
        self.assertEqual("Black Drake Swamp", result[0]["Name"])
        self.assertGreater(result[0]["MatchScore"], 0.7)

    def test_optionally_layers_confirmed_destination_overrides(self) -> None:
        world_def = """
        WORLDNAME= Aerynth
        WORLDNUM= 1
        LENGTH= 512
        WIDTH= 384
        <BEGINZONE> 1
            # ZONE_#NAME= "Western Reach"
            CENTX= 65536
            CENTZ= -49152
        <ENDZONE>
        """
        override = {
            "schema_version": 1,
            "world_name": "Aerynth",
            "destinations": [
                {
                    "names": ["Runegate Sea Dog's Rest", "Sea Dog's Rest Runegate"],
                    "lt": 88980,
                    "lg": 45020,
                    "source": "wonderbane_server_confirmed",
                }
            ],
        }

        result = self._lookup(
            world_def,
            "Sea Dogs Rest Runegate",
            override=override,
        )

        self.assertEqual(1, len(result))
        self.assertEqual(88980, result[0]["LT"])
        self.assertEqual(45020, result[0]["LG"])
        self.assertEqual("Confirmed override", result[0]["Zone"])
        self.assertEqual("wonderbane_server_confirmed", result[0]["Source"])
        self.assertEqual(75, result[0]["ArrivalRadius"])

    def _lookup(self, world_def: str, query: str, *, override: dict | None = None) -> list:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world_path = root / "WorldDef.cfg"
            world_path.write_text(world_def, encoding="utf-8")
            command = [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-WorldDef",
                str(world_path),
                "-Query",
                query,
                "-AsJson",
            ]
            if override is None:
                command.append("-NoOverrides")
            else:
                override_path = root / "overrides.json"
                override_path.write_text(json.dumps(override), encoding="utf-8")
                command.extend(["-NamedDestinationOverrides", str(override_path)])
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if completed.returncode != 0:
                self.fail(
                    f"lookup failed with code {completed.returncode}:\n"
                    f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
                )
            return json.loads(completed.stdout)


if __name__ == "__main__":
    unittest.main()
