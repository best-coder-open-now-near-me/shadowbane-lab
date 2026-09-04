"""Calculator-authoritative attribute allocation and rune-repair search."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace

from shadowbane_lab.progression import (
    CalculatorBuildOutput,
    CalculatorReviewStatus,
    StatLine,
    WonderbaneCalculatorCatalog,
    WonderbaneCalculatorImportError,
)
from shadowbane_lab.sim import DeterministicRandom

from .build_compiler import LegalBuildCompiler
from .build_model import LegalBuildCompileError, LegalBuildGenome, canonical_digest
from .training import (
    CatalogBackedLegalityGate,
    CompilerBackedGenomeMutator,
    genome_mechanical_digest,
)

_OPERATION_ORDER = {"spend": 0, "transfer": 1, "refund": 2}


@dataclass(frozen=True, slots=True)
class CalculatorAllocation:
    """One reviewed calculator result bound to its exact trained allocation."""

    trained_modifiers: StatLine
    attributes: StatLine
    attribute_caps: StatLine
    creation_points: int
    level_points: int
    trained_points: int
    rune_cost: int
    available_points: int
    health: int
    mana: int
    stamina: int
    defense: int
    calculator_declaration_sha256: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.trained_modifiers, "trained_modifiers"),
            (self.attributes, "attributes"),
            (self.attribute_caps, "attribute_caps"),
        ):
            if not isinstance(value, StatLine):
                raise LegalBuildCompileError(f"{field_name} must be StatLine")
        for field_name in (
            "creation_points",
            "level_points",
            "trained_points",
            "rune_cost",
            "available_points",
            "health",
            "mana",
            "stamina",
            "defense",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise LegalBuildCompileError(f"{field_name} must be an integer")
        if self.creation_points < 0 or self.level_points < 0 or self.rune_cost < 0:
            raise LegalBuildCompileError("calculator point pools and rune cost cannot be negative")
        if self.available_points < 0:
            raise LegalBuildCompileError("available_points cannot be negative")
        if any(value < 0 for value in (self.health, self.mana, self.stamina, self.defense)):
            raise LegalBuildCompileError("calculator resources and defense cannot be negative")
        if (
            not isinstance(self.calculator_declaration_sha256, str)
            or len(self.calculator_declaration_sha256) != 64
        ):
            raise LegalBuildCompileError(
                "calculator_declaration_sha256 must be a SHA-256 string"
            )

    @property
    def point_pool(self) -> int:
        return self.creation_points + self.level_points

    @property
    def fully_allocated(self) -> bool:
        return self.available_points == 0

    @property
    def allocation_digest(self) -> str:
        return canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "trained_modifiers": self.trained_modifiers.as_dict(),
            "attributes": self.attributes.as_dict(),
            "attribute_caps": self.attribute_caps.as_dict(),
            "creation_points": self.creation_points,
            "level_points": self.level_points,
            "point_pool": self.point_pool,
            "trained_points": self.trained_points,
            "rune_cost": self.rune_cost,
            "available_points": self.available_points,
            "fully_allocated": self.fully_allocated,
            "health": self.health,
            "mana": self.mana,
            "stamina": self.stamina,
            "defense": self.defense,
            "calculator_declaration_sha256": self.calculator_declaration_sha256,
        }


@dataclass(frozen=True, slots=True)
class CalculatorAllocationNeighbor:
    """One legal one-point transition in calculator allocation space."""

    operation: str
    donor_index: int | None
    recipient_index: int | None
    genome: LegalBuildGenome
    allocation: CalculatorAllocation

    def __post_init__(self) -> None:
        if self.operation not in _OPERATION_ORDER:
            raise LegalBuildCompileError(f"unknown allocation operation {self.operation}")
        for value, field_name in (
            (self.donor_index, "donor_index"),
            (self.recipient_index, "recipient_index"),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 5
            ):
                raise LegalBuildCompileError(f"{field_name} must be null or a stat index")
        if not isinstance(self.genome, LegalBuildGenome):
            raise LegalBuildCompileError("neighbor genome must be LegalBuildGenome")
        if not isinstance(self.allocation, CalculatorAllocation):
            raise LegalBuildCompileError("neighbor allocation must be CalculatorAllocation")

    @property
    def donor(self) -> str | None:
        return None if self.donor_index is None else StatLine.names()[self.donor_index]

    @property
    def recipient(self) -> str | None:
        return (
            None
            if self.recipient_index is None
            else StatLine.names()[self.recipient_index]
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "donor": self.donor,
            "recipient": self.recipient,
            "genome_mechanical_digest": genome_mechanical_digest(self.genome),
            "allocation": self.allocation.as_dict(),
        }


class CalculatorAllocationSpace:
    """Enumerate and repair build allocations using only the reviewed calculator."""

    def __init__(self, calculator: WonderbaneCalculatorCatalog) -> None:
        if not isinstance(calculator, WonderbaneCalculatorCatalog):
            raise LegalBuildCompileError("calculator has the wrong type")
        if calculator.review_status is not CalculatorReviewStatus.ACCEPTED:
            raise LegalBuildCompileError("calculator catalog has not passed review")
        self._calculator = calculator

    @property
    def calculator(self) -> WonderbaneCalculatorCatalog:
        return self._calculator

    def evaluate(self, genome: LegalBuildGenome) -> CalculatorAllocation:
        """Compile one allocation and reject final post-rune cap overflow."""

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
            raise LegalBuildCompileError(f"calculator rejected allocation: {exc}") from exc
        if any(
            actual > maximum
            for actual, maximum in zip(
                output.attributes.values(),
                output.attribute_caps.values(),
                strict=True,
            )
        ):
            raise LegalBuildCompileError(
                "calculator allocation exceeds a final post-rune attribute cap"
            )
        return self._receipt(genome.trained_modifiers, output)

    def legal_neighbors(
        self,
        genome: LegalBuildGenome,
        *,
        include_spend: bool = True,
        include_transfer: bool = True,
        include_refund: bool = False,
    ) -> tuple[CalculatorAllocationNeighbor, ...]:
        """Return every legal one-point allocation transition in stable order."""

        for value, field_name in (
            (include_spend, "include_spend"),
            (include_transfer, "include_transfer"),
            (include_refund, "include_refund"),
        ):
            if not isinstance(value, bool):
                raise LegalBuildCompileError(f"{field_name} must be a boolean")
        current = self.evaluate(genome)
        values = genome.trained_modifiers.values()
        neighbors: list[CalculatorAllocationNeighbor] = []

        if include_spend and current.available_points > 0:
            for recipient in range(5):
                trial = list(values)
                trial[recipient] += 1
                neighbor = self._neighbor(
                    genome,
                    "spend",
                    None,
                    recipient,
                    StatLine.from_values(tuple(trial)),
                )
                if neighbor is not None:
                    neighbors.append(neighbor)

        if include_transfer:
            for donor in range(5):
                if values[donor] <= -5:
                    continue
                for recipient in range(5):
                    if recipient == donor:
                        continue
                    trial = list(values)
                    trial[donor] -= 1
                    trial[recipient] += 1
                    neighbor = self._neighbor(
                        genome,
                        "transfer",
                        donor,
                        recipient,
                        StatLine.from_values(tuple(trial)),
                    )
                    if neighbor is not None:
                        neighbors.append(neighbor)

        if include_refund:
            for donor in range(5):
                if values[donor] <= -5:
                    continue
                trial = list(values)
                trial[donor] -= 1
                neighbor = self._neighbor(
                    genome,
                    "refund",
                    donor,
                    None,
                    StatLine.from_values(tuple(trial)),
                )
                if neighbor is not None:
                    neighbors.append(neighbor)

        unique: dict[str, CalculatorAllocationNeighbor] = {}
        for neighbor in neighbors:
            unique.setdefault(genome_mechanical_digest(neighbor.genome), neighbor)
        return tuple(
            sorted(
                unique.values(),
                key=lambda item: (
                    _OPERATION_ORDER[item.operation],
                    -1 if item.donor_index is None else item.donor_index,
                    -1 if item.recipient_index is None else item.recipient_index,
                    item.allocation.allocation_digest,
                ),
            )
        )

    def mutate(
        self,
        genome: LegalBuildGenome,
        random: DeterministicRandom,
        *,
        include_refund: bool = False,
    ) -> LegalBuildGenome | None:
        """Select one deterministic random calculator-legal neighbor."""

        if not isinstance(random, DeterministicRandom):
            raise LegalBuildCompileError("random must be DeterministicRandom")
        neighbors = self.legal_neighbors(
            genome,
            include_spend=True,
            include_transfer=True,
            include_refund=include_refund,
        )
        if not neighbors:
            return None
        return neighbors[random.randbelow(len(neighbors))].genome

    def fill(
        self,
        genome: LegalBuildGenome,
        random: DeterministicRandom,
    ) -> LegalBuildGenome:
        """Spend every point that has at least one calculator-legal destination."""

        if not isinstance(random, DeterministicRandom):
            raise LegalBuildCompileError("random must be DeterministicRandom")
        current = genome
        while True:
            receipt = self.evaluate(current)
            if receipt.available_points == 0:
                return current
            choices = self.legal_neighbors(
                current,
                include_spend=True,
                include_transfer=False,
                include_refund=False,
            )
            if not choices:
                return current
            current = choices[random.randbelow(len(choices))].genome

    def repair_runes(
        self,
        genome: LegalBuildGenome,
        rune_ids: tuple[int, ...],
        random: DeterministicRandom,
        *,
        fill_available: bool = True,
    ) -> LegalBuildGenome | None:
        """Rebalance trained points around a changed rune selection.

        Rune costs, pre-rune minimum attributes, the -5 dump floor, pre-rune caps,
        post-rune caps, and the calculator's race/class/promotion access checks all
        remain authoritative. No final attribute value is edited directly.
        """

        if not isinstance(genome, LegalBuildGenome):
            raise LegalBuildCompileError("genome must be LegalBuildGenome")
        if not isinstance(random, DeterministicRandom):
            raise LegalBuildCompileError("random must be DeterministicRandom")
        if not isinstance(fill_available, bool):
            raise LegalBuildCompileError("fill_available must be a boolean")
        selected = tuple(sorted(rune_ids))
        if len(selected) != len(set(selected)):
            raise LegalBuildCompileError("rune_ids must not contain duplicates")
        if len(selected) > 12:
            return None
        try:
            runes = tuple(self._calculator.rune(rune_id) for rune_id in selected)
            current = self.evaluate(genome)
            race = self._calculator.race(genome.race_id)
            base = self._calculator.base_class(genome.base_class_id)
        except (
            KeyError,
            LegalBuildCompileError,
            WonderbaneCalculatorImportError,
        ):
            return None

        base_values = tuple(
            race_value + class_value + self._calculator.formulas.boon
            for race_value, class_value in zip(
                race.starting_attributes.values(),
                base.attribute_modifiers.values(),
                strict=True,
            )
        )
        minimums = [-5, -5, -5, -5, -5]
        for rune in runes:
            minimums = [
                max(current_minimum, required - base_value)
                for current_minimum, required, base_value in zip(
                    minimums,
                    rune.minimum_stats.values(),
                    base_values,
                    strict=True,
                )
            ]
        rune_grants = tuple(
            sum(rune.stat_grants.values()[index] for rune in runes)
            for index in range(5)
        )
        cap_grants = tuple(
            sum(rune.cap_grants.values()[index] for rune in runes)
            for index in range(5)
        )
        maximums = tuple(
            min(
                race.maximum_attributes.values()[index] - base_values[index],
                race.maximum_attributes.values()[index]
                + cap_grants[index]
                - base_values[index]
                - rune_grants[index],
            )
            for index in range(5)
        )
        if any(
            minimum > maximum
            for minimum, maximum in zip(minimums, maximums, strict=True)
        ):
            return None

        rune_cost = sum(rune.cost for rune in runes)
        target_trained = current.point_pool - rune_cost
        if target_trained < sum(minimums):
            return None
        values = list(genome.trained_modifiers.values())
        values = [
            min(max(value, minimum), maximum)
            for value, minimum, maximum in zip(
                values,
                minimums,
                maximums,
                strict=True,
            )
        ]

        while sum(values) > target_trained:
            donors = tuple(
                index for index, value in enumerate(values) if value > minimums[index]
            )
            if not donors:
                return None
            values[donors[random.randbelow(len(donors))]] -= 1

        candidate = replace(
            genome,
            rune_ids=selected,
            trained_modifiers=StatLine.from_values(tuple(values)),
        )
        try:
            self.evaluate(candidate)
        except LegalBuildCompileError:
            return None
        if fill_available:
            candidate = self.fill(candidate, random)
        try:
            self.evaluate(candidate)
        except LegalBuildCompileError:
            return None
        return candidate

    def distinct_variants(
        self,
        genome: LegalBuildGenome,
        *,
        count: int,
        maximum_nodes: int = 10_000,
        fully_allocated_only: bool = True,
    ) -> tuple[LegalBuildGenome, ...]:
        """Breadth-first enumerate mechanically distinct legal allocations."""

        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise LegalBuildCompileError("count must be a positive integer")
        if (
            isinstance(maximum_nodes, bool)
            or not isinstance(maximum_nodes, int)
            or maximum_nodes < count
        ):
            raise LegalBuildCompileError("maximum_nodes must be an integer at least count")
        if not isinstance(fully_allocated_only, bool):
            raise LegalBuildCompileError("fully_allocated_only must be a boolean")
        self.evaluate(genome)
        queue = deque((genome,))
        queued = {genome_mechanical_digest(genome)}
        accepted: list[LegalBuildGenome] = []
        visited = 0
        while queue and visited < maximum_nodes and len(accepted) < count:
            current = queue.popleft()
            visited += 1
            receipt = self.evaluate(current)
            if not fully_allocated_only or receipt.fully_allocated:
                accepted.append(current)
                if len(accepted) == count:
                    break
            neighbors = self.legal_neighbors(
                current,
                include_spend=True,
                include_transfer=True,
                include_refund=not fully_allocated_only,
            )
            for neighbor in neighbors:
                digest = genome_mechanical_digest(neighbor.genome)
                if digest in queued:
                    continue
                queued.add(digest)
                queue.append(neighbor.genome)
        if len(accepted) != count:
            raise LegalBuildCompileError(
                f"found only {len(accepted)} distinct legal allocations; requested {count}"
            )
        return tuple(accepted)

    def _neighbor(
        self,
        genome: LegalBuildGenome,
        operation: str,
        donor: int | None,
        recipient: int | None,
        modifiers: StatLine,
    ) -> CalculatorAllocationNeighbor | None:
        candidate = replace(genome, trained_modifiers=modifiers)
        try:
            allocation = self.evaluate(candidate)
        except LegalBuildCompileError:
            return None
        return CalculatorAllocationNeighbor(
            operation=operation,
            donor_index=donor,
            recipient_index=recipient,
            genome=candidate,
            allocation=allocation,
        )

    def _receipt(
        self,
        trained_modifiers: StatLine,
        output: CalculatorBuildOutput,
    ) -> CalculatorAllocation:
        return CalculatorAllocation(
            trained_modifiers=trained_modifiers,
            attributes=output.attributes,
            attribute_caps=output.attribute_caps,
            creation_points=output.creation_points,
            level_points=output.level_points,
            trained_points=output.trained_points,
            rune_cost=output.rune_cost,
            available_points=output.available_points,
            health=output.health,
            mana=output.mana,
            stamina=output.stamina,
            defense=output.defense,
            calculator_declaration_sha256=self._calculator.declaration_sha256,
        )


class CalculatorBackedGenomeMutator(CompilerBackedGenomeMutator):
    """Use calculator allocation transitions inside the existing compiler gate."""

    def __init__(
        self,
        compiler: LegalBuildCompiler,
        allocation_space: CalculatorAllocationSpace,
        *,
        gate: CatalogBackedLegalityGate | None = None,
        rune_ids: tuple[int, ...] = (),
        equipment_options: tuple[tuple[str, tuple[int, ...]], ...] = (),
        power_options: tuple[tuple[str, int], ...] = (),
        maximum_attempts: int = 64,
    ) -> None:
        if not isinstance(allocation_space, CalculatorAllocationSpace):
            raise LegalBuildCompileError("allocation_space has the wrong type")
        super().__init__(
            compiler,
            gate=gate,
            rune_ids=rune_ids,
            equipment_options=equipment_options,
            power_options=power_options,
            maximum_attempts=maximum_attempts,
        )
        self._allocation_space = allocation_space
        self._allocation_rune_ids = tuple(sorted(rune_ids))

    def _mutate_attributes(
        self,
        parent: LegalBuildGenome,
        random: DeterministicRandom,
    ) -> LegalBuildGenome | None:
        candidate = self._allocation_space.mutate(parent, random)
        if candidate is None:
            return None
        return _replace_allocation_mutation(
            parent,
            trained_modifiers=candidate.trained_modifiers,
        )

    def _mutate_rune(
        self,
        parent: LegalBuildGenome,
        random: DeterministicRandom,
    ) -> LegalBuildGenome | None:
        selected = set(parent.rune_ids)
        available = tuple(
            rune_id for rune_id in self._allocation_rune_ids if rune_id not in selected
        )
        can_remove = bool(selected)
        can_add = bool(available)
        if not can_remove and not can_add:
            return None
        remove = can_remove and (not can_add or random.randbelow(2) == 0)
        if remove:
            ordered = tuple(sorted(selected))
            selected.remove(ordered[random.randbelow(len(ordered))])
        else:
            selected.add(available[random.randbelow(len(available))])
        repaired = self._allocation_space.repair_runes(
            parent,
            tuple(sorted(selected)),
            random,
            fill_available=True,
        )
        if repaired is None:
            return None
        return _replace_allocation_mutation(
            parent,
            rune_ids=repaired.rune_ids,
            trained_modifiers=repaired.trained_modifiers,
        )


def _replace_allocation_mutation(
    parent: LegalBuildGenome,
    **changes: object,
) -> LegalBuildGenome:
    payload = {
        "parent": genome_mechanical_digest(parent),
        "changes": {
            key: value.as_dict() if isinstance(value, StatLine) else value
            for key, value in sorted(changes.items())
        },
    }
    suffix = canonical_digest(payload)[:16]
    return replace(
        parent,
        genome_id=f"{parent.genome_id}.m.{suffix}",
        display_name=f"{parent.display_name} mutation {suffix[:8]}",
        **changes,
    )


__all__ = [
    "CalculatorAllocation",
    "CalculatorAllocationNeighbor",
    "CalculatorAllocationSpace",
    "CalculatorBackedGenomeMutator",
]
