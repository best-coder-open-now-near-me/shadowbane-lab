"""Compile reviewed calculator choices into source-bounded simulation build views."""

from __future__ import annotations

import re
from dataclasses import replace

from shadowbane_lab.composition import (
    BodyValues,
    BuildBlueprint,
    SourcePackage,
    SourcePackageCatalog,
    SourcePackageKind,
    resolve_build_blueprint,
)
from shadowbane_lab.equipment import (
    AffixChoice,
    AffixModifier,
    AffixPosition,
    EquipmentCatalog,
    load_bundled_equipment_catalog,
)
from shadowbane_lab.progression import (
    CalculatorReviewStatus,
    CalculatorRuneCategory,
    StatLine,
    WonderbaneCalculatorCatalog,
    WonderbaneCalculatorImportError,
    load_bundled_wonderbane_calculator_catalog,
)
from shadowbane_lab.rulesets import CharacterBuild, CompilationStatus, CompiledRuleset
from shadowbane_lab.sim import DeterministicRandom

from .build_model import (
    BuildCompilationStatus,
    BuildCoverageReport,
    CompiledLegalBuild,
    EquipmentSelection,
    LegalBuildCompileError,
    LegalBuildCompilePolicy,
    LegalBuildGenome,
    SelectedAffix,
    canonical_digest,
)


