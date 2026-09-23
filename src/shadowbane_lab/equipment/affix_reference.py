"""Field-reference affix tiers, separate from verified live modifier identity."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path

from shadowbane_lab.equipment.model import AffixPosition

_REFERENCE_FILE = "wonderbane_affix_reference_v3_7.json"


@dataclass(frozen=True, slots=True)
class ReferenceAffix:
    tier: int
    position: AffixPosition
    name: str
    effects: str
    equipment: tuple[str, ...]
    vendor_races: str
    formula_resource_cost: str
    total_resource_units: int
    evidence: str
    notes: str
    source: str


@dataclass(frozen=True, slots=True)
class AffixReference:
    edition: str
    source_document: str
    source_sha256: str
    entries: tuple[ReferenceAffix, ...]

    def by_tier(
        self, tier: int, *, position: AffixPosition | None = None
    ) -> tuple[ReferenceAffix, ...]:
        return tuple(
            row for row in self.entries
            if row.tier == tier and (position is None or row.position == position)
        )

    def lookup(
        self, name: str, *, position: AffixPosition, tier: int | None = None
    ) -> tuple[ReferenceAffix, ...]:
        """Exact names after case/space normalization; never fuzzy-match live tokens.

        Return every match: names can be reused across tiers and equipment groups.
        A missing match is unknown, not permission to discard an item.
        """
        key = " ".join(name.casefold().split())
        return tuple(
            row for row in self.entries
            if " ".join(row.name.casefold().split()) == key
            and row.position == position and (tier is None or row.tier == tier)
        )


def parse_affix_reference(data: dict[str, object]) -> AffixReference:
    if data["schema_version"] != 1:
        raise ValueError("unsupported affix reference schema")
    rows = data["affixes"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4096:
        raise ValueError("affix reference must contain a bounded nonempty list")
    entries = []
    identities = set()
    text_fields = (
        "Name", "Effects", "Equipment", "Vendor races", "Formula resource cost",
        "Evidence", "Notes", "Source",
    )
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("affix row must be an object")
        if any(not isinstance(row.get(key), str) for key in text_fields):
            raise ValueError("affix row has missing or invalid text fields")
        if not row["Name"].strip() or not row["Equipment"].strip():
            raise ValueError("affix name and equipment must be nonempty")
        tier, units = row["Tier"], row["Total resource units"]
        if type(tier) is not int or not 1 <= tier <= 4:
            raise ValueError("invalid affix tier")
        if type(units) is not int or units < 0:
            raise ValueError("invalid formula resource units")
        position = AffixPosition(row["Position"].lower())
        equipment = tuple(part.strip() for part in row["Equipment"].split(";"))
        identity = (tier, position, row["Name"].casefold(), equipment)
        if identity in identities:
            raise ValueError("duplicate affix reference row")
        identities.add(identity)
        entries.append(ReferenceAffix(
            tier, position, row["Name"], row["Effects"], equipment,
            row["Vendor races"], row["Formula resource cost"], units,
            row["Evidence"], row["Notes"], row["Source"],
        ))
    edition, document, digest = (
        data["edition"], data["source_document"], data["source_sha256"]
    )
    if not all(isinstance(value, str) and value for value in (edition, document, digest)):
        raise ValueError("missing affix reference provenance")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid reference source hash")
    return AffixReference(edition, document, digest, tuple(entries))


def load_bundled_affix_reference() -> AffixReference:
    text = files("shadowbane_lab.equipment").joinpath("data", _REFERENCE_FILE).read_text(
        encoding="utf-8"
    )
    return parse_affix_reference(json.loads(text))


class _ReferenceDataParser(HTMLParser):
    """Extract inert JSON only; never run scripts or interpret document instructions."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.capturing = False
        self.matches = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "script" and attributes.get("id") == "reference-data":
            if attributes.get("type") != "application/json":
                raise ValueError("reference-data must be inert JSON")
            self.matches += 1
            self.capturing = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.capturing = False

    def handle_data(self, data):
        if self.capturing:
            self.parts.append(data)


def import_field_reference_affixes(path: Path) -> dict[str, object]:
    """Import only the supplied document's affix data, preserving its evidence labels."""
    with path.open("rb") as source:
        raw = source.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("field reference exceeds 2 MB")
    parser = _ReferenceDataParser()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    if parser.matches != 1 or parser.capturing:
        raise ValueError("expected exactly one complete reference-data JSON block")
    document = json.loads("".join(parser.parts))
    result = {
        "schema_version": 1,
        "edition": document["edition"],
        "source_document": path.name,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_repo_commit": document.get("repo_commit"),
        "status": "user_selected_historical_reference_not_live_token_authority",
        "affixes": document["data"]["affixes"],
    }
    parse_affix_reference(result)
    return result
