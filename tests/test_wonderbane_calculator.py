import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

from shadowbane_lab.cli import main
from shadowbane_lab.progression import (
    CalculatorReviewStatus,
    CalculatorRuneCategory,
    StatLine,
    WonderbaneCalculatorImportError,
    capture_wonderbane_calculator_snapshot,
    import_wonderbane_calculator_snapshot,
    load_bundled_calculator_review_profile,
    parse_wonderbane_calculator_snapshot,
)

_SNAPSHOT = (
    Path(__file__).parents[1]
    / "evidence"
    / "pvp"
    / "calculator"
    / "wonderbane-calculator-20260828T074250Z.html"
)


class WonderbaneCalculatorImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = _SNAPSHOT.read_bytes()
        cls.catalog = parse_wonderbane_calculator_snapshot(cls.snapshot)

    def test_reviewed_snapshot_imports_complete_structured_declarations(self) -> None:
        catalog = self.catalog

        self.assertEqual(CalculatorReviewStatus.ACCEPTED, catalog.review_status)
        self.assertEqual(
            "311cc3e496e5362dba268fb56b2f11aecf00a2298d16746e4b0c6d90fcf9c5c0",
            catalog.declaration_sha256,
        )
        self.assertEqual(hashlib.sha256(self.snapshot).hexdigest(), catalog.snapshot_sha256)
        self.assertEqual(22, len(catalog.races))
        self.assertEqual(12, len({race.family for race in catalog.races}))
        self.assertEqual(4, len(catalog.base_classes))
        self.assertEqual(23, len(catalog.promotions))
        self.assertEqual(179, len(catalog.runes))
        self.assertEqual(
            48,
            sum(
                rune.category is CalculatorRuneCategory.DISCIPLINE
                for rune in catalog.runes
            ),
        )
        self.assertEqual("Ninja", catalog.promotion(2527).name)

    def test_source_only_references_remain_explicit_instead_of_being_invented(self) -> None:
        self.assertEqual(
            (
                "rune:3001:race:Saetor",
                "rune:3005:race:Saetor",
                "rune:3015:race:Saetor",
                "rune:3023:race:Saetor",
                "rune:3024:race:Saetor",
                "rune:3025:race:Saetor",
                "rune:3032:race:Saetor",
            ),
            self.catalog.unresolved_references,
        )

    def test_golden_level_one_human_fighter_matches_reviewed_calculator(self) -> None:
        result = self.catalog.calculate(
            race_id=2011,
            base_class_id=2500,
            promotion_id=None,
            level=1,
        )

        self.assertEqual(StatLine(55, 50, 55, 40, 50), result.attributes)
        self.assertEqual(StatLine(100, 100, 100, 100, 100), result.attribute_caps)
        self.assertEqual(30, result.available_points)
        self.assertEqual(67, result.health)
        self.assertEqual(78, result.mana)
        self.assertEqual(127, result.stamina)
        self.assertEqual(100, result.defense)

    def test_discipline_limit_and_pre_rune_requirements_fail_closed(self) -> None:
        with self.assertRaisesRegex(
            WonderbaneCalculatorImportError,
            "at most 2 disciplines",
        ):
            self.catalog.calculate(
                race_id=2013,
                base_class_id=2502,
                promotion_id=2504,
                level=59,
                rune_ids=(3029, 3046, 3007),
            )

        with self.assertRaisesRegex(
            WonderbaneCalculatorImportError,
            "minimum stats",
        ):
            self.catalog.calculate(
                race_id=2013,
                base_class_id=2502,
                promotion_id=2504,
                level=59,
                rune_ids=(250035,),
            )

    def test_changed_declaration_requires_review_and_cannot_be_calculated(self) -> None:
        changed = self.snapshot.replace(b'"name":"Animator"', b'"name":"Animator Drift"', 1)
        catalog = parse_wonderbane_calculator_snapshot(changed)

        self.assertEqual(CalculatorReviewStatus.REVIEW_REQUIRED, catalog.review_status)
        self.assertNotEqual(
            load_bundled_calculator_review_profile().declaration_sha256,
            catalog.declaration_sha256,
        )
        with self.assertRaisesRegex(
            WonderbaneCalculatorImportError,
            "require review",
        ):
            catalog.calculate(
                race_id=2011,
                base_class_id=2500,
                promotion_id=None,
                level=1,
            )

    def test_executable_data_expression_is_never_evaluated(self) -> None:
        changed = self.snapshot.replace(b"var RACES = [", b"var RACES = loadRaces() || [", 1)

        with self.assertRaisesRegex(
            WonderbaneCalculatorImportError,
            "must be an array literal",
        ):
            parse_wonderbane_calculator_snapshot(changed)

    def test_import_writes_timestamped_snapshot_hash_manifest_and_catalog(self) -> None:
        retrieved_at = datetime(2026, 8, 28, 8, 30, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifacts = import_wonderbane_calculator_snapshot(
                _SNAPSHOT,
                temporary_directory,
                retrieved_at=retrieved_at,
            )
            manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
            normalized = json.loads(artifacts.catalog_path.read_text(encoding="utf-8"))

            self.assertEqual(
                "wonderbane-calculator-20260828T083000Z.html",
                artifacts.snapshot_path.name,
            )
            self.assertEqual(self.snapshot, artifacts.snapshot_path.read_bytes())
            self.assertEqual(
                hashlib.sha256(self.snapshot).hexdigest(),
                manifest["snapshot_sha256"],
            )
            self.assertEqual("accepted", manifest["review_status"])
            self.assertEqual("wonderbane_calculator_derived", manifest["evidence_status"])
            self.assertEqual(179, normalized["counts"]["runes"])

    def test_bounded_download_path_saves_the_same_evidence_set_without_rendering(self) -> None:
        def opener(_request, *, timeout):
            self.assertEqual(30, timeout)
            return io.BytesIO(self.snapshot)

        with tempfile.TemporaryDirectory() as temporary_directory:
            artifacts = capture_wonderbane_calculator_snapshot(
                temporary_directory,
                retrieved_at=datetime(2026, 8, 28, 9, 0, tzinfo=UTC),
                opener=opener,
            )

            self.assertEqual(CalculatorReviewStatus.ACCEPTED, artifacts.catalog.review_status)
            self.assertEqual(self.snapshot, artifacts.snapshot_path.read_bytes())

    def test_cli_import_reports_pinned_paths_hashes_and_counts(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary_directory, redirect_stdout(output):
            result = main(
                (
                    "progression",
                    "import-wonderbane-calculator",
                    "--snapshot",
                    str(_SNAPSHOT),
                    "--output",
                    temporary_directory,
                    "--retrieved-at",
                    "2026-08-28T09:30:00Z",
                    "--json",
                )
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(0, result)
        self.assertTrue(payload["ok"])
        self.assertEqual("accepted", payload["review_status"])
        self.assertEqual(179, payload["counts"]["runes"])
        self.assertEqual(7, len(payload["unresolved_references"]))


if __name__ == "__main__":
    unittest.main()
