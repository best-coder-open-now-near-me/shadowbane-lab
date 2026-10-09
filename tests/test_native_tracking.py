from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_tracking import (
    REVIEWED_TRACK_EXECUTABLES,
    NativeTrackingCompatibilityError,
    NativeTrackingError,
    NativeTrackingReader,
)
from tests.test_native_vendor_queue import CONTROL, ENTRY, HUD, LIST, ROOT
from tests.test_native_vendor_queue import fixture as queue_fixture
from tests.test_native_vendor_roster import text


def fixture():
    memory = queue_fixture()
    memory.executable_sha256 = next(iter(REVIEWED_TRACK_EXECUTABLES))
    for address, value in (
        (HUD, memory.base_address + 0x116FB58), (HUD + 0x3C0, LIST),
        (HUD + 0x3B8, 429578587), (ENTRY, memory.base_address + 0x116FCC0),
        (ENTRY + 8, 0x1C),
    ):
        memory.put(address, '<I', value)
    memory.put(ENTRY + 0x10, '<II', 1122, 53)
    text(memory, ENTRY + 0x20, 0x310000, 'Praeda')
    binding = SimpleNamespace(
        process_id=memory.pid, process_creation_filetime_utc=100,
        executable_sha256=memory.executable_sha256,
    )
    session = SimpleNamespace(
        binding=binding,
        reader=SimpleNamespace(process=memory, process_creation_filetime_utc=100),
        require_current=Mock(),
    )
    return session, memory


def test_reads_contacts_without_selection_or_fabricated_freshness():
    session, memory = fixture()
    memory.put(HUD + 0x3BC, '<I', 0xDEADBEEF)
    result = NativeTrackingReader(session).read()
    assert result.loaded and result.power_id == 429578587
    assert result.contacts[0].object_key == NativeObjectKey(1122, 53)
    assert result.contacts[0].name == 'Praeda'
    assert result.as_dict()['response_age_seconds'] is None
    assert (HUD + 0x3BC, 4) not in memory.reads
    assert session.require_current.call_count == 3


def test_absent_and_empty_lists_are_distinct():
    session, memory = fixture()
    memory.put(LIST + 0x408, '<III', 0, 0, 0)
    empty = NativeTrackingReader(session).read()
    assert empty.loaded and empty.contacts == ()
    memory.put(HUD, '<I', memory.base_address + 0x1168CA8)
    missing = NativeTrackingReader(session).read()
    assert not missing.loaded and missing.power_id is None and missing.contacts == ()


@pytest.mark.parametrize('address,value', [
    (ROOT + 0x64, 1), (LIST + 0x3BC, HUD + 4),
    (CONTROL + 0x458, LIST + 4), (CONTROL + 0x3BC, HUD + 4),
    (ENTRY + 8, 0x1D), (ENTRY, 0), (0x160000, LIST + 4),
])
def test_rejects_wrong_world_or_disconnected_objects(address, value):
    session, memory = fixture()
    memory.put(address, '<I', value)
    with pytest.raises(NativeTrackingError):
        NativeTrackingReader(session).read()


@pytest.mark.parametrize('address,size', [(ENTRY + 0x10, 8), (LIST + 0x408, 12),
                                        (0x310000, 12), (HUD + 0x3B8, 4)])
def test_changed_result_is_unavailable_not_an_empty_success(address, size):
    session, memory = fixture()
    memory.change = address, size, bytes([255]) * size
    with pytest.raises(NativeTrackingError):
        NativeTrackingReader(session).read()


def test_duplicate_contact_cannot_masquerade_as_two_players():
    session, memory = fixture()
    other = 0x210000
    memory.put(LIST + 0x408, '<III', 0x170000, 0x170008, 0x170010)
    memory.put(0x170000, '<II', CONTROL, other)
    for offset, value in ((0, memory.base_address + 0x116AEBC), (0x3BC, HUD),
                          (0x458, LIST), (0x44C, ENTRY)):
        memory.put(other + offset, '<I', value)
    with pytest.raises(NativeTrackingError, match='duplicate'):
        NativeTrackingReader(session).read()


def test_unknown_build_rejected_without_reading_memory():
    session, memory = fixture()
    memory.executable_sha256 = session.binding.executable_sha256 = 'f' * 64
    with pytest.raises(NativeTrackingCompatibilityError):
        NativeTrackingReader(session)
    assert not memory.reads


def test_revoked_or_replaced_character_is_not_rebound():
    session, _ = fixture()
    reader = NativeTrackingReader(session)
    session.require_current.side_effect = RuntimeError('character changed')
    with pytest.raises(RuntimeError, match='character changed'):
        reader.read()
    session.require_current.side_effect = None
    session.reader = SimpleNamespace(process=object())
    with pytest.raises(NativeTrackingError, match='session changed'):
        reader.read()
