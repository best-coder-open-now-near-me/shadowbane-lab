"""Versioned identity catalog for build-permutation simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shadowbane_lab.progression.model import SourceReference, StatLine


def _identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _unique_identifiers(values: tuple[str, ...], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    for value in values:
        _identifier(value, field_name)


class CatalogVariantStatus(StrEnum):
    """How directly a catalog represents the target ruleset variant."""

    LEGACY_BASELINE = "legacy_baseline"
    WONDERBANE_VERIFIED = "wonderbane_verified"


class CoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"


class CharacterSex(StrEnum):
    FEMALE = "female"
    MALE = "male"


ALL_CHARACTER_SEXES = (CharacterSex.FEMALE, CharacterSex.MALE)


@dataclass(frozen=True, slots=True)
class CoverageEntry:
    domain: str
    status: CoverageStatus
    note: str

    def __post_init__(self) -> None:
        _identifier(self.domain, "coverage domain")
        if not isinstance(self.status, CoverageStatus):
            raise ValueError("coverage status must be a CoverageStatus")
        _identifier(self.note, "coverage note")


@dataclass(frozen=True, slots=True)
class BaseClassProfile:
    key: str
    name: str
    source_id: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.key, "base class key"),
            (self.name, "base class name"),
            (self.source_id, "base class source id"),
        ):
            _identifier(value, field_name)


@dataclass(frozen=True, slots=True)
class RaceProfile:
    key: str
    name: str
    creation_cost: int
    starting_attributes: StatLine
    maximum_attributes: StatLine
    allowed_base_class_keys: tuple[str, ...]
    racial_discipline_keys: tuple[str, ...]
    allowed_sexes: tuple[CharacterSex, ...]
    source_id: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.key, "race key"),
            (self.name, "race name"),
            (self.source_id, "race source id"),
        ):
            _identifier(value, field_name)
        if (
            isinstance(self.creation_cost, bool)
            or not isinstance(self.creation_cost, int)
            or self.creation_cost < 0
        ):
            raise ValueError("race creation cost must be a non-negative integer")
        if not isinstance(self.starting_attributes, StatLine) or not isinstance(
            self.maximum_attributes, StatLine
        ):
            raise ValueError("race attributes must be StatLine values")
        for starting, maximum in zip(
            self.starting_attributes.values(), self.maximum_attributes.values(), strict=True
        ):
            if starting > maximum:
                raise ValueError("race starting attributes must not exceed their maxima")
        if not self.allowed_base_class_keys:
            raise ValueError("races require at least one allowed base class")
        _unique_identifiers(self.allowed_base_class_keys, "allowed base class key")
        _unique_identifiers(self.racial_discipline_keys, "racial discipline key")
        if not self.allowed_sexes:
            raise ValueError("races require at least one allowed sex")
        if len(self.allowed_sexes) != len(set(self.allowed_sexes)):
            raise ValueError("race allowed sexes must not contain duplicates")
        if any(not isinstance(value, CharacterSex) for value in self.allowed_sexes):
            raise ValueError("race allowed sexes must contain CharacterSex values")


@dataclass(frozen=True, slots=True)
class ProfessionProfile:
    key: str
    name: str
    promotion_level: int
    allowed_base_class_keys: tuple[str, ...]
    allowed_race_keys: tuple[str, ...]
    allowed_sexes: tuple[CharacterSex, ...]
    source_id: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.key, "profession key"),
            (self.name, "profession name"),
            (self.source_id, "profession source id"),
        ):
            _identifier(value, field_name)
        if (
            isinstance(self.promotion_level, bool)
            or not isinstance(self.promotion_level, int)
            or self.promotion_level < 1
        ):
            raise ValueError("profession promotion level must be a positive integer")
        if not self.allowed_base_class_keys or not self.allowed_race_keys:
            raise ValueError("professions require allowed base classes and races")
        _unique_identifiers(self.allowed_base_class_keys, "profession base class key")
        _unique_identifiers(self.allowed_race_keys, "profession race key")
        if not self.allowed_sexes:
            raise ValueError("professions require at least one allowed sex")
        if len(self.allowed_sexes) != len(set(self.allowed_sexes)):
            raise ValueError("profession allowed sexes must not contain duplicates")
        if any(not isinstance(value, CharacterSex) for value in self.allowed_sexes):
            raise ValueError("profession allowed sexes must contain CharacterSex values")


@dataclass(frozen=True, slots=True)
class DisciplineProfile:
    key: str
    name: str
    racial_access_keys: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.key, "discipline key"),
            (self.name, "discipline name"),
            (self.source_id, "discipline source id"),
        ):
            _identifier(value, field_name)
        _unique_identifiers(self.racial_access_keys, "discipline racial access key")


@dataclass(frozen=True, slots=True)
class CoreBuildIdentity:
    race_key: str
    base_class_key: str
    profession_key: str
    sex: CharacterSex

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.race_key, "build race key"),
            (self.base_class_key, "build base class key"),
            (self.profession_key, "build profession key"),
        ):
            _identifier(value, field_name)
        if not isinstance(self.sex, CharacterSex):
            raise ValueError("build sex must be a CharacterSex")


class IllegalCoreBuildError(ValueError):
    """Raised when a race/base-class/profession/sex combination is illegal."""


@dataclass(frozen=True, slots=True)
class GameCatalog:
    catalog_id: str
    target_variant: str
    variant_status: CatalogVariantStatus
    retrieved_on: str
    sources: tuple[SourceReference, ...]
    coverage: tuple[CoverageEntry, ...]
    base_classes: tuple[BaseClassProfile, ...]
    races: tuple[RaceProfile, ...]
    professions: tuple[ProfessionProfile, ...]
    disciplines: tuple[DisciplineProfile, ...]

    def __post_init__(self) -> None:
        _identifier(self.catalog_id, "catalog id")
        _identifier(self.target_variant, "target variant")
        _identifier(self.retrieved_on, "catalog retrieval date")
        if not isinstance(self.variant_status, CatalogVariantStatus):
            raise ValueError("variant status must be a CatalogVariantStatus")

        source_ids = self._unique_keys(self.sources, "source")
        coverage_domains = tuple(item.domain for item in self.coverage)
        _unique_identifiers(coverage_domains, "coverage domain")
        base_class_keys = self._unique_keys(self.base_classes, "base class")
        race_keys = self._unique_keys(self.races, "race")
        self._unique_keys(self.professions, "profession")
        discipline_keys = self._unique_keys(self.disciplines, "discipline")

        for record_group, group_name in (
            (self.base_classes, "base class"),
            (self.races, "race"),
            (self.professions, "profession"),
            (self.disciplines, "discipline"),
        ):
            for record in record_group:
                if record.source_id not in source_ids:
                    raise ValueError(f"{group_name} references unknown source {record.source_id}")

        for race in self.races:
            self._require_known(
                race.allowed_base_class_keys, base_class_keys, f"race {race.key} base classes"
            )
            self._require_known(
                race.racial_discipline_keys,
                discipline_keys,
                f"race {race.key} racial disciplines",
            )
        for profession in self.professions:
            self._require_known(
                profession.allowed_base_class_keys,
                base_class_keys,
                f"profession {profession.key} base classes",
            )
            self._require_known(
                profession.allowed_race_keys,
                race_keys,
                f"profession {profession.key} races",
            )
            for race_key in profession.allowed_race_keys:
                race = self.race(race_key)
                if not set(race.allowed_base_class_keys).intersection(
                    profession.allowed_base_class_keys
                ):
                    raise ValueError(
                        f"profession {profession.key} has no legal base class for race {race_key}"
                    )
        for discipline in self.disciplines:
            self._require_known(
                discipline.racial_access_keys,
                race_keys,
                f"discipline {discipline.key} racial access",
            )

        racial_access = {
            (race_key, discipline.key)
            for discipline in self.disciplines
            for race_key in discipline.racial_access_keys
        }
        racial_grants = {
            (race.key, discipline_key)
            for race in self.races
            for discipline_key in race.racial_discipline_keys
        }
        if racial_access != racial_grants:
            raise ValueError("race and discipline racial access declarations must agree")

        if not self.legal_core_builds():
            raise ValueError("catalog must contain at least one legal core build")

    def base_class(self, key: str) -> BaseClassProfile:
        return self._by_key(self.base_classes, key, "base class")

    def race(self, key: str) -> RaceProfile:
        return self._by_key(self.races, key, "race")

    def profession(self, key: str) -> ProfessionProfile:
        return self._by_key(self.professions, key, "profession")

    def discipline(self, key: str) -> DisciplineProfile:
        return self._by_key(self.disciplines, key, "discipline")

    def coverage_for(self, domain: str) -> CoverageEntry:
        return self._by_key(self.coverage, domain, "coverage domain", key_attribute="domain")

    def validate_core_build(self, build: CoreBuildIdentity) -> CoreBuildIdentity:
        if not isinstance(build, CoreBuildIdentity):
            raise ValueError("build must be a CoreBuildIdentity")
        try:
            race = self.race(build.race_key)
            self.base_class(build.base_class_key)
            profession = self.profession(build.profession_key)
        except KeyError as exc:
            raise IllegalCoreBuildError(str(exc)) from exc
        if build.base_class_key not in race.allowed_base_class_keys:
            raise IllegalCoreBuildError(
                f"{race.name} cannot select base class {build.base_class_key}"
            )
        if build.race_key not in profession.allowed_race_keys:
            raise IllegalCoreBuildError(
                f"{race.name} cannot promote to {profession.name}"
            )
        if build.base_class_key not in profession.allowed_base_class_keys:
            raise IllegalCoreBuildError(
                f"{profession.name} cannot promote from {build.base_class_key}"
            )
        if build.sex not in race.allowed_sexes:
            raise IllegalCoreBuildError(f"{race.name} does not allow sex {build.sex.value}")
        if build.sex not in profession.allowed_sexes:
            raise IllegalCoreBuildError(
                f"{profession.name} does not allow sex {build.sex.value}"
            )
        return build

    def legal_core_builds(self) -> tuple[CoreBuildIdentity, ...]:
        builds: list[CoreBuildIdentity] = []
        for race in self.races:
            for profession in self.professions:
                if race.key not in profession.allowed_race_keys:
                    continue
                for base_class_key in race.allowed_base_class_keys:
                    if base_class_key not in profession.allowed_base_class_keys:
                        continue
                    for sex in race.allowed_sexes:
                        if sex in profession.allowed_sexes:
                            builds.append(
                                CoreBuildIdentity(
                                    race_key=race.key,
                                    base_class_key=base_class_key,
                                    profession_key=profession.key,
                                    sex=sex,
                                )
                            )
        return tuple(
            sorted(
                builds,
                key=lambda item: (
                    item.race_key,
                    item.base_class_key,
                    item.profession_key,
                    item.sex.value,
                ),
            )
        )

    @staticmethod
    def _unique_keys(records: tuple[object, ...], kind: str) -> set[str]:
        keys = tuple(
            record.key if hasattr(record, "key") else record.source_id
            for record in records
        )
        _unique_identifiers(keys, f"{kind} key")
        return set(keys)

    @staticmethod
    def _require_known(values: tuple[str, ...], known: set[str], field_name: str) -> None:
        unknown = set(values) - known
        if unknown:
            raise ValueError(f"{field_name} contain unknown keys: {', '.join(sorted(unknown))}")

    @staticmethod
    def _by_key(records, key: str, kind: str, *, key_attribute: str = "key"):
        try:
            return next(item for item in records if getattr(item, key_attribute) == key)
        except StopIteration as exc:
            raise KeyError(f"unknown {kind}: {key}") from exc
