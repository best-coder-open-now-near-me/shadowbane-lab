import json
import unittest
from dataclasses import replace

from shadowbane_lab.differential import (
    ComparisonTolerance,
    DifferenceCategory,
    GapEntry,
    GapLedger,
    GapStatus,
    ReferenceTraceRecorder,
    TraceDecodeError,
    TraceMetadata,
    TraceSource,
    compare_traces,
    decode_trace,
    encode_trace,
    load_bundled_gap_ledger,
)
from shadowbane_lab.protocol import EntityKind, NamedScalar, Vector2
from shadowbane_lab.rulesets import load_shadowbane_vertical_slice
from shadowbane_lab.sim import EntityState, ReferenceEnvironment

SHADOW_BOLT = "shadowbane.assassin.shadow_bolt"


def shadow_bolt_trace():
    ruleset = load_shadowbane_vertical_slice()
    caster = EntityState(
        entity_id="assassin",
        life_id="assassin:1",
        kind=EntityKind.ACTOR,
        team_id="red",
        position=Vector2(0.0, 0.0),
        scalars={"health": 100.0, "mana": 100.0},
        maximums={"health": 100.0, "mana": 100.0},
        action_keys=(SHADOW_BOLT,),
    )
    target = EntityState(
        entity_id="target",
        life_id="target:1",
        kind=EntityKind.ACTOR,
        team_id="blue",
        position=Vector2(10.0, 0.0),
        scalars={"health": 100.0, "mana": 100.0},
        maximums={"health": 100.0, "mana": 100.0},
    )
    environment = ReferenceEnvironment(ruleset.catalog, (caster, target), seed=17)
    recorder = ReferenceTraceRecorder(
        environment,
        TraceMetadata(
            trace_id="trace:reference:shadow-bolt-17",
            source=TraceSource.REFERENCE_SIMULATOR,
            ruleset_id=ruleset.ruleset_id,
            ruleset_revision="vertical-slice-v1",
            scenario_id="shadow_bolt.rank40.controlled",
            tick_duration_ms=200,
            seed=17,
            captured_at="2026-08-25T12:00:00Z",
        ),
        ("assassin",),
    )
    exchange = environment.exchange("assassin")
    affordance = next(
        item
        for item in exchange.affordances.affordances
        if item.action_key == SHADOW_BOLT and item.binding.target_entity_id == "target"
    )
    decision = exchange.decision(affordance.affordance_id, "shadow-bolt-17")
    recorder.step((decision,))
    for _ in range(9):
        recorder.step()
    return recorder.trace()


def with_scalar(trace, step_index: int, entity_id: str, scalar_key: str, value: float):
    step = trace.steps[step_index]
    entities = tuple(
        replace(
            entity,
            scalars=tuple(
                NamedScalar(item.name, value if item.name == scalar_key else item.value)
                for item in entity.scalars
            ),
        )
        if entity.entity_id == entity_id
        else entity
        for entity in step.after.entities
    )
    steps = list(trace.steps)
    steps[step_index] = replace(step, after=replace(step.after, entities=entities))
    return replace(
        trace,
        metadata=replace(
            trace.metadata,
            trace_id="trace:emulator:shadow-bolt-17",
            source=TraceSource.EMULATOR_SERVER,
        ),
        steps=tuple(steps),
    )


def scalar_value(trace, step_index: int, entity_id: str, scalar_key: str) -> float:
    entity = next(
        item for item in trace.steps[step_index].after.entities if item.entity_id == entity_id
    )
    return next(item.value for item in entity.scalars if item.name == scalar_key)


