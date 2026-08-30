"""Public semantic protocol API."""

from shadowbane_lab.protocol.adapters import (
    DecisionAdapter,
    DispatchResult,
    RecordingDecisionAdapter,
)
from shadowbane_lab.protocol.codec import ProtocolDecodeError, decode_message, encode_message
from shadowbane_lab.protocol.model import (
    PROTOCOL_VERSION,
    ActionBinding,
    Affordance,
    AffordanceSetMessage,
    DecisionMessage,
    EntityKind,
    EntityObservation,
    Event,
    EventBatchMessage,
    EventKind,
    NamedScalar,
    ObservationMessage,
    ProtocolMessage,
    Relation,
    TargetKind,
    Vector2,
)
from shadowbane_lab.protocol.validation import ProtocolMismatchError, validate_exchange

__all__ = [
    "PROTOCOL_VERSION",
    "ActionBinding",
    "Affordance",
    "AffordanceSetMessage",
    "DecisionAdapter",
    "DecisionMessage",
    "DispatchResult",
    "EntityKind",
    "EntityObservation",
    "Event",
    "EventBatchMessage",
    "EventKind",
    "NamedScalar",
    "ObservationMessage",
    "ProtocolDecodeError",
    "ProtocolMessage",
    "ProtocolMismatchError",
    "RecordingDecisionAdapter",
    "Relation",
    "TargetKind",
    "Vector2",
    "decode_message",
    "encode_message",
    "validate_exchange",
]
