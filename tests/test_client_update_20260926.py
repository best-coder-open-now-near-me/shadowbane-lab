"""Exact September 26 client support must not broaden command or affix admission."""
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

ORIGINAL = "3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7"
PREPARED = "2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289"
PREVIOUS = "6347b420c6c151995f168f16fd1624408dd8911698d11a4a74b26d211fb49f19"


def test_original_has_exact_bootstrap_layout_and_both_images_have_reviewed_observation_layout():
    profile = resolve_reviewed_bootstrap_profile(ORIGINAL)
    previous = resolve_reviewed_bootstrap_profile(PREVIOUS)
    assert profile.profile_id == "wonderbane-1.3.38.12-3891fcab"
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


@pytest.mark.parametrize("digest", [PREPARED,
    "7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f"])
def test_recipe_catalog_keeps_qualified_menu_ownership_on_each_exact_build(digest):
    from shadowbane_lab.client_observation.native_vendor_recipe_catalog import (
        read_native_vendor_recipe_catalog,
    )
    from tests.test_native_vendor_recipe_catalog import recipe_fixture
    memory = recipe_fixture()
    memory.executable_sha256 = digest
    result = read_native_vendor_recipe_catalog(memory)
    assert result["recipe_count"] == 2
    assert result["retained_template"] == result["activated_template"]
    assert not result["command_admitted"] and not result["complete_server_catalog_verified"]


@pytest.mark.parametrize("digest", [ORIGINAL, "ff" * 32,
    "761f375e422332cac2512398bb935af38b30267b9b3a7a5cede9f87e98982442"])
def test_catalog_does_not_inherit_unreviewed_recipe_graphs(digest):
    from shadowbane_lab.client_observation.native_vendor_recipe_catalog import (
        read_native_vendor_recipe_catalog,
    )
    from tests.test_native_vendor_recipe_catalog import recipe_fixture
    memory = recipe_fixture()
    memory.executable_sha256 = digest
    with pytest.raises(NativeVendorDialogCompatibilityError):
        read_native_vendor_recipe_catalog(memory)
    assert not memory.reads


@pytest.mark.parametrize("digest,allowed", [(PREPARED, True), (ORIGINAL, False),
    ("7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f", True),
    ("ff" * 32, False)])
def test_saved_recipe_context_rechecks_build_and_character_without_command_admission(
        tmp_path, monkeypatch, digest, allowed):
    import struct
    from types import SimpleNamespace

    from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
    from shadowbane_lab.manager.vendor_recipes import read_context
    memory = CharacterMemory(tmp_path)
    memory.executable_sha256 = digest
    memory.put(memory.player + 0x18, struct.pack("<II", 123, 53))
    monkeypatch.setattr(
        "shadowbane_lab.manager.vendor_recipes.WindowsReadOnlyProcessMemory.open_for_process",
        lambda *args: memory,
    )
    binding = SimpleNamespace(game_process_id=memory.pid,
                              game_process_started_at_100ns=memory.process_creation_filetime_utc)
    if allowed:
        owner, catalog = read_context(binding)
        assert owner == dict(character="testercle", server="Wonderbane", key=[123, 53])
        assert catalog is None
    else:
        with pytest.raises(VendorBatchStopped, match="lifetime or image changed"):
            read_context(binding)
        assert not memory.reads
    assert memory.closed
