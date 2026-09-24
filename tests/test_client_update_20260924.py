"""Exact September 24 client support must not broaden command or affix admission."""
from dataclasses import replace

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
from shadowbane_lab.client_observation.native_crafting import (
    CRAFTING_BREAKPOINTS,
    NativeCraftingTracer,
)
from shadowbane_lab.client_observation.native_crest_lists import read_native_crest_lists
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCompatibilityError,
)
from shadowbane_lab.equipment.crafting_assessment import assess_native_crafting_roll
from shadowbane_lab.equipment.rolling_policy import RollDisposition
from tests.test_active_character_config import CharacterMemory
from tests.test_crafting_assessment import result as crafting_result
from tests.test_native_crafting import Backend
from tests.test_native_crest_lists import fixture as crest_fixture

ORIGINAL = "6347b420c6c151995f168f16fd1624408dd8911698d11a4a74b26d211fb49f19"
PREPARED = "7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f"
PREVIOUS = "cae5311b5b6134bf25155b16c70b1743c1216c0bd0c88f1240d7e92388211d26"


def test_original_has_exact_bootstrap_layout_and_both_images_have_reviewed_observation_layout():
    profile = resolve_reviewed_bootstrap_profile(ORIGINAL)
    previous = resolve_reviewed_bootstrap_profile(PREVIOUS)
    assert profile.profile_id == "wonderbane-1.3.38.11-6347b420"
    assert replace(profile, profile_id=previous.profile_id,
                   source_sha256=previous.source_sha256) == previous
    assert profile.source_length == 21143613
    for digest in (ORIGINAL, PREPARED):
        assert native_layout_is_compatible(PREVIOUS, digest)
    assert not native_layout_is_compatible(PREVIOUS, "ff" * 32)
    for digest in (PREPARED, "ff" * 32):
        with pytest.raises(BootstrapAuthoringError):
            resolve_reviewed_bootstrap_profile(digest)


def test_prepared_character_and_crest_readers_preserve_identity(tmp_path):
    memory = CharacterMemory(tmp_path)
    memory.executable_sha256 = PREPARED
    identity = NativeCharacterConfigReader(memory).observe()
    assert identity.character_name == "testercle"
    assert identity.server_name == "Wonderbane"
    crests = crest_fixture()
    crests.executable_sha256 = PREPARED
    observed = read_native_crest_lists(crests)
    assert observed["windows"][0]["entries"][0]["identities"]["nation"] == {
        "object_id": 12, "object_type": 23,
    }
    assert not observed["command_admitted"]
    assert not observed["server_acceptance_verified"]


@pytest.mark.parametrize("digest", [ORIGINAL, "ff" * 32])
def test_unprepared_or_unknown_client_cannot_enter_strict_readers(tmp_path, digest):
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
    backend = Backend()
    backend.executable_sha256 = digest
    with pytest.raises(NativeVendorDialogCompatibilityError):
        NativeCraftingTracer(backend)._validate()
    assert not backend.attached


def test_prepared_crafting_capture_still_requires_every_exact_signature():
    backend = Backend()
    backend.executable_sha256 = PREPARED
    NativeCraftingTracer(backend)._validate()
    assert not backend.attached
    for rva, signature in CRAFTING_BREAKPOINTS.values():
        address = backend.base_address + rva
        backend.memory[address] = bytes([signature[0] ^ 1]) + signature[1:]
        with pytest.raises(NativeVendorDialogCompatibilityError, match="signature mismatch"):
            NativeCraftingTracer(backend)._validate()
        backend.memory[address] = signature
    assert not backend.attached


def test_new_client_does_not_inherit_disposable_affix_qualification():
    record = crafting_result()
    record["executable_sha256"] = PREPARED
    assessed = assess_native_crafting_roll(record)
    assert assessed.disposition == RollDisposition.KEEP
    assert assessed.reason == "unknown_affix_preserved"
    assert assessed.suffix.tier is None
    assert not assessed.command_admitted
