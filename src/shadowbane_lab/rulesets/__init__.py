"""Ruleset compilation and bundled Shadowbane source declarations."""

from shadowbane_lab.rulesets.loader import (
    RULESET_SOURCE_VERSION,
    RulesetLoadError,
    load_ruleset,
    load_ruleset_text,
    load_shadowbane_vertical_slice,
)
from shadowbane_lab.rulesets.model import (
    CompilationStatus,
    CompiledActionRecord,
    CompiledRuleset,
    ConcreteMapping,
    FieldProvenance,
    ProvenanceSource,
    SourceKind,
)

__all__ = [
    "RULESET_SOURCE_VERSION",
    "CompilationStatus",
    "CompiledActionRecord",
    "CompiledRuleset",
    "ConcreteMapping",
    "FieldProvenance",
    "ProvenanceSource",
    "RulesetLoadError",
    "SourceKind",
    "load_ruleset",
    "load_ruleset_text",
    "load_shadowbane_vertical_slice",
]
