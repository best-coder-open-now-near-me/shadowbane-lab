"""Composable source-package, build-view, and simulation-case contracts."""

from shadowbane_lab.composition.adapters import (
    build_view_from_primitive_loadout,
    primitive_loadout_from_build_view,
)
from shadowbane_lab.composition.io import (
    CompositionFormatError,
    dump_build_blueprint,
    dump_source_package_catalog,
    load_build_blueprint,
    load_build_blueprint_text,
    load_source_package_catalog,
    load_source_package_catalog_text,
)
from shadowbane_lab.composition.model import (
    BodyDelta,
    BodyValues,
    BuildBlueprint,
    CompositionError,
    GrantSource,
    ResolvedBuildView,
    ResolvedScenarioView,
    ScenarioOverlay,
    ScenarioSlotView,
    SimulationCaseView,
    SimulationParticipantView,
    SourcePackage,
    SourcePackageCatalog,
    SourcePackageKind,
    canonical_json,
)
from shadowbane_lab.composition.resolver import (
    BuildResolutionError,
    BuildResolver,
    resolve_build_blueprint,
)

__all__ = [
    "BodyDelta",
    "BodyValues",
    "BuildBlueprint",
    "BuildResolutionError",
    "BuildResolver",
    "CompositionError",
    "CompositionFormatError",
    "GrantSource",
    "ResolvedBuildView",
    "ResolvedScenarioView",
    "ScenarioOverlay",
    "ScenarioSlotView",
    "SimulationCaseView",
    "SimulationParticipantView",
    "SourcePackage",
    "SourcePackageCatalog",
    "SourcePackageKind",
    "build_view_from_primitive_loadout",
    "canonical_json",
    "dump_build_blueprint",
    "dump_source_package_catalog",
    "load_build_blueprint",
    "load_build_blueprint_text",
    "load_source_package_catalog",
    "load_source_package_catalog_text",
    "primitive_loadout_from_build_view",
    "resolve_build_blueprint",
]
