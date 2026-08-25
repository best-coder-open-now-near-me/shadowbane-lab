"""Cross-message validation for semantic decisions."""

from __future__ import annotations

from shadowbane_lab.protocol.model import (
    Affordance,
    AffordanceSetMessage,
    DecisionMessage,
    ObservationMessage,
)


class ProtocolMismatchError(ValueError):
    """Raised when individually valid messages do not belong to the same exchange."""


def validate_exchange(
    observation: ObservationMessage,
    affordance_set: AffordanceSetMessage,
    decision: DecisionMessage,
) -> Affordance:
    """Validate a decision and return the exact affordance it selected.

    The comparison includes the complete binding so a policy cannot alter a target or
    parameter after legality was calculated.
    """

    expected = (observation.observation_id, observation.agent_id, observation.tick)
    if (affordance_set.observation_id, affordance_set.agent_id, affordance_set.tick) != expected:
        raise ProtocolMismatchError("affordance set does not match the observation")
    if (decision.observation_id, decision.agent_id, decision.tick) != expected:
        raise ProtocolMismatchError("decision does not match the observation")

    selected = next(
        (
            affordance
            for affordance in affordance_set.affordances
            if affordance.affordance_id == decision.affordance_id
        ),
        None,
    )
    if selected is None:
        raise ProtocolMismatchError("decision selected an unavailable affordance")
    if selected.action_key != decision.action_key:
        raise ProtocolMismatchError("decision action key does not match the affordance")
    if selected.binding != decision.binding:
        raise ProtocolMismatchError("decision binding does not match the legal affordance")
    return selected
