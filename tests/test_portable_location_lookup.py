from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.run_shadowbane_location_lookup import resolve_world_definition
from shadowbane_vanilla_diagnostics.model import ProcessIdentity


class PortableLocationLookupTests(unittest.TestCase):
    def test_resolves_world_definition_beside_exact_running_client(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = Path(directory)
            world_def = game / "Config" / "WorldDef.cfg"
            world_def.parent.mkdir()
            world_def.write_text("world 1 Test\n", encoding="utf-8")
            identity = ProcessIdentity(42, 99, str(game / "sb.exe"))

            self.assertEqual(
                world_def.resolve(strict=True),
                resolve_world_definition(None, (identity,)),
            )

    def test_requires_one_client_when_path_is_not_explicit(self) -> None:
        with self.assertRaisesRegex(ValueError, "No running sb.exe"):
            resolve_world_definition(None, ())
        identities = (
            ProcessIdentity(42, 99, r"C:\first\sb.exe"),
            ProcessIdentity(43, 100, r"C:\second\sb.exe"),
        )
        with self.assertRaisesRegex(ValueError, "Multiple sb.exe"):
            resolve_world_definition(None, identities)


if __name__ == "__main__":
    unittest.main()