class LegalBuildCompiler:
    """Validate a genome while keeping every unproven mechanic explicit."""

    def __init__(
        self,
        calculator: WonderbaneCalculatorCatalog,
        equipment: EquipmentCatalog,
        *,
        ruleset: CompiledRuleset | None = None,
        policy: LegalBuildCompilePolicy = LegalBuildCompilePolicy(),
    ) -> None:
        if not isinstance(calculator, WonderbaneCalculatorCatalog):
            raise LegalBuildCompileError("calculator has the wrong type")
        if calculator.review_status is not CalculatorReviewStatus.ACCEPTED:
            raise LegalBuildCompileError("calculator catalog has not passed review")
        if not isinstance(equipment, EquipmentCatalog):
            raise LegalBuildCompileError("equipment has the wrong type")
        if ruleset is not None and not isinstance(ruleset, CompiledRuleset):
            raise LegalBuildCompileError("ruleset must be CompiledRuleset or null")
        if not isinstance(policy, LegalBuildCompilePolicy):
            raise LegalBuildCompileError("policy has the wrong type")
        self._calculator = calculator
        self._equipment = equipment
        self._ruleset = ruleset
        self._policy = policy
        self._modifiers = {
            (modifier.table_id, modifier.action_id): modifier
            for modifier in equipment.modifiers
        }

    @classmethod
    def bundled(
        cls,
        *,
        ruleset: CompiledRuleset | None = None,
        policy: LegalBuildCompilePolicy = LegalBuildCompilePolicy(),
    ) -> LegalBuildCompiler:
        return cls(
            load_bundled_wonderbane_calculator_catalog(),
            load_bundled_equipment_catalog(),
            ruleset=ruleset,
            policy=policy,
        )

    @property
    def policy(self) -> LegalBuildCompilePolicy:
        return self._policy

    def compile(self, genome: LegalBuildGenome) -> CompiledLegalBuild:
        if not isinstance(genome, LegalBuildGenome):
            raise LegalBuildCompileError("genome must be LegalBuildGenome")
        try:
            output = self._calculator.calculate(
                race_id=genome.race_id,
                base_class_id=genome.base_class_id,
                promotion_id=genome.promotion_id,
                level=genome.level,
                trained_modifiers=genome.trained_modifiers,
                rune_ids=genome.rune_ids,
            )
        except WonderbaneCalculatorImportError as exc:
            raise LegalBuildCompileError(f"calculator rejected build: {exc}") from exc
        if any(
            actual > maximum
            for actual, maximum in zip(
                output.attributes.values(),
                output.attribute_caps.values(),
                strict=True,
            )
        ):
            raise LegalBuildCompileError("calculator output exceeds an attribute cap")

        race = self._calculator.race(genome.race_id)
        base = self._calculator.base_class(genome.base_class_id)
        promotion = (
            None
            if genome.promotion_id is None
            else self._calculator.promotion(genome.promotion_id)
        )
        runes = tuple(self._calculator.rune(rune_id) for rune_id in genome.rune_ids)
        profession = _semantic_key((promotion or base).name)
        character_build = CharacterBuild(
            profession=profession,
            level=genome.level,
            skill_ranks=tuple(sorted(genome.skill_ranks)),
            power_ranks=tuple(sorted(genome.power_ranks)),
            enabled_power_keys=tuple(sorted(key for key, _ in genome.power_ranks)),
        )

        unresolved: set[str] = set()
        assumptions: set[str] = set()
        requested_actions, accepted_actions, available_triggers = self._actions(
            character_build,
            unresolved,
            assumptions,
        )
        packages = list(self._identity_packages(genome, race.name, base.name, promotion))
        requested_package_ids = [package.package_id for package in packages]

        for rune in runes:
            package = SourcePackage(
                package_id=f"calculator.rune.{rune.record_id}",
                display_name=rune.name,
                kind=(
                    SourcePackageKind.DISCIPLINE
                    if rune.category is CalculatorRuneCategory.DISCIPLINE
                    else SourcePackageKind.STAT_RUNE
                ),
                selection_slot=(
                    "discipline"
                    if rune.category is CalculatorRuneCategory.DISCIPLINE
                    else "rune"
                ),
                metadata=(
                    ("calculator_category", rune.category.value),
                    ("source_kind", rune.source_kind),
                ),
            )
            packages.append(package)
            requested_package_ids.append(package.package_id)

        training = tuple(
            sorted(
                (
                    *((f"skill.{key}", float(rank)) for key, rank in genome.skill_ranks),
                    *((f"power.{key}", float(rank)) for key, rank in genome.power_ranks),
                )
            )
        )
        if training:
            training_package = SourcePackage(
                package_id=f"calculator.training.{profession}",
                display_name=f"{(promotion or base).name} training allocation",
                kind=SourcePackageKind.EXPERIMENTAL,
                training_access_keys=tuple(key for key, _ in training),
                metadata=(("budget_status", "unverified"),),
            )
            packages.append(training_package)
            requested_package_ids.append(training_package.package_id)
            unresolved.add("training.point_budget_unverified")

        equipment_packages = self._equipment_packages(
            genome.equipment,
            unresolved,
            assumptions,
        )
        packages.extend(equipment_packages)
        requested_package_ids.extend(package.package_id for package in equipment_packages)
        catalog = SourcePackageCatalog(
            catalog_id=self._catalog_id(),
            packages=tuple(packages),
            slot_limits=self._slot_limits(genome.equipment),
        )
        blueprint = BuildBlueprint(
            blueprint_id=genome.genome_id,
            display_name=genome.display_name,
            requested_package_ids=tuple(requested_package_ids),
            base_body=BodyValues(
                health=float(output.health),
                mana=float(output.mana),
                stamina=float(output.stamina),
                move_speed=float(genome.move_speed),
            ),
            direct_action_keys=requested_actions,
            base_scalars=(("defense", float(output.defense)),),
            attributes=tuple(
                (name, float(value))
                for name, value in zip(
                    StatLine.names(),
                    output.attributes.values(),
                    strict=True,
                )
            ),
            training=training,
            metadata=(
                ("calculator_race", race.name),
                ("calculator_base_class", base.name),
                ("calculator_promotion", "none" if promotion is None else promotion.name),
                ("genome_digest", genome.genome_digest),
            ),
            notes=(
                "Equipment mechanics require explicit compiler policy.",
                "General training-point legality is not yet sourced.",
            ),
        )
        try:
            view = resolve_build_blueprint(
                catalog,
                blueprint,
                available_action_keys=accepted_actions,
                available_persistent_trigger_keys=available_triggers,
            )
        except ValueError as exc:
            raise LegalBuildCompileError(f"composition rejected build: {exc}") from exc

        coverage = BuildCoverageReport(
            calculator_review_status=self._calculator.review_status.value,
            equipment_catalog_status=self._equipment.status,
            ruleset_id=None if self._ruleset is None else self._ruleset.ruleset_id,
            requested_action_count=len(requested_actions),
            executable_action_count=len(view.executable_action_keys),
            requested_equipment_count=len(genome.equipment),
            candidate_equipment_values_applied=(
                self._policy.apply_candidate_equipment_values and bool(genome.equipment)
            ),
            unresolved=tuple(sorted(unresolved)),
            accepted_assumptions=tuple(sorted(assumptions)),
        )
        status = self._status(coverage)
        if self._policy.require_simulation_ready and (
            status is not BuildCompilationStatus.SIMULATION_READY
        ):
            details = ", ".join((*coverage.unresolved, *coverage.accepted_assumptions))
            suffix = "" if not details else f": {details}"
            raise LegalBuildCompileError(f"build is not strict simulation-ready{suffix}")
        return CompiledLegalBuild(
            status=status,
            genome=genome,
            calculator_output=output,
            character_build=character_build,
            view=view,
            coverage=coverage,
            source_fingerprints=self._source_fingerprints(),
            compile_policy=self._policy,
        )

    def mutate_attributes(
        self,
        parent: LegalBuildGenome,
        random: DeterministicRandom,
        *,
        maximum_attempts: int = 64,
    ) -> LegalBuildGenome:
        """Transfer one trained point and keep only calculator-legal children."""

        if not isinstance(parent, LegalBuildGenome):
            raise LegalBuildCompileError("parent must be LegalBuildGenome")
        if not isinstance(random, DeterministicRandom):
            raise LegalBuildCompileError("random must be DeterministicRandom")
        if (
            isinstance(maximum_attempts, bool)
            or not isinstance(maximum_attempts, int)
            or not 1 <= maximum_attempts <= 10_000
        ):
            raise LegalBuildCompileError("maximum_attempts must be in [1, 10000]")
        self.compile(parent)
        original = parent.trained_modifiers.values()
        for _ in range(maximum_attempts):
            donor = random.randbelow(5)
            recipient = random.randbelow(4)
            if recipient >= donor:
                recipient += 1
            values = list(original)
            values[donor] -= 1
            values[recipient] += 1
            modifiers = StatLine.from_values(tuple(values))
            digest = canonical_digest(
                {"parent": parent.genome_digest, "trained_modifiers": modifiers.as_dict()}
            )
            candidate = replace(
                parent,
                genome_id=f"{parent.genome_id}.mutation.{digest[:12]}",
                trained_modifiers=modifiers,
            )
            try:
                self.compile(candidate)
            except LegalBuildCompileError:
                continue
            return candidate
        return parent

    def _actions(
        self,
        build: CharacterBuild,
        unresolved: set[str],
        assumptions: set[str],
    ) -> tuple[tuple[str, ...], frozenset[str] | None, frozenset[str] | None]:
        if self._ruleset is None:
            unresolved.add("ruleset.not_supplied")
            return (), None, None
        try:
            requested = self._ruleset.action_keys_for(build)
        except ValueError as exc:
            raise LegalBuildCompileError(f"ruleset rejected build: {exc}") from exc
        accepted: set[str] = set()
        for action_key in requested:
            record = self._ruleset.record(action_key)
            if record.status is CompilationStatus.COMPILED:
                accepted.add(action_key)
            elif (
                record.status is CompilationStatus.COMPILED_WITH_OVERRIDE
                and self._policy.allow_ruleset_overrides
            ):
                accepted.add(action_key)
                assumptions.add(f"ruleset.override.{action_key}")
            else:
                unresolved.add(f"ruleset.action.{action_key}.{record.status.value}")
        return requested, frozenset(accepted), frozenset(self._ruleset.catalog.trigger_keys)

    def _identity_packages(self, genome, race_name, base_name, promotion):
        packages = [
            SourcePackage(
                package_id=f"calculator.race.{genome.race_id}",
                display_name=race_name,
                kind=SourcePackageKind.RACE,
                selection_slot="race",
            ),
            SourcePackage(
                package_id=f"calculator.base_class.{genome.base_class_id}",
                display_name=base_name,
                kind=SourcePackageKind.BASE_CLASS,
                selection_slot="base_class",
            ),
        ]
        if promotion is not None:
            packages.append(
                SourcePackage(
                    package_id=f"calculator.promotion.{genome.promotion_id}",
                    display_name=promotion.name,
                    kind=SourcePackageKind.PROMOTION,
                    selection_slot="promotion",
                    requires=(f"calculator.base_class.{genome.base_class_id}",),
                )
            )
        return tuple(packages)

    def _equipment_packages(
        self,
        selections: tuple[EquipmentSelection, ...],
        unresolved: set[str],
        assumptions: set[str],
    ) -> tuple[SourcePackage, ...]:
        packages: list[SourcePackage] = []
        for selection in selections:
            try:
                item = self._equipment.item(selection.item_id)
            except KeyError as exc:
                raise LegalBuildCompileError(f"unknown equipment item {selection.item_id}") from exc
            prefix = self._validate_affix(selection.prefix, AffixPosition.PREFIX)
            suffix = self._validate_affix(selection.suffix, AffixPosition.SUFFIX)
            if not self._equipment.is_valid_affix_pair(
                selection.item_id,
                prefix=None if selection.prefix is None else AffixChoice(
                    selection.prefix.table_id,
                    selection.prefix.action_id,
                ),
                suffix=None if selection.suffix is None else AffixChoice(
                    selection.suffix.table_id,
                    selection.suffix.action_id,
                ),
            ):
                raise LegalBuildCompileError(
                    f"item {selection.item_id} does not permit the selected affix pair"
                )
            path = f"equipment.{selection.slot_key}.{selection.item_id}"
            unresolved.add(f"{path}.slot_semantics_unverified")
            for requirement in item.requirements:
                unresolved.add(f"{path}.requirement.{requirement.kind}.{requirement.token}")
            if item.equip_flags:
                unresolved.add(f"{path}.equip_flags.{item.equip_flags}")
            if item.restrict_flags:
                unresolved.add(f"{path}.restrict_flags.{item.restrict_flags}")
            if not item.current_name_verified:
                unresolved.add(f"{path}.current_name_unverified")
            for position, selected, modifier in (
                ("prefix", selection.prefix, prefix),
                ("suffix", selection.suffix, suffix),
            ):
                if selected is None or modifier is None:
                    continue
                unresolved.add(f"{path}.{position}.effect.{modifier.action_id}")
                if selected.roll is None:
                    unresolved.add(f"{path}.{position}.roll_unresolved")

            scalars: dict[str, float] = {}
            if self._policy.apply_candidate_equipment_values:
                assumptions.add(f"equipment.candidate_values.{selection.slot_key}")
                if item.defense:
                    scalars["defense"] = float(item.defense)
                if selection.slot_key in {"main_hand", "off_hand"} and (
                    item.damage_type is not None
                    and item.maximum_damage > item.minimum_damage
                ):
                    weapon = f"weapon.{selection.slot_key}"
                    scalars[f"{weapon}.damage_min"] = float(item.minimum_damage)
                    scalars[f"{weapon}.damage_max"] = float(item.maximum_damage)
                    scalars[f"{weapon}.delay_ms"] = float(item.speed * 100.0)
                    scalars[f"{weapon}.range"] = float(item.range)
                    unresolved.add(f"{path}.weapon_speed_semantics_candidate")
            else:
                unresolved.add(f"{path}.base_values_not_applied")

            package_digest = canonical_digest(
                {
                    "selection": selection.as_dict(),
                    "equipment_catalog": self._equipment.catalog_id,
                }
            )
            packages.append(
                SourcePackage(
                    package_id=(
                        f"equipment.{selection.slot_key}.{selection.item_id}."
                        f"{package_digest[:12]}"
                    ),
                    display_name=item.name,
                    kind=SourcePackageKind.EQUIPMENT,
                    selection_slot=f"equipment.{selection.slot_key}",
                    scalar_deltas=tuple(sorted(scalars.items())),
                    metadata=(
                        ("damage_type", item.damage_type or "none"),
                        ("historical_name", item.historical_name or item.name),
                        ("item_type", item.item_type),
                    ),
                )
            )
        return tuple(packages)

    def _validate_affix(
        self,
        selection: SelectedAffix | None,
        position: AffixPosition,
    ) -> AffixModifier | None:
        if selection is None:
            return None
        try:
            modifier = self._modifiers[(selection.table_id, selection.action_id)]
        except KeyError as exc:
            raise LegalBuildCompileError(
                f"unknown affix ({selection.table_id}, {selection.action_id})"
            ) from exc
        current_name = (
            modifier.current_prefix_name
            if position is AffixPosition.PREFIX
            else modifier.current_suffix_name
        )
        if current_name is None:
            raise LegalBuildCompileError(f"selected modifier has no current {position.value} name")
        if selection.roll is not None and not (
            modifier.minimum_roll <= selection.roll <= modifier.maximum_roll
        ):
            raise LegalBuildCompileError(
                f"affix roll {selection.roll} is outside "
                f"[{modifier.minimum_roll}, {modifier.maximum_roll}]"
            )
        return modifier

    def _catalog_id(self) -> str:
        return "wonderbane.legal-build.v1." + canonical_digest(
            {
                "calculator": self._calculator.declaration_sha256,
                "equipment": self._equipment.catalog_id,
                "ruleset": "none" if self._ruleset is None else self._ruleset.ruleset_id,
                "policy": self._policy.as_dict(),
            }
        )[:16]

    def _source_fingerprints(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            sorted(
                {
                    "calculator.declaration_sha256": self._calculator.declaration_sha256,
                    "calculator.review_profile_id": self._calculator.review_profile_id,
                    "calculator.snapshot_sha256": self._calculator.snapshot_sha256,
                    "equipment.catalog_id": self._equipment.catalog_id,
                    "equipment.retrieved_on": self._equipment.retrieved_on,
                    "equipment.status": self._equipment.status,
                    "ruleset.id": (
                        "none" if self._ruleset is None else self._ruleset.ruleset_id
                    ),
                }.items()
            )
        )

    @staticmethod
    def _slot_limits(equipment: tuple[EquipmentSelection, ...]):
        limits = {
            "race": 1,
            "base_class": 1,
            "promotion": 1,
            "discipline": 3,
            "rune": 12,
        }
        limits.update({f"equipment.{item.slot_key}": 1 for item in equipment})
        return tuple(sorted(limits.items()))

    def _status(self, coverage: BuildCoverageReport) -> BuildCompilationStatus:
        if self._ruleset is None:
            remaining = tuple(
                item for item in coverage.unresolved if item != "ruleset.not_supplied"
            )
            return (
                BuildCompilationStatus.SOURCE_CANDIDATE
                if remaining or coverage.accepted_assumptions
                else BuildCompilationStatus.CHASSIS_VERIFIED
            )
        if coverage.unresolved or coverage.accepted_assumptions:
            return BuildCompilationStatus.SOURCE_CANDIDATE
        return BuildCompilationStatus.SIMULATION_READY


def _semantic_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    if not normalized:
        raise LegalBuildCompileError("calculator class name has no semantic key")
    return normalized


__all__ = ["LegalBuildCompiler"]
