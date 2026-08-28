"""Safe, revision-pinned import of the public WonderBane character calculator.

The calculator is embedded in the public home page as JavaScript declarations.  This module
never evaluates that JavaScript.  It recognizes a deliberately small literal grammar, extracts
only reviewed declarations, and fingerprints the result before calculator outputs are trusted.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlparse

from shadowbane_lab.progression.model import StatLine

CALCULATOR_SCHEMA_VERSION = 1
CALCULATOR_SOURCE_URL = "https://wonderbane.com/"
CALCULATOR_EVIDENCE_STATUS = "wonderbane_calculator_derived"
_MAXIMUM_SNAPSHOT_BYTES = 2 * 1024 * 1024
_BUNDLED_REVIEW_NAME = "data/wonderbane_calculator_review_v1.json"
_DECLARATION_NAMES = ("RACES", "BASES", "PROMOS", "RUNES")
_FORMULA_NAMES = (
    "levelBonus",
    "fgForLevel",
    "categoryOf",
    "runeAllowed",
    "runeMinsMet",
    "compute",
    "disciplineLimit",
)


class WonderbaneCalculatorImportError(ValueError):
    """Raised when a calculator snapshot cannot be imported without guessing."""


class CalculatorReviewStatus(StrEnum):
    ACCEPTED = "accepted"
    REVIEW_REQUIRED = "review_required"


class CalculatorRuneCategory(StrEnum):
    DISCIPLINE = "discipline"
    STARTING = "starting"
    STAT_TIER = "stat_tier"


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise WonderbaneCalculatorImportError(f"{field_name} must be a non-empty string")


def _integer(value: object, field_name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WonderbaneCalculatorImportError(f"{field_name} must be an integer")
    if minimum is not None and value < minimum:
        raise WonderbaneCalculatorImportError(f"{field_name} must be at least {minimum}")
    return value


def _stats(value: object, field_name: str) -> StatLine:
    if not isinstance(value, list) or len(value) != 5:
        raise WonderbaneCalculatorImportError(f"{field_name} must be a five-integer array")
    values = tuple(_integer(item, field_name) for item in value)
    return StatLine(*values)


def _strings(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise WonderbaneCalculatorImportError(f"{field_name} must be an array")
    result = tuple(value)
    if any(not isinstance(item, str) or not item.strip() for item in result):
        raise WonderbaneCalculatorImportError(f"{field_name} must contain non-empty strings")
    if len(result) != len(set(result)):
        raise WonderbaneCalculatorImportError(f"{field_name} must not contain duplicates")
    return result


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise WonderbaneCalculatorImportError(f"{field_name} must be an object")
    return value


def _exact_fields(
    data: dict[str, Any],
    required: set[str],
    *,
    optional: set[str] = frozenset(),
    field_name: str,
) -> None:
    missing = required - data.keys()
    unknown = data.keys() - required - optional
    if missing:
        raise WonderbaneCalculatorImportError(
            f"{field_name} is missing fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise WonderbaneCalculatorImportError(
            f"{field_name} has unknown fields: {', '.join(sorted(unknown))}"
        )


@dataclass(frozen=True, slots=True)
class CalculatorRace:
    record_id: int
    name: str
    family: str
    sex: str
    starting_attributes: StatLine
    maximum_attributes: StatLine
    creation_points: int
    health_base: int
    mana_base: int
    stamina_base: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.record_id,
            "name": self.name,
            "family": self.family,
            "sex": self.sex,
            "starting_attributes": list(self.starting_attributes.values()),
            "maximum_attributes": list(self.maximum_attributes.values()),
            "creation_points": self.creation_points,
            "health_base": self.health_base,
            "mana_base": self.mana_base,
            "stamina_base": self.stamina_base,
        }


@dataclass(frozen=True, slots=True)
class CalculatorClass:
    record_id: int
    name: str
    allowed_base_classes: tuple[str, ...]
    attribute_modifiers: StatLine
    health_growth: int
    mana_growth: int
    stamina_growth: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.record_id,
            "name": self.name,
            "allowed_base_classes": list(self.allowed_base_classes),
            "attribute_modifiers": list(self.attribute_modifiers.values()),
            "health_growth": self.health_growth,
            "mana_growth": self.mana_growth,
            "stamina_growth": self.stamina_growth,
        }


@dataclass(frozen=True, slots=True)
class CalculatorSkillGrant:
    name: str
    amount: int

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "amount": self.amount}


@dataclass(frozen=True, slots=True)
class CalculatorRune:
    record_id: int
    name: str
    category: CalculatorRuneCategory
    source_kind: str
    cost: int
    minimum_level: int
    stat_grants: StatLine
    cap_grants: StatLine
    minimum_stats: StatLine
    allowed_races: tuple[str, ...]
    allowed_base_classes: tuple[str, ...]
    allowed_promotions: tuple[str, ...]
    description: str | None
    powers: tuple[str, ...]
    skill_grants: tuple[CalculatorSkillGrant, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.record_id,
            "name": self.name,
            "category": self.category.value,
            "source_kind": self.source_kind,
            "cost": self.cost,
            "minimum_level": self.minimum_level,
            "stat_grants": list(self.stat_grants.values()),
            "cap_grants": list(self.cap_grants.values()),
            "minimum_stats": list(self.minimum_stats.values()),
            "allowed_races": list(self.allowed_races),
            "allowed_base_classes": list(self.allowed_base_classes),
            "allowed_promotions": list(self.allowed_promotions),
            "description": self.description,
            "powers": list(self.powers),
            "skill_grants": [item.to_dict() for item in self.skill_grants],
        }


@dataclass(frozen=True, slots=True)
class CalculatorFormulaEvidence:
    boon: int
    function_sha256: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "boon": self.boon,
            "function_sha256": dict(self.function_sha256),
        }


@dataclass(frozen=True, slots=True)
class CalculatorReviewProfile:
    profile_id: str
    declaration_sha256: str
    race_records: int
    base_classes: int
    promotions: int
    runes: int

    def __post_init__(self) -> None:
        _identifier(self.profile_id, "review profile id")
        if not re.fullmatch(r"[0-9a-f]{64}", self.declaration_sha256):
            raise WonderbaneCalculatorImportError(
                "review declaration_sha256 must be lowercase SHA-256"
            )
        for value, name in (
            (self.race_records, "race records"),
            (self.base_classes, "base classes"),
            (self.promotions, "promotions"),
            (self.runes, "runes"),
        ):
            _integer(value, name, minimum=1)


@dataclass(frozen=True, slots=True)
class CalculatorBuildOutput:
    attributes: StatLine
    attribute_caps: StatLine
    attributes_before_runes: StatLine
    creation_points: int
    level_points: int
    trained_points: int
    rune_cost: int
    available_points: int
    health: int
    mana: int
    stamina: int
    defense: int
    base_growth_factor: float
    promotion_growth_factor: float

    def to_dict(self) -> dict[str, object]:
        return {
            "attributes": list(self.attributes.values()),
            "attribute_caps": list(self.attribute_caps.values()),
            "attributes_before_runes": list(self.attributes_before_runes.values()),
            "creation_points": self.creation_points,
            "level_points": self.level_points,
            "trained_points": self.trained_points,
            "rune_cost": self.rune_cost,
            "available_points": self.available_points,
            "health": self.health,
            "mana": self.mana,
            "stamina": self.stamina,
            "defense": self.defense,
            "base_growth_factor": self.base_growth_factor,
            "promotion_growth_factor": self.promotion_growth_factor,
        }


@dataclass(frozen=True, slots=True)
class WonderbaneCalculatorCatalog:
    source_url: str
    snapshot_sha256: str
    declaration_sha256: str
    review_status: CalculatorReviewStatus
    review_profile_id: str
    evidence_status: str
    races: tuple[CalculatorRace, ...]
    base_classes: tuple[CalculatorClass, ...]
    promotions: tuple[CalculatorClass, ...]
    runes: tuple[CalculatorRune, ...]
    formulas: CalculatorFormulaEvidence
    unresolved_references: tuple[str, ...]

    def __post_init__(self) -> None:
        for digest, field_name in (
            (self.snapshot_sha256, "snapshot SHA-256"),
            (self.declaration_sha256, "declaration SHA-256"),
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise WonderbaneCalculatorImportError(
                    f"{field_name} must be lowercase SHA-256"
                )
        for records, name in (
            (self.races, "race"),
            (self.base_classes, "base class"),
            (self.promotions, "promotion"),
            (self.runes, "rune"),
        ):
            ids = tuple(item.record_id for item in records)
            if len(ids) != len(set(ids)):
                raise WonderbaneCalculatorImportError(f"{name} ids must be unique")

    def race(self, record_id: int) -> CalculatorRace:
        return _record_by_id(self.races, record_id, "race")

    def base_class(self, record_id: int) -> CalculatorClass:
        return _record_by_id(self.base_classes, record_id, "base class")

    def promotion(self, record_id: int) -> CalculatorClass:
        return _record_by_id(self.promotions, record_id, "promotion")

    def rune(self, record_id: int) -> CalculatorRune:
        return _record_by_id(self.runes, record_id, "rune")

    def calculate(
        self,
        *,
        race_id: int,
        base_class_id: int,
        promotion_id: int | None,
        level: int,
        trained_modifiers: StatLine | None = None,
        rune_ids: tuple[int, ...] = (),
    ) -> CalculatorBuildOutput:
        """Evaluate the reviewed calculator formulas without executing site JavaScript."""

        if self.review_status is not CalculatorReviewStatus.ACCEPTED:
            raise WonderbaneCalculatorImportError(
                "calculator declarations require review before formulas can be evaluated"
            )
        _integer(level, "level", minimum=1)
        if level > 80:
            raise WonderbaneCalculatorImportError("level must not exceed the calculator's 80 cap")
        if len(rune_ids) != len(set(rune_ids)):
            raise WonderbaneCalculatorImportError("rune ids must not contain duplicates")
        if len(rune_ids) > 12:
            raise WonderbaneCalculatorImportError("calculator allows at most 12 runes")

        race = self.race(race_id)
        base = self.base_class(base_class_id)
        promotion = self.promotion(promotion_id) if promotion_id is not None else None
        if promotion is not None and base.name not in promotion.allowed_base_classes:
            raise WonderbaneCalculatorImportError(
                f"{promotion.name} does not promote from {base.name}"
            )
        modifiers = trained_modifiers or StatLine(0, 0, 0, 0, 0)
        if any(value < -5 for value in modifiers.values()):
            raise WonderbaneCalculatorImportError(
                "trained modifiers cannot dump a stat below -5"
            )

        before_runes = _sum_stats(
            race.starting_attributes,
            base.attribute_modifiers,
            modifiers,
            StatLine(*(self.formulas.boon for _ in range(5))),
        )
        if any(
            value > maximum
            for value, maximum in zip(
                before_runes.values(), race.maximum_attributes.values(), strict=True
            )
        ):
            raise WonderbaneCalculatorImportError(
                "trained modifiers exceed a race attribute cap before runes"
            )

        selected = tuple(self.rune(record_id) for record_id in rune_ids)
        discipline_limit = 3 if level >= 70 else 2
        if sum(item.category is CalculatorRuneCategory.DISCIPLINE for item in selected) > (
            discipline_limit
        ):
            raise WonderbaneCalculatorImportError(
                f"calculator allows at most {discipline_limit} disciplines at level {level}"
            )
        for rune in selected:
            _validate_rune_access(rune, race, base, promotion, level, before_runes)

        rune_cost = sum(item.cost for item in selected)
        level_points = _level_bonus(level)
        trained_points = sum(modifiers.values())
        if rune_cost > race.creation_points + level_points - trained_points:
            raise WonderbaneCalculatorImportError(
                "selected rune cost exceeds the calculator's available point pool"
            )
        attributes = _sum_stats(before_runes, *(item.stat_grants for item in selected))
        caps = _sum_stats(
            race.maximum_attributes,
            *(item.cap_grants for item in selected),
        )
        available = max(0, race.creation_points - rune_cost + level_points - trained_points)
        base_factor, promotion_factor = _growth_factors(level, promotion is not None)
        constitution = attributes.constitution
        spirit = attributes.spirit
        promo_health = promotion.health_growth if promotion is not None else 0
        promo_mana = promotion.mana_growth if promotion is not None else 0
        promo_stamina = promotion.stamina_growth if promotion is not None else 0
        health = (
            (base_factor * base.health_growth + promotion_factor * promo_health)
            * (0.3 + 0.005 * constitution)
            + constitution
            + race.health_base
        )
        mana = (
            (base_factor * base.mana_growth + promotion_factor * promo_mana)
            * (0.3 + 0.005 * spirit)
            + spirit
            + race.mana_base
        )
        stamina = (
            (base_factor * base.stamina_growth + promotion_factor * promo_stamina)
            * (0.3 + 0.005 * constitution)
            + constitution
            + race.stamina_base
        )
        return CalculatorBuildOutput(
            attributes=attributes,
            attribute_caps=caps,
            attributes_before_runes=before_runes,
            creation_points=race.creation_points,
            level_points=level_points,
            trained_points=trained_points,
            rune_cost=rune_cost,
            available_points=available,
            health=_javascript_round(health),
            mana=_javascript_round(mana),
            stamina=_javascript_round(stamina),
            defense=attributes.dexterity * 2,
            base_growth_factor=base_factor,
            promotion_growth_factor=promotion_factor,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": CALCULATOR_SCHEMA_VERSION,
            "source": {
                "url": self.source_url,
                "snapshot_sha256": self.snapshot_sha256,
                "declaration_sha256": self.declaration_sha256,
                "review_profile_id": self.review_profile_id,
                "review_status": self.review_status.value,
                "evidence_status": self.evidence_status,
            },
            "counts": {
                "race_records": len(self.races),
                "race_families": len({item.family for item in self.races}),
                "base_classes": len(self.base_classes),
                "promotions": len(self.promotions),
                "runes": len(self.runes),
                "disciplines": sum(
                    item.category is CalculatorRuneCategory.DISCIPLINE
                    for item in self.runes
                ),
            },
            "unresolved_references": list(self.unresolved_references),
            "formulas": self.formulas.to_dict(),
            "races": [item.to_dict() for item in self.races],
            "base_classes": [item.to_dict() for item in self.base_classes],
            "promotions": [item.to_dict() for item in self.promotions],
            "runes": [item.to_dict() for item in self.runes],
        }


@dataclass(frozen=True, slots=True)
class CalculatorSnapshotArtifacts:
    snapshot_path: Path
    manifest_path: Path
    catalog_path: Path
    catalog: WonderbaneCalculatorCatalog


def load_bundled_calculator_review_profile() -> CalculatorReviewProfile:
    resource = files("shadowbane_lab.progression").joinpath(_BUNDLED_REVIEW_NAME)
    return load_calculator_review_profile_text(resource.read_text(encoding="utf-8"))


def load_calculator_review_profile_text(text: str) -> CalculatorReviewProfile:
    try:
        data = _mapping(json.loads(text), "calculator review profile")
    except (json.JSONDecodeError, TypeError) as exc:
        raise WonderbaneCalculatorImportError(
            "calculator review profile is not valid JSON"
        ) from exc
    _exact_fields(
        data,
        {
            "schema_version",
            "profile_id",
            "declaration_sha256",
            "race_records",
            "base_classes",
            "promotions",
            "runes",
        },
        field_name="calculator review profile",
    )
    if _integer(data["schema_version"], "schema version") != CALCULATOR_SCHEMA_VERSION:
        raise WonderbaneCalculatorImportError(
            "unsupported calculator review profile schema version"
        )
    return CalculatorReviewProfile(
        profile_id=_required_string(data, "profile_id"),
        declaration_sha256=_required_string(data, "declaration_sha256"),
        race_records=_integer(data["race_records"], "race records", minimum=1),
        base_classes=_integer(data["base_classes"], "base classes", minimum=1),
        promotions=_integer(data["promotions"], "promotions", minimum=1),
        runes=_integer(data["runes"], "runes", minimum=1),
    )


def parse_wonderbane_calculator_snapshot(
    snapshot: bytes,
    *,
    review_profile: CalculatorReviewProfile | None = None,
    source_url: str = CALCULATOR_SOURCE_URL,
) -> WonderbaneCalculatorCatalog:
    """Parse only the calculator's reviewed data and formula declarations."""

    if not isinstance(snapshot, bytes) or not snapshot:
        raise WonderbaneCalculatorImportError("calculator snapshot must contain bytes")
    if len(snapshot) > _MAXIMUM_SNAPSHOT_BYTES:
        raise WonderbaneCalculatorImportError("calculator snapshot exceeds the 2 MiB bound")
    try:
        text = snapshot.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise WonderbaneCalculatorImportError("calculator snapshot is not UTF-8") from exc
    profile = review_profile or load_bundled_calculator_review_profile()

    declarations = {
        name: _RestrictedLiteralParser(_extract_declaration(text, name)).parse()
        for name in _DECLARATION_NAMES
    }
    functions = {name: _extract_function(text, name) for name in _FORMULA_NAMES}
    boon = _extract_boon(text)
    declaration_material = {
        "declarations": declarations,
        "boon": boon,
        "functions": functions,
    }
    declaration_sha256 = hashlib.sha256(
        json.dumps(
            declaration_material,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    snapshot_sha256 = hashlib.sha256(snapshot).hexdigest()

    races = tuple(_parse_race(item) for item in _array(declarations["RACES"], "RACES"))
    bases = tuple(_parse_base(item) for item in _array(declarations["BASES"], "BASES"))
    raw_promotions = tuple(
        _parse_promotion(item)
        for item in _array(declarations["PROMOS"], "PROMOS")
    )
    no_promotion = tuple(item for item in raw_promotions if item.record_id == 0)
    if len(no_promotion) != 1 or no_promotion[0].name != "(none)":
        raise WonderbaneCalculatorImportError(
            "PROMOS must contain exactly one id-zero '(none)' sentinel"
        )
    promotions = tuple(item for item in raw_promotions if item.record_id != 0)
    runes = tuple(_parse_rune(item) for item in _array(declarations["RUNES"], "RUNES"))

    counts_match = (
        len(races) == profile.race_records
        and len(bases) == profile.base_classes
        and len(promotions) == profile.promotions
        and len(runes) == profile.runes
    )
    accepted = declaration_sha256 == profile.declaration_sha256 and counts_match
    unresolved = _unresolved_references(races, bases, promotions, runes)
    function_hashes = tuple(
        (name, hashlib.sha256(functions[name].encode("utf-8")).hexdigest())
        for name in _FORMULA_NAMES
    )
    return WonderbaneCalculatorCatalog(
        source_url=source_url,
        snapshot_sha256=snapshot_sha256,
        declaration_sha256=declaration_sha256,
        review_status=(
            CalculatorReviewStatus.ACCEPTED
            if accepted
            else CalculatorReviewStatus.REVIEW_REQUIRED
        ),
        review_profile_id=profile.profile_id,
        evidence_status=CALCULATOR_EVIDENCE_STATUS,
        races=races,
        base_classes=bases,
        promotions=promotions,
        runes=runes,
        formulas=CalculatorFormulaEvidence(boon=boon, function_sha256=function_hashes),
        unresolved_references=unresolved,
    )


def import_wonderbane_calculator_snapshot(
    source_path: str | Path,
    output_directory: str | Path,
    *,
    retrieved_at: datetime | None = None,
    review_profile: CalculatorReviewProfile | None = None,
    source_url: str = CALCULATOR_SOURCE_URL,
) -> CalculatorSnapshotArtifacts:
    """Copy a snapshot into a timestamped evidence set and normalize its declarations."""

    source = Path(source_path)
    snapshot = source.read_bytes()
    return _write_snapshot_artifacts(
        snapshot,
        output_directory,
        retrieved_at=retrieved_at,
        review_profile=review_profile,
        source_url=source_url,
    )


def capture_wonderbane_calculator_snapshot(
    output_directory: str | Path,
    *,
    retrieved_at: datetime | None = None,
    review_profile: CalculatorReviewProfile | None = None,
    source_url: str = CALCULATOR_SOURCE_URL,
    opener: Callable[..., BinaryIO] | None = None,
) -> CalculatorSnapshotArtifacts:
    """Download the bounded public HTML document without rendering or executing it."""

    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname != "wonderbane.com" or parsed.path != "/":
        raise WonderbaneCalculatorImportError(
            "calculator capture URL must be exactly the WonderBane HTTPS home page"
        )
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "shadowbane-lab-calculator-evidence/1"},
    )
    open_response = opener or urllib.request.urlopen
    with open_response(request, timeout=30) as response:
        snapshot = response.read(_MAXIMUM_SNAPSHOT_BYTES + 1)
    if len(snapshot) > _MAXIMUM_SNAPSHOT_BYTES:
        raise WonderbaneCalculatorImportError("calculator snapshot exceeds the 2 MiB bound")
    return _write_snapshot_artifacts(
        snapshot,
        output_directory,
        retrieved_at=retrieved_at,
        review_profile=review_profile,
        source_url=source_url,
    )


