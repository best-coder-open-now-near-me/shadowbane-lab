"""Tracking resolves real synthetic memory through the shared learned reader."""

import struct
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_native_ability import PREPARED, Memory, entry

from shadowbane_lab.client_observation import native_ability as ability
from shadowbane_lab.client_observation.native_character_config import ActiveCharacterError
from shadowbane_lab.client_observation.native_tracking_ability import (
    NativeTrackingAbility,
    resolve_learned_tracking_ability,
)

FOE = 123456  # Synthetic ID: production resolves the learned native ID.


@pytest.fixture
def tracking(monkeypatch):
    process = Memory()
    process.configure([(FOE, "Hunt Foe")])
    data = process.blocks[process.definitions[FOE]]
    struct.pack_into("<I", data, 0x204, 4)
    struct.pack_into("<I", data, 0x1A8, 4)
    session = SimpleNamespace(
        binding=SimpleNamespace(
            process_id=123, executable_sha256=PREPARED, process_creation_filetime_utc=456,
        ),
        reader=SimpleNamespace(process=process, process_creation_filetime_utc=456),
        require_current=Mock(),
    )
    reader = Mock()
    reader.observe.return_value = SimpleNamespace(powers=(entry(FOE, rank=1),))
    factory = Mock(return_value=reader)
    monkeypatch.setattr(ability, "NativePlayerTrainingReader", factory)
    monkeypatch.setattr(ability, "load_bundled_native_training_profile", lambda: "profile")
    return session, process, reader, factory


@pytest.mark.parametrize("rank", [1, 40, 99])
def test_tracking_resolves_native_rank_and_borrowed_handle_without_combat_routing(tracking, rank):
    session, process, reader, factory = tracking
    reader.observe.return_value = SimpleNamespace(powers=(entry(FOE, rank=rank),))
    result = resolve_learned_tracking_ability(session, " hunt FOE ")
    assert result == NativeTrackingAbility(FOE, "Hunt Foe", f"POWER-{FOE}", 4, 4, 0, rank)
    assert result.as_dict()["kind"] == "player_tracking"
    assert "recipient" not in result.as_dict()
    factory.assert_called_once_with("profile", process)
    with pytest.raises(FrozenInstanceError):
        result.power_id = 1
    with pytest.raises(ability.NativeAbilityError, match="unsupported"):
        ability.resolve_learned_ability(session, "Hunt Foe")
    raw = ability.NativeAbilityResolver(session).resolve_definition("Hunt Foe")
    assert raw.power_id == result.power_id
    with pytest.raises(ability.NativeAbilityError, match="unsupported"):
        _ = raw.recipient


@pytest.mark.parametrize("selector", ["Track", "Hunt Prey", str(FOE), "", None])
def test_other_selection_never_reads_native_memory(tracking, selector):
    session, process, _, factory = tracking
    with pytest.raises(ability.NativeAbilityError, match="selector"):
        resolve_learned_tracking_ability(session, selector)
    assert not process.reads
    factory.assert_not_called()


@pytest.mark.parametrize("offset,value", [(0x204, 0), (0x1A8, 5), (0x1B4, 1)])
def test_tracking_rejects_wrong_native_semantics(tracking, offset, value):
    session, process, _, _ = tracking
    struct.pack_into("<I", process.blocks[process.definitions[FOE]], offset, value)
    with pytest.raises(ability.NativeAbilityError, match="category 4"):
        resolve_learned_tracking_ability(session)


def test_unlearned_tracking_rejected(tracking):
    session, _, reader, _ = tracking
    reader.observe.return_value = SimpleNamespace(powers=(entry(FOE, rank=0),))
    with pytest.raises(ability.NativeAbilityError, match="not learned"):
        resolve_learned_tracking_ability(session)


def test_duplicate_named_learned_powers_remain_ambiguous(tracking):
    session, process, reader, _ = tracking
    process.configure([(100, "Hunt Foe"), (200, "HUNT FOE")])
    reader.observe.return_value = SimpleNamespace(powers=(entry(100), entry(200)))
    with pytest.raises(ability.NativeAbilityError, match="ambiguous"):
        resolve_learned_tracking_ability(session)


@pytest.mark.parametrize(
    "fault", ["image", "creation", "handle", "definition", "rank", "character"],
)
def test_tracking_preserves_exact_session_and_stable_observation_guards(tracking, fault):
    session, process, reader, _ = tracking
    if fault == "image":
        session.binding.executable_sha256 = process.executable_sha256 = "a" * 64
    elif fault == "creation":
        session.reader.process_creation_filetime_utc = 789
    elif fault == "handle":
        def replaced():
            session.reader.process = Memory()
            return SimpleNamespace(powers=(entry(FOE),))
        reader.observe.side_effect = replaced
    elif fault == "definition":
        process.mutate = process.definitions[FOE]
    elif fault == "rank":
        reader.observe.side_effect = [
            SimpleNamespace(powers=(entry(FOE, rank=1),)),
            SimpleNamespace(powers=(entry(FOE, rank=2),)),
        ]
    else:
        def retired():
            if reader.observe.call_count == 2:
                session.require_current.side_effect = ActiveCharacterError("retired")
            return SimpleNamespace(powers=(entry(FOE, rank=1),))
        reader.observe.side_effect = retired
    with pytest.raises((ability.NativeAbilityError, ActiveCharacterError)):
        resolve_learned_tracking_ability(session)


@pytest.mark.parametrize("changes", [
    {"display_name": "Hunt Prey"}, {"learned_rank": 0}, {"learned_rank": True},
    {"category": 0}, {"target_mode": 5}, {"delivery": 1}, {"power_id": 0},
])
def test_dto_cannot_claim_player_tracking_with_invalid_definition(tracking, changes):
    result = resolve_learned_tracking_ability(tracking[0])
    with pytest.raises((ValueError, ability.NativeAbilityError)):
        replace(result, **changes)
