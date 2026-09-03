"""Legal build compilation and deterministic quality-diversity search."""

from .build_compiler import LegalBuildCompiler
from .build_io import load_legal_build_genome, load_legal_build_genome_text
from .build_model import (
    LEGAL_BUILD_COMPILER_VERSION,
    LEGAL_BUILD_GENOME_SCHEMA_VERSION,
    BuildCompilationStatus,
    BuildCoverageReport,
    CompiledLegalBuild,
    EquipmentSelection,
    LegalBuildCompileError,
    LegalBuildCompilePolicy,
    LegalBuildGenome,
    SelectedAffix,
)
from .calculator_allocation import (
    CalculatorAllocation,
    CalculatorAllocationNeighbor,
    CalculatorAllocationSpace,
    CalculatorBackedGenomeMutator,
)
from .map_elites import (
    ArchiveAdmission,
    DescriptorAxis,
    MapElitesArchive,
    MapElitesCell,
    MapElitesError,
    MapElitesEvaluation,
    MapElitesInsertStatus,
    MapElitesRun,
    run_map_elites,
)
from .policy_rollout import (
    UtilityPolicyEvaluation,
    UtilityPolicyLeagueEvaluator,
    primitive_loadout_mechanical_digest,
    primitive_loadout_mechanical_payload,
    run_open_duel_with_policies,
)
from .policy_search import (
    DiagonalPolicySearchConfig,
    DiagonalPolicySearchGeneration,
    DiagonalPolicySearchResult,
    run_diagonal_policy_search,
)
from .static_capabilities import (
    StaticCapabilityGrant,
    StaticCapabilityProjection,
    project_static_capabilities,
)
from .strict_training import StrictLegalBuildLeagueEvaluator
from .training import (
    CatalogBackedLegalityGate,
    CatalogLegalityAudit,
    CompiledOpponent,
    CompilerBackedGenomeMutator,
    DuelScenario,
    EquipmentSkillRequirement,
    evaluation_digest,
    genome_mechanical_digest,
    genome_mechanical_payload,
)
from .training import (
    LegalBuildLeagueEvaluator as PermissiveLegalBuildLeagueEvaluator,
)
from .training_budget import (
    TrainingAllocationAudit,
    TrainingBudgetCatalog,
    TrainingBudgetProfile,
    TrainingCostEvidence,
    TrainingLevelBand,
    TrainingPopulationScope,
    TrainingSelectionCost,
    load_bundled_training_budget_catalog,
)
from .training_budget_gate import (
    TrainingBudgetBackedLegalityGate,
    TrainingCatalogLegalityAudit,
)
from .utility_policy import (
    POLICY_WEIGHT_FIELDS,
    DuelPolicy,
    PolicyFactory,
    UtilityPolicyWeights,
    WeightedUtilityDuelPolicy,
    baseline_policy_factory,
    weighted_policy_factory,
)

LegalBuildLeagueEvaluator = StrictLegalBuildLeagueEvaluator

__all__ = [
    "LEGAL_BUILD_COMPILER_VERSION",
    "LEGAL_BUILD_GENOME_SCHEMA_VERSION",
    "POLICY_WEIGHT_FIELDS",
    "ArchiveAdmission",
    "BuildCompilationStatus",
    "BuildCoverageReport",
    "CalculatorAllocation",
    "CalculatorAllocationNeighbor",
    "CalculatorAllocationSpace",
    "CalculatorBackedGenomeMutator",
    "CatalogBackedLegalityGate",
    "CatalogLegalityAudit",
    "CompiledLegalBuild",
    "CompiledOpponent",
    "CompilerBackedGenomeMutator",
    "DescriptorAxis",
    "DiagonalPolicySearchConfig",
    "DiagonalPolicySearchGeneration",
    "DiagonalPolicySearchResult",
    "DuelPolicy",
    "DuelScenario",
    "EquipmentSelection",
    "EquipmentSkillRequirement",
    "LegalBuildCompileError",
    "LegalBuildCompilePolicy",
    "LegalBuildCompiler",
    "LegalBuildGenome",
    "LegalBuildLeagueEvaluator",
    "MapElitesArchive",
    "MapElitesCell",
    "MapElitesError",
    "MapElitesEvaluation",
    "MapElitesInsertStatus",
    "MapElitesRun",
    "PermissiveLegalBuildLeagueEvaluator",
    "PolicyFactory",
    "SelectedAffix",
    "StaticCapabilityGrant",
    "StaticCapabilityProjection",
    "StrictLegalBuildLeagueEvaluator",
    "TrainingAllocationAudit",
    "TrainingBudgetBackedLegalityGate",
    "TrainingBudgetCatalog",
    "TrainingBudgetProfile",
    "TrainingCatalogLegalityAudit",
    "TrainingCostEvidence",
    "TrainingLevelBand",
    "TrainingPopulationScope",
    "TrainingSelectionCost",
    "UtilityPolicyEvaluation",
    "UtilityPolicyLeagueEvaluator",
    "UtilityPolicyWeights",
    "WeightedUtilityDuelPolicy",
    "baseline_policy_factory",
    "evaluation_digest",
    "genome_mechanical_digest",
    "genome_mechanical_payload",
    "load_bundled_training_budget_catalog",
    "load_legal_build_genome",
    "load_legal_build_genome_text",
    "primitive_loadout_mechanical_digest",
    "primitive_loadout_mechanical_payload",
    "project_static_capabilities",
    "run_diagonal_policy_search",
    "run_map_elites",
    "run_open_duel_with_policies",
    "weighted_policy_factory",
]