class DifferentialValidationTests(unittest.TestCase):
    def test_reference_trace_round_trips_through_canonical_json(self) -> None:
        trace = shadow_bolt_trace()

        encoded = encode_trace(trace)

        self.assertEqual(trace, decode_trace(encoded))
        self.assertEqual(encoded, encode_trace(decode_trace(encoded)))

    def test_producer_specific_metadata_does_not_create_semantic_differences(self) -> None:
        expected = shadow_bolt_trace()
        actual = replace(
            expected,
            metadata=replace(
                expected.metadata,
                trace_id="trace:emulator:shadow-bolt-17",
                source=TraceSource.EMULATOR_SERVER,
                captured_at="2026-08-25T12:05:00Z",
            ),
        )

        report = compare_traces(expected, actual)

        self.assertTrue(report.exact)
        self.assertTrue(report.acceptable)

    def test_unordered_semantic_tags_do_not_create_differences(self) -> None:
        expected = shadow_bolt_trace()
        first = expected.steps[0]
        affordance_set = first.affordances[0]
        affordances = tuple(
            replace(item, tags=tuple(reversed(item.tags))) for item in affordance_set.affordances
        )
        actual = replace(
            expected,
            steps=(
                replace(first, affordances=(replace(affordance_set, affordances=affordances),)),
                *expected.steps[1:],
            ),
        )

        self.assertTrue(compare_traces(expected, actual).exact)

    def test_state_damage_difference_is_classified_and_unexpected(self) -> None:
        expected = shadow_bolt_trace()
        expected_health = scalar_value(expected, 9, "target", "health")
        actual = with_scalar(expected, 9, "target", "health", expected_health + 0.5)

        report = compare_traces(expected, actual)

        self.assertFalse(report.exact)
        self.assertFalse(report.acceptable)
        self.assertEqual(1, len(report.unexpected))
        self.assertEqual(DifferenceCategory.DAMAGE, report.unexpected[0].category)
        self.assertEqual(0.5, report.unexpected[0].absolute_delta)

    def test_numeric_tolerance_suppresses_only_its_category(self) -> None:
        expected = shadow_bolt_trace()
        last = expected.steps[-1]
        actual_steps = (
            *expected.steps[:-1],
            replace(last, after=replace(last.after, sim_time_ms=2_010)),
        )
        actual = replace(expected, steps=actual_steps)

        report = compare_traces(
            expected,
            actual,
            tolerance=ComparisonTolerance(timing_ms=10.0),
        )

        self.assertTrue(report.exact)

    def test_reviewed_gap_can_accept_a_scoped_bounded_difference(self) -> None:
        expected = shadow_bolt_trace()
        expected_health = scalar_value(expected, 9, "target", "health")
        actual = with_scalar(expected, 9, "target", "health", expected_health + 0.5)
        ledger = GapLedger(
            (
                GapEntry(
                    gap_id="test-midpoint-gap",
                    status=GapStatus.ACCEPTED_APPROXIMATION,
                    category=DifferenceCategory.DAMAGE,
                    scenario_pattern="shadow_bolt.rank40.controlled",
                    path_pattern="trace/steps/9/after/entities/target/scalars/health",
                    description="Test-only bounded midpoint difference.",
                    action_key=SHADOW_BOLT,
                    max_absolute_delta=0.5,
                    evidence_trace_ids=("trace:emulator:shadow-bolt-17",),
                ),
            )
        )

        report = compare_traces(expected, actual, gap_ledger=ledger)

        self.assertFalse(report.exact)
        self.assertTrue(report.acceptable)
        self.assertEqual("test-midpoint-gap", report.differences[0].accepted_gap_id)

    def test_open_bundled_gap_does_not_hide_a_difference(self) -> None:
        expected = shadow_bolt_trace()
        expected_health = scalar_value(expected, 9, "target", "health")
        actual = with_scalar(expected, 9, "target", "health", expected_health + 0.5)
        ledger = load_bundled_gap_ledger()

        report = compare_traces(expected, actual, gap_ledger=ledger)

        self.assertFalse(report.acceptable)
        self.assertEqual(10, len(ledger.entries))
        self.assertTrue(all(entry.status is GapStatus.OPEN for entry in ledger.entries))

    def test_missing_affordance_is_a_legality_difference(self) -> None:
        expected = shadow_bolt_trace()
        first = expected.steps[0]
        empty = replace(first.affordances[0], affordances=())
        actual = replace(
            expected, steps=(replace(first, affordances=(empty,)), *expected.steps[1:])
        )

        report = compare_traces(expected, actual)

        self.assertTrue(report.unexpected)
        self.assertTrue(
            all(item.category is DifferenceCategory.LEGALITY for item in report.unexpected)
        )

    def test_malformed_nested_protocol_message_fails_closed(self) -> None:
        data = json.loads(encode_trace(shadow_bolt_trace()))
        del data["steps"][0]["events"]["protocol_version"]

        with self.assertRaises(TraceDecodeError):
            decode_trace(json.dumps(data))


if __name__ == "__main__":
    unittest.main()
