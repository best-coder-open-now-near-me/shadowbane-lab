"""Deterministic combat simulation and build-search tools."""

from .catalog import default_action_catalog
from .genome import BuildGenome, compile_genome, reference_genomes
from .simulator import CombatSimulator, DuelResult

__all__ = [
    "BuildGenome",
    "CombatSimulator",
    "DuelResult",
    "compile_genome",
    "default_action_catalog",
    "reference_genomes",
]

__version__ = "0.1.0"
