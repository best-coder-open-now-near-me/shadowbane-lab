"""Exact .15 compatibility does not broaden mutation, lifetime or affix authority."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from shadowbane_lab.client_extension.bootstrap_author import (
    BootstrapAuthoringError,
    resolve_reviewed_bootstrap_profile,
)
from shadowbane_lab.client_observation.build_compatibility import native_layout_is_compatible
from shadowbane_lab.client_observation.native_character_config import (
    ActiveCharacterError,
    NativeCharacterConfigReader,
)
from shadowbane_lab.client_observation.native_character_session import NativeCharacterSession
from shadowbane_lab.client_observation.native_crest_lists import read_native_crest_lists
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCompatibilityError,
)
from shadowbane_lab.equipment.crafting_assessment import assess_native_crafting_roll
from shadowbane_lab.equipment.rolling_policy import RollDisposition
from tests.test_active_character_config import CharacterMemory
from tests.test_crafting_assessment import result as crafting_result
from tests.test_native_crest_lists import fixture as crest_fixture

ORIGINAL = "381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5"
PREPARED = "e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437"
PREVIOUS = "e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e"


def test_bootstrap_keeps_exact_unchanged_layout_and_unknown_denial():
    previous = resolve_reviewed_bootstrap_profile(PREVIOUS)
    profile = resolve_reviewed_bootstrap_profile(ORIGINAL)
    assert profile.profile_id == "wonderbane-1.3.38.15-381e6758"
    assert profile.source_length == 21143613
    assert replace(profile, profile_id=previous.profile_id,
                   source_sha256=previous.source_sha256) == previous
    assert native_layout_is_compatible(PREVIOUS, ORIGINAL)
    assert native_layout_is_compatible(PREVIOUS, PREPARED)
    assert not native_layout_is_compatible(PREVIOUS, "ff" * 32)
    for digest in (PREPARED, "ff" * 32):
        with pytest.raises(BootstrapAuthoringError):
            resolve_reviewed_bootstrap_profile(digest)


def test_prepared_character_session_still_revokes_replaced_native_key(tmp_path):
    import struct
    memory = CharacterMemory(tmp_path)
    memory.executable_sha256 = PREPARED
    memory.put(memory.player + 0x18, struct.pack("<II", 1001, 53))
    session = NativeCharacterSession(NativeCharacterConfigReader(memory))
    session.require_current()
    assert session.binding.executable_sha256 == PREPARED
    memory.put(memory.player + 0x18, struct.pack("<II", 1002, 53))
    with pytest.raises(ActiveCharacterError):
        session.require_current()
    memory.put(memory.player + 0x18, struct.pack("<II", 1001, 53))
    with pytest.raises(ActiveCharacterError, match="revoked"):
        session.require_current()
    session.close()
    assert memory.closed


@pytest.mark.parametrize("digest", [ORIGINAL, "ff" * 32])
def test_strict_readers_reject_original_unknown_before_memory(tmp_path, digest):
    memory = CharacterMemory(tmp_path)
    memory.executable_sha256 = digest
    with pytest.raises(ActiveCharacterError):
        NativeCharacterConfigReader(memory)
    assert not memory.reads
    crests = crest_fixture()
    crests.executable_sha256 = digest
    with pytest.raises(NativeVendorDialogCompatibilityError):
        read_native_crest_lists(crests)
    assert not crests.reads


def test_new_prepared_crest_copy_has_no_command_or_server_authority():
    memory = crest_fixture()
    memory.executable_sha256 = PREPARED
    result = read_native_crest_lists(memory)
    assert result["windows"]
    assert not result["command_admitted"] and not result["server_acceptance_verified"]


def test_new_image_does_not_inherit_affix_disposal_qualification():
    record = crafting_result()
    record["executable_sha256"] = PREPARED
    result = assess_native_crafting_roll(record)
    assert result.disposition == RollDisposition.KEEP
    assert result.reason == "unknown_affix_preserved" and not result.command_admitted


def test_registry_observation_layout_explicitly_admits_only_reviewed_pair():
    source = Path(__file__).parents[1] / "src/shadowbane_lab/client_observation/data"
    profile_path = source / "wonderbane-ef43784b.native-character-population.json"
    profile = json.loads(profile_path.read_text())
    images = profile["registry_profile"]["executable_sha256s"]
    assert PREPARED in images and ORIGINAL in images and "ff" * 32 not in images
