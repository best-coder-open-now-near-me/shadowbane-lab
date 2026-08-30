"""Ruleset compilation and bundled Shadowbane source declarations."""

from shadowbane_lab.rulesets.loader import (
    RULESET_SOURCE_VERSION,
    RulesetLoadError,
    load_ruleset,
    load_ruleset_text,
    load_shadowbane_vertical_slice,
)
from shadowbane_lab.rulesets.model import (
    CharacterBuild,
    CompilationStatus,
    CompiledActionRecord,
    CompiledRuleset,
    ConcreteMapping,
    FieldProvenance,
    PowerProgression,
    ProvenanceSource,
    SourceKind,
    TrainingRequirement,
)

__all__ = [
    "RULESET_SOURCE_VERSION",
    "CompilationStatus",
    "CharacterBuild",
    "CompiledActionRecord",
    "CompiledRuleset",
    "ConcreteMapping",
    "FieldProvenance",
    "PowerProgression",
    "ProvenanceSource",
    "RulesetLoadError",
    "SourceKind",
    "TrainingRequirement",
    "load_ruleset",
    "load_ruleset_text",
    "load_shadowbane_vertical_slice",
]
