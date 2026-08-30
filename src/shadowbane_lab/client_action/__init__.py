"""Bounded, evidence-bearing acceptance actions for the live client."""

from .evidence import (
    ClientActionEvidenceError,
    load_client_action_evidence,
    save_client_action_evidence,
)
from .model import (
    CLIENT_ACTION_RESULT_SCHEMA_VERSION,
    ActionEvidenceValue,
    ClientActionBoundary,
    ClientActionBoundaryRecord,
    ClientActionCheckpoint,
    ClientActionEffectObservation,
    ClientActionResult,
    ClientActionSpec,
    ClientActionVerification,
)
from .runner import BoundedClientAction, ClientActionRunner
from .world_map import (
    WORLD_MAP_DESTINATION_CLICK_ACTION_KEY,
    ExtensionEventSnapshotSource,
    InputPlanExecutor,
    WorldMapDestinationClickAction,
    WorldMapDestinationClickError,
    WorldMapObservationSource,
)

__all__ = [
    "CLIENT_ACTION_RESULT_SCHEMA_VERSION",
    "ActionEvidenceValue",
    "BoundedClientAction",
    "ClientActionBoundary",
    "ClientActionBoundaryRecord",
    "ClientActionCheckpoint",
    "ClientActionEffectObservation",
    "ClientActionEvidenceError",
    "ClientActionResult",
    "ClientActionRunner",
    "ClientActionSpec",
    "ClientActionVerification",
    "ExtensionEventSnapshotSource",
    "InputPlanExecutor",
    "WORLD_MAP_DESTINATION_CLICK_ACTION_KEY",
    "WorldMapDestinationClickAction",
    "WorldMapDestinationClickError",
    "WorldMapObservationSource",
    "load_client_action_evidence",
    "save_client_action_evidence",
]
