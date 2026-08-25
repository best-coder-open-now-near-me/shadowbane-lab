import unittest

from shadowbane_lab.protocol import DecisionAdapter, RecordingDecisionAdapter

from tests.fixtures import protocol_exchange


class RecordingAdapterTests(unittest.TestCase):
    def test_records_decision_without_external_side_effects(self) -> None:
        decision = protocol_exchange()[2]
        adapter = RecordingDecisionAdapter()

        result = adapter.dispatch(decision)

        self.assertIsInstance(adapter, DecisionAdapter)
        self.assertTrue(result.accepted)
        self.assertEqual(decision.correlation_id, result.correlation_id)
        self.assertEqual((decision,), adapter.decisions)


if __name__ == "__main__":
    unittest.main()
