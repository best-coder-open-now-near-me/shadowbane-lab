"""Keep exact client updates separate from generic layout and affix qualification."""
from unittest.mock import Mock, patch

import pytest

from shadowbane_lab.client_extension.vendor_batch import VendorBatchStopped
from shadowbane_lab.client_observation.native_nearby_vendor_roster import (
    read_native_nearby_vendor_roster,
)
from shadowbane_lab.client_observation.native_vendor_dialog import (
    NativeVendorDialogCompatibilityError,
)
from shadowbane_lab.client_observation.native_vendor_queue import read_native_vendor_queue
from shadowbane_lab.client_observation.native_vendor_roster import read_native_vendor_roster
from shadowbane_lab.client_observation.reviewed_vendor_builds import REVIEWED_VENDOR_EXECUTABLES
from shadowbane_lab.manager.vendor_discovery import _memory
from tests.test_native_nearby_vendor_roster import nearby_fixture
from tests.test_native_vendor_queue import fixture
from tests.test_native_vendor_roster import roster_fixture


@pytest.mark.parametrize("digest", sorted(REVIEWED_VENDOR_EXECUTABLES))
def test_reviewed_vendor_readers_and_discovery_preserve_identity(digest):
    for factory, reader in ((fixture, read_native_vendor_queue),
                            (roster_fixture, read_native_vendor_roster),
                            (nearby_fixture, read_native_nearby_vendor_roster)):
        memory = factory()
        expected = reader(memory)
        memory.executable_sha256 = digest
        result = reader(memory)
        # Only evidence attribution changes; copied owner/queue payloads stay equal.
        if "executable_sha256" in expected:
            expected["executable_sha256"] = digest
        assert result == expected
    binding = Mock(game_process_id=988, game_process_started_at_100ns=100)
    memory = Mock(executable_sha256=digest, process_creation_filetime_utc=100)
    with patch(
        "shadowbane_lab.manager.vendor_discovery.WindowsReadOnlyProcessMemory.open_for_process",
        return_value=memory,
    ):
        assert _memory(binding) is memory
        memory.process_creation_filetime_utc = 101
        with pytest.raises(VendorBatchStopped, match="identity or build changed"):
            _memory(binding)
        memory.close.assert_called_once()


@pytest.mark.parametrize("digest", ["ff" * 32,
    "55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc",
    "ac9ca46467997667d49b85cd6076954813a72b56f71e2ad85a4085f3a9f391ca",
    "a32275aabab8d5955f4d45adde6e84a666f44be54c951ccf8dc2d538237e8be4",
    "cae5311b5b6134bf25155b16c70b1743c1216c0bd0c88f1240d7e92388211d26"])
def test_unknown_generic_family_and_unprepared_builds_cannot_admit_vendor_reads(digest):
    for factory, reader in ((fixture, read_native_vendor_queue),
                            (roster_fixture, read_native_vendor_roster),
                            (nearby_fixture, read_native_nearby_vendor_roster)):
        memory = factory()
        memory.executable_sha256 = digest
        with pytest.raises(NativeVendorDialogCompatibilityError):
            reader(memory)
        assert not memory.reads
