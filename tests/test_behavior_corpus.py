"""Integrity checks for the versioned Shadowbane behavior corpus."""

from __future__ import annotations

import json
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_PATH = _ROOT / "schemas" / "behavior-evidence-v1.schema.json"
_CORPUS_PATH = _ROOT / "research" / "shadowbane-behavior-corpus-v1.json"


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


class BehaviorCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = _load(_SCHEMA_PATH)
        cls.corpus = _load(_CORPUS_PATH)

    def test_schema_is_valid_and_corpus_matches(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.corpus)

    def test_ids_are_unique_and_references_resolve(self) -> None:
        profiles = self.corpus["profiles"]
        sources = self.corpus["sources"]
        claims = self.corpus["claims"]
        coverage = self.corpus["coverage"]

        profile_ids = [item["profile_id"] for item in profiles]
        source_ids = [item["source_id"] for item in sources]
        claim_ids = [item["claim_id"] for item in claims]
        self.assertEqual([], _duplicates(profile_ids))
        self.assertEqual([], _duplicates(source_ids))
        self.assertEqual([], _duplicates(claim_ids))

        profile_set = set(profile_ids)
        source_set = set(source_ids)
        claim_set = set(claim_ids)
        for source in sources:
            self.assertTrue(set(source["profiles"]) <= profile_set, source["source_id"])
        for claim in claims:
            self.assertIn(claim["profile_id"], profile_set, claim["claim_id"])
            for evidence in claim["evidence"]:
                self.assertIn(evidence["source_id"], source_set, claim["claim_id"])
        for row in coverage:
            self.assertTrue(set(row["claim_ids"]) <= claim_set, row["domain"])

    def test_profiles_do_not_implicitly_inherit_mechanics(self) -> None:
        for profile in self.corpus["profiles"]:
            self.assertIsNone(profile["inherits_from"], profile["profile_id"])

    def test_disputed_and_unresolved_claims_fail_closed(self) -> None:
        for claim in self.corpus["claims"]:
            if claim["confidence"] in {"disputed", "unresolved"}:
                self.assertEqual("block", claim["compile_disposition"], claim["claim_id"])

    def test_contradiction_groups_contain_multiple_incompatible_claims(self) -> None:
        groups: dict[str, list[dict[str, object]]] = defaultdict(list)
        for claim in self.corpus["claims"]:
            group = claim["contradiction_group"]
            if group is not None:
                groups[group].append(claim)

        self.assertTrue(groups, "the seed corpus should preserve at least one live contradiction")
        for group, claims in groups.items():
            self.assertGreaterEqual(len(claims), 2, group)
            self.assertTrue(
                all(claim["compile_disposition"] == "block" for claim in claims),
                group,
            )
            statements = {claim["statement"] for claim in claims}
            self.assertEqual(len(claims), len(statements), group)

    def test_captured_sources_have_repository_snapshots(self) -> None:
        for source in self.corpus["sources"]:
            if source["capture_status"] == "captured":
                self.assertIsNotNone(source["snapshot_path"], source["source_id"])
                snapshot = _ROOT / source["snapshot_path"]
                self.assertTrue(snapshot.is_file(), source["source_id"])
            if source["uri"].startswith("local://"):
                self.assertIn(source["capture_status"], {"pending", "unavailable"})

    def test_claims_bind_to_simulator_and_define_discriminating_tests(self) -> None:
        for claim in self.corpus["claims"]:
            self.assertTrue(claim["simulator_bindings"], claim["claim_id"])
            self.assertTrue(claim["test_requirements"], claim["claim_id"])

    def test_coverage_domains_are_unique_and_prioritized(self) -> None:
        rows = self.corpus["coverage"]
        self.assertEqual([], _duplicates([row["domain"] for row in rows]))
        priorities = Counter(row["priority"] for row in rows)
        self.assertGreater(priorities["P0"], 0)
        self.assertGreater(priorities["P1"], 0)
        self.assertGreater(priorities["P2"], 0)


def _duplicates(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


if __name__ == "__main__":
    unittest.main()