def _write_snapshot_artifacts(
    snapshot: bytes,
    output_directory: str | Path,
    *,
    retrieved_at: datetime | None,
    review_profile: CalculatorReviewProfile | None,
    source_url: str,
) -> CalculatorSnapshotArtifacts:
    catalog = parse_wonderbane_calculator_snapshot(
        snapshot,
        review_profile=review_profile,
        source_url=source_url,
    )
    timestamp = (retrieved_at or datetime.now(UTC)).astimezone(UTC)
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    stem = f"wonderbane-calculator-{stamp}"
    snapshot_path = output / f"{stem}.html"
    manifest_path = output / f"{stem}.manifest.json"
    catalog_path = output / f"{stem}.catalog.json"
    if snapshot_path.exists() or manifest_path.exists() or catalog_path.exists():
        raise WonderbaneCalculatorImportError(
            f"calculator evidence set already exists for timestamp {stamp}"
        )
    snapshot_path.write_bytes(snapshot)
    manifest = {
        "schema_version": CALCULATOR_SCHEMA_VERSION,
        "retrieved_at": timestamp.isoformat().replace("+00:00", "Z"),
        "source_url": source_url,
        "snapshot_file": snapshot_path.name,
        "snapshot_sha256": catalog.snapshot_sha256,
        "catalog_file": catalog_path.name,
        "declaration_sha256": catalog.declaration_sha256,
        "review_profile_id": catalog.review_profile_id,
        "review_status": catalog.review_status.value,
        "evidence_status": catalog.evidence_status,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    catalog_path.write_text(
        json.dumps(catalog.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return CalculatorSnapshotArtifacts(
        snapshot_path=snapshot_path,
        manifest_path=manifest_path,
        catalog_path=catalog_path,
        catalog=catalog,
    )


class _RestrictedLiteralParser:
    """Parser for arrays/objects/strings/integers with bare object keys only."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._index = 0

    def parse(self) -> object:
        value = self._value()
        self._whitespace()
        if self._index != len(self._text):
            raise WonderbaneCalculatorImportError(
                "unsupported token follows calculator literal declaration"
            )
        return value

    def _value(self) -> object:
        self._whitespace()
        if self._index >= len(self._text):
            raise WonderbaneCalculatorImportError("calculator literal ended unexpectedly")
        token = self._text[self._index]
        if token == "[":
            return self._array()
        if token == "{":
            return self._object()
        if token == '"':
            return self._string()
        match = re.match(r"-?(?:0|[1-9][0-9]*)", self._text[self._index :])
        if match is None:
            raise WonderbaneCalculatorImportError(
                "calculator literal contains unsupported executable syntax"
            )
        self._index += len(match.group(0))
        return int(match.group(0))

    def _array(self) -> list[object]:
        self._index += 1
        result: list[object] = []
        self._whitespace()
        if self._take("]"):
            return result
        while True:
            result.append(self._value())
            self._whitespace()
            if self._take("]"):
                return result
            self._require(",")

    def _object(self) -> dict[str, object]:
        self._index += 1
        result: dict[str, object] = {}
        self._whitespace()
        if self._take("}"):
            return result
        while True:
            self._whitespace()
            if self._index < len(self._text) and self._text[self._index] == '"':
                key = self._string()
            else:
                match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", self._text[self._index :])
                if match is None:
                    raise WonderbaneCalculatorImportError(
                        "calculator object key is not a simple identifier"
                    )
                key = match.group(0)
                self._index += len(key)
            if key in result:
                raise WonderbaneCalculatorImportError(
                    f"calculator object contains duplicate key {key}"
                )
            self._whitespace()
            self._require(":")
            result[key] = self._value()
            self._whitespace()
            if self._take("}"):
                return result
            self._require(",")

    def _string(self) -> str:
        try:
            value, consumed = json.JSONDecoder().raw_decode(self._text[self._index :])
        except json.JSONDecodeError as exc:
            raise WonderbaneCalculatorImportError(
                "calculator literal contains an invalid string"
            ) from exc
        if not isinstance(value, str):
            raise WonderbaneCalculatorImportError("calculator string decoder returned non-string")
        self._index += consumed
        return value

    def _whitespace(self) -> None:
        while self._index < len(self._text) and self._text[self._index].isspace():
            self._index += 1

    def _take(self, token: str) -> bool:
        if self._index < len(self._text) and self._text[self._index] == token:
            self._index += 1
            return True
        return False

    def _require(self, token: str) -> None:
        if not self._take(token):
            raise WonderbaneCalculatorImportError(
                f"calculator literal expected {token!r}"
            )


def _extract_declaration(text: str, name: str) -> str:
    matches = tuple(re.finditer(rf"\bvar\s+{re.escape(name)}\s*=\s*", text))
    if len(matches) != 1:
        raise WonderbaneCalculatorImportError(
            f"expected exactly one calculator {name} declaration"
        )
    start = matches[0].end()
    if start >= len(text) or text[start] != "[":
        raise WonderbaneCalculatorImportError(f"calculator {name} must be an array literal")
    end = _balanced_end(text, start, "[", "]")
    if not re.match(r"\s*;", text[end:]):
        raise WonderbaneCalculatorImportError(
            f"calculator {name} array must end with a semicolon"
        )
    return text[start:end]


def _extract_function(text: str, name: str) -> str:
    matches = tuple(
        re.finditer(rf"\bfunction\s+{re.escape(name)}\s*\([^)]*\)\s*\{{", text)
    )
    if len(matches) != 1:
        raise WonderbaneCalculatorImportError(
            f"expected exactly one calculator {name} function"
        )
    start = matches[0].start()
    brace = matches[0].end() - 1
    end = _balanced_end(text, brace, "{", "}")
    return _normalize_source(text[start:end])


def _extract_boon(text: str) -> int:
    matches = tuple(re.finditer(r"\bvar\s+BOON\s*=\s*(-?[0-9]+)\s*;", text))
    if len(matches) != 1:
        raise WonderbaneCalculatorImportError(
            "expected exactly one integer calculator BOON declaration"
        )
    return int(matches[0].group(1))


def _balanced_end(text: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    index = start
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char in "\r\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 2
            else:
                index += 1
            continue
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'":
            quote = char
            index += 1
            continue
        if char == "/" and next_char == "/":
            line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            block_comment = True
            index += 2
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise WonderbaneCalculatorImportError("calculator declaration is not balanced")


def _normalize_source(source: str) -> str:
    return "\n".join(line.rstrip() for line in source.replace("\r\n", "\n").split("\n")).strip()


def _parse_race(value: object) -> CalculatorRace:
    data = _mapping(value, "race")
    _exact_fields(
        data,
        {"id", "name", "start", "max", "sp", "hb", "mb", "sb"},
        field_name="race",
    )
    name = _required_string(data, "name")
    match = re.fullmatch(r"(.+), (Male|Female)", name)
    if match is None:
        raise WonderbaneCalculatorImportError(
            f"race name must contain a family and sex: {name}"
        )
    return CalculatorRace(
        record_id=_integer(data["id"], "race id", minimum=1),
        name=name,
        family=match.group(1),
        sex=match.group(2).lower(),
        starting_attributes=_stats(data["start"], "race starting attributes"),
        maximum_attributes=_stats(data["max"], "race maximum attributes"),
        creation_points=_integer(data["sp"], "race creation points", minimum=0),
        health_base=_integer(data["hb"], "race health base", minimum=0),
        mana_base=_integer(data["mb"], "race mana base", minimum=0),
        stamina_base=_integer(data["sb"], "race stamina base", minimum=0),
    )


def _parse_base(value: object) -> CalculatorClass:
    data = _mapping(value, "base class")
    _exact_fields(
        data,
        {"id", "name", "mod", "hb", "mb", "sb"},
        field_name="base class",
    )
    return CalculatorClass(
        record_id=_integer(data["id"], "base class id", minimum=1),
        name=_required_string(data, "name"),
        allowed_base_classes=(),
        attribute_modifiers=_stats(data["mod"], "base class modifiers"),
        health_growth=_integer(data["hb"], "base class health growth", minimum=0),
        mana_growth=_integer(data["mb"], "base class mana growth", minimum=0),
        stamina_growth=_integer(data["sb"], "base class stamina growth", minimum=0),
    )


def _parse_promotion(value: object) -> CalculatorClass:
    data = _mapping(value, "promotion")
    _exact_fields(
        data,
        {"id", "name", "bases", "hb", "mb", "sb"},
        field_name="promotion",
    )
    return CalculatorClass(
        record_id=_integer(data["id"], "promotion id", minimum=0),
        name=_required_string(data, "name"),
        allowed_base_classes=_strings(data["bases"], "promotion base classes"),
        attribute_modifiers=StatLine(0, 0, 0, 0, 0),
        health_growth=_integer(data["hb"], "promotion health growth", minimum=0),
        mana_growth=_integer(data["mb"], "promotion mana growth", minimum=0),
        stamina_growth=_integer(data["sb"], "promotion stamina growth", minimum=0),
    )


def _parse_rune(value: object) -> CalculatorRune:
    data = _mapping(value, "rune")
    _exact_fields(
        data,
        {
            "id",
            "name",
            "cost",
            "stats",
            "caps",
            "mins",
            "races",
            "classes",
            "promos",
            "level",
            "kind",
        },
        optional={"desc", "powers", "skills"},
        field_name="rune",
    )
    record_id = _integer(data["id"], "rune id", minimum=1)
    source_kind = _required_string(data, "kind")
    if source_kind not in {"disc", "stat"}:
        raise WonderbaneCalculatorImportError(f"unsupported rune kind: {source_kind}")
    if source_kind == "disc":
        category = CalculatorRuneCategory.DISCIPLINE
    elif 250000 <= record_id <= 250044:
        category = CalculatorRuneCategory.STAT_TIER
    else:
        category = CalculatorRuneCategory.STARTING
    description = data.get("desc")
    if description is not None and (not isinstance(description, str) or not description.strip()):
        raise WonderbaneCalculatorImportError("rune description must be a non-empty string")
    skill_grants: list[CalculatorSkillGrant] = []
    for value in _array(data.get("skills", []), "rune skills"):
        skill = _mapping(value, "rune skill")
        _exact_fields(skill, {"n", "a"}, field_name="rune skill")
        skill_grants.append(
            CalculatorSkillGrant(
                name=_required_string(skill, "n"),
                amount=_integer(skill["a"], "rune skill amount", minimum=0),
            )
        )
    return CalculatorRune(
        record_id=record_id,
        name=_required_string(data, "name"),
        category=category,
        source_kind=source_kind,
        cost=_integer(data["cost"], "rune cost", minimum=0),
        minimum_level=_integer(data["level"], "rune minimum level", minimum=0),
        stat_grants=_stats(data["stats"], "rune stat grants"),
        cap_grants=_stats(data["caps"], "rune cap grants"),
        minimum_stats=_stats(data["mins"], "rune minimum stats"),
        allowed_races=_strings(data["races"], "rune races"),
        allowed_base_classes=_strings(data["classes"], "rune base classes"),
        allowed_promotions=_strings(data["promos"], "rune promotions"),
        description=description,
        powers=_strings(data.get("powers", []), "rune powers"),
        skill_grants=tuple(skill_grants),
    )


def _unresolved_references(
    races: tuple[CalculatorRace, ...],
    bases: tuple[CalculatorClass, ...],
    promotions: tuple[CalculatorClass, ...],
    runes: tuple[CalculatorRune, ...],
) -> tuple[str, ...]:
    race_names = {item.family for item in races}
    base_names = {item.name for item in bases}
    promotion_names = {item.name for item in promotions}
    unresolved: set[str] = set()
    for promotion in promotions:
        for name in set(promotion.allowed_base_classes) - base_names:
            unresolved.add(f"promotion:{promotion.name}:base_class:{name}")
    for rune in runes:
        for name in set(rune.allowed_races) - race_names:
            unresolved.add(f"rune:{rune.record_id}:race:{name}")
        for name in set(rune.allowed_base_classes) - base_names:
            unresolved.add(f"rune:{rune.record_id}:base_class:{name}")
        for name in set(rune.allowed_promotions) - promotion_names:
            unresolved.add(f"rune:{rune.record_id}:promotion:{name}")
    return tuple(sorted(unresolved))


def _validate_rune_access(
    rune: CalculatorRune,
    race: CalculatorRace,
    base: CalculatorClass,
    promotion: CalculatorClass | None,
    level: int,
    attributes_before_runes: StatLine,
) -> None:
    if rune.allowed_races and race.family not in rune.allowed_races:
        raise WonderbaneCalculatorImportError(
            f"{rune.name} is not available to {race.family}"
        )
    if rune.allowed_base_classes and base.name not in rune.allowed_base_classes:
        raise WonderbaneCalculatorImportError(
            f"{rune.name} is not available to {base.name}"
        )
    if rune.allowed_promotions and (
        promotion is None or promotion.name not in rune.allowed_promotions
    ):
        raise WonderbaneCalculatorImportError(
            f"{rune.name} is not available to the selected promotion"
        )
    if rune.minimum_level and level < rune.minimum_level:
        raise WonderbaneCalculatorImportError(
            f"{rune.name} requires level {rune.minimum_level}"
        )
    if any(
        actual < required
        for actual, required in zip(
            attributes_before_runes.values(), rune.minimum_stats.values(), strict=True
        )
    ):
        raise WonderbaneCalculatorImportError(
            f"{rune.name} minimum stats are not satisfied before runes"
        )


def _level_bonus(level: int) -> int:
    if level < 20:
        return (level - 1) * 5
    if level < 30:
        return 90 + (level - 19) * 4
    if level < 40:
        return 130 + (level - 29) * 3
    if level < 50:
        return 160 + (level - 39) * 2
    return 180 + (level - 49)


def _growth_factors(level: int, has_promotion: bool) -> tuple[float, float]:
    if level < 10 or not has_promotion:
        return float(level), 0.0
    if level < 20:
        return float(level), float(level - 9)
    if level < 30:
        return 19 + (level - 19) * 0.8, 10 + (level - 19) * 0.8
    if level < 40:
        return 27 + (level - 29) * 0.6, 18 + (level - 29) * 0.6
    if level < 50:
        return 33 + (level - 39) * 0.4, 24 + (level - 39) * 0.4
    if level < 60:
        return 37 + (level - 49) * 0.2, 28 + (level - 49) * 0.2
    return 39 + (level - 59) * 0.1, 30 + (level - 59) * 0.1


def _javascript_round(value: float) -> int:
    return math.floor(value + 0.5)


def _sum_stats(*lines: StatLine) -> StatLine:
    values = tuple(sum(items) for items in zip(*(line.values() for line in lines), strict=True))
    return StatLine(*values)


def _record_by_id(records: tuple[Any, ...], record_id: int, kind: str):
    try:
        return next(item for item in records if item.record_id == record_id)
    except StopIteration as exc:
        raise WonderbaneCalculatorImportError(f"unknown calculator {kind} id: {record_id}") from exc


def _array(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise WonderbaneCalculatorImportError(f"{field_name} must be an array")
    return value


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WonderbaneCalculatorImportError(f"{key} must be a non-empty string")
    return value
