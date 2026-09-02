import unittest

from shadowbane_lab.client_observation import (
    NativePlayerVitalsObservation,
    NativeTargetHealthObservation,
    NativeTargetIdentityObservation,
)
from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.protocol import Relation
from shadowbane_lab.pve import (
    PvEObservation,
    PvETargetAuthorityEvidence,
    PvETargetAuthorityExclusion,
    PvETargetCharacterKind,
    evaluate_pve_target_authority,
)


class PvETargetAuthorityProvenanceTests(unittest.TestCase):
    def test_missing_provenance_is_a_rejection_not_an_evaluator_exception(self) -> None:
        observation = PvEObservation(
            now_ms=100,
            target=NativeTargetHealthObservation(
                target_present=True,
                current_health=10.0,
                maximum_health=10.0,
                target_token="mob",
            ),
            player=NativePlayerVitalsObservation(
                current_health=100.0,
                maximum_health=100.0,
                current_mana=50.0,
                maximum_mana=50.0,
                current_stamina=100.0,
                maximum_stamina=100.0,
            ),
            target_identity=NativeTargetIdentityObservation(
                target_present=True,
                arc_character=True,
                merchant=False,
                shopkeeper=False,
                banker=False,
                trainer=False,
                minion=False,
                target_token="mob",
            ),
        )
        evidence = PvETargetAuthorityEvidence(
            target_token="mob",
            source_revision=1,
            target_object_key=NativeObjectKey(10, 100),
            local_player_object_key=NativeObjectKey(10, 200),
            character_kind=PvETargetCharacterKind.NPC,
            relation=Relation.ENEMY,
            same_party=False,
            friendly_owned=False,
            attackable=True,
            evidence_sources=(),
        )

        decision = evaluate_pve_target_authority(observation, evidence)

        self.assertFalse(decision.accepted)
        self.assertIn(
            PvETargetAuthorityExclusion.EVIDENCE_PROVENANCE_UNAVAILABLE,
            decision.exclusions,
        )


if __name__ == "__main__":
    unittest.main()
