"""Catalog legality gate enriched with source-pinned training budgets."""

from __future__ import annotations

from dataclasses import dataclass, replace

from shadowbane_lab.equipment import EquipmentCatalog
from shadowbane_lab.progression import WonderbaneCalculatorCatalog

from .build_model import LegalBuildCompileError, LegalBuildGenome
from .training import (
    CatalogBackedLegalityGate,
    CatalogLegalityAudit,
)
from .training_budget import (
    TrainingAllocationAudit,
    TrainingBudgetCatalog,
    load_bundled_training_budget_catalog,
)


@dataclass(frozen=True, slots=True)
class TrainingCatalogLegalityAudit(CatalogLegalityAudit):
    """Existing equipment audit plus typed training-budget evidence."""

    training_allocation: TrainingAllocationAudit

    def __post_init__(self) -> None:
        if not isinstance(self.training_allocation, TrainingAllocationAudit):
            raise LegalBuildCompileError("training_allocation has the wrong type")

    def as_dict(self) -> dict[str, object]:
        payload = CatalogLegalityAudit.as_dict(self)
        payload["training_allocation"] = self.training_allocation.as_dict()
        payload["power_budget_scope"] = (
            "source-pinned earned budget with conservative rank-cost lower bounds"
        )
        return payload


class TrainingBudgetBackedLegalityGate(CatalogBackedLegalityGate):
    """Keep equipment checks while replacing the legacy Rogue-only budget shortcut."""

    def __init__(
        self,
        calculator: WonderbaneCalculatorCatalog,
        equipment: EquipmentCatalog,
        *,
        budgets: TrainingBudgetCatalog | None = None,
        skill_aliases: tuple[tuple[str, str], ...] = (
            ("unarmed", "unarmed_combat"),
            ("unarmed_combat", "unarmed"),
        ),
    ) -> None:
        super().__init__(
            calculator,
            equipment,
            skill_aliases=skill_aliases,
        )
        if budgets is None:
            budgets = load_bundled_training_budget_catalog()
        if not isinstance(budgets, TrainingBudgetCatalog):
            raise LegalBuildCompileError("budgets has the wrong type")
        self._training_calculator = calculator
        self._training_budgets = budgets

    @property
    def training_budgets(self) -> TrainingBudgetCatalog:
        return self._training_budgets

    def audit(self, genome: LegalBuildGenome) -> TrainingCatalogLegalityAudit:
        if not isinstance(genome, LegalBuildGenome):
            raise LegalBuildCompileError("genome must be LegalBuildGenome")
        race = self._training_calculator.race(genome.race_id)
        base = self._training_calculator.base_class(genome.base_class_id)
        training = self._training_budgets.audit(
            race_family=race.family,
            base_class_name=base.name,
            level=genome.level,
            skill_ranks=genome.skill_ranks,
            power_ranks=genome.power_ranks,
        )

        # The legacy gate owns the equipment checks but also contains an older
        # unconditional Rogue shortcut. Strip powers only for that call, then
        # restore the typed audit below. This prevents Human Rogue or unsupported
        # identities from inheriting a non-Human budget by accident.
        equipment_audit = super().audit(replace(genome, power_ranks=()))
        if training.lower_bound_overspent:
            assert training.budget_points is not None
            raise LegalBuildCompileError(
                f"selected ranks require at least {training.minimum_points_spent} "
                f"training points, but {training.budget_profile_id} supplies only "
                f"{training.budget_points} at level {genome.level}"
            )
        return TrainingCatalogLegalityAudit(
            base_class_name=equipment_audit.base_class_name,
            power_rank_points=sum(rank for _, rank in genome.power_ranks),
            known_power_training_budget=training.budget_points,
            equipment_skill_requirements=equipment_audit.equipment_skill_requirements,
            opaque_item_requirement_count=equipment_audit.opaque_item_requirement_count,
            unresolved_skill_cost_keys=training.unresolved_skill_cost_keys,
            training_allocation=training,
        )


__all__ = [
    "TrainingBudgetBackedLegalityGate",
    "TrainingCatalogLegalityAudit",
]
