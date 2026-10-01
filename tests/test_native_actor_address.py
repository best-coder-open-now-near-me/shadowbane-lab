"""Actor-only address hints require fresh registry ownership, never a synthetic target."""

import pytest
from test_native_character_population import FakeScanningProcess, _profile

from shadowbane_lab.client_observation.native_object import NativeObjectKey
from shadowbane_lab.client_observation.native_population import (
    NativeCharacterPopulationReader,
    NativeCharacterPopulationReadError,
)


def test_actor_resolution_without_selected_or_any_other_character():
    process = FakeScanningProcess(_profile())
    process.set_registry(process.player)
    reader = NativeCharacterPopulationReader(process.profile, process)
    token, key, _ = reader.observe_actor_identity()
    assert reader.resolve_actor_address(local_key=key, token=token) == process.player
    assert process.find_calls == 0


@pytest.mark.parametrize("what", ["token", "key", "unregistered"])
def test_actor_resolution_never_reuses_key_only_or_heap_remnant(what):
    process = FakeScanningProcess(_profile())
    reader = NativeCharacterPopulationReader(process.profile, process)
    token, key, _ = reader.observe_actor_identity()
    if what == "token":
        token = "other"
    if what == "key":
        key = NativeObjectKey(1234, 53)
    if what == "unregistered":
        process.set_registry(process.crab)
    with pytest.raises(NativeCharacterPopulationReadError):
        reader.resolve_actor_address(local_key=key, token=token)
