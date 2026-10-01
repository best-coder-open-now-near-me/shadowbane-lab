from dataclasses import replace
from pathlib import Path

import pytest

from shadowbane_lab.client_extension.actor_selector_manifest import Manifest, Selector

FIXTURE = Path(__file__).parent / "fixtures" / "actor_selector_manifest_v1.hex"


def manifest():
    return Manifest.decode(bytes.fromhex(FIXTURE.read_text()))


def test_cross_language_manifest_golden_round_trip():
    value = manifest()
    assert value.encode() == bytes.fromhex(FIXTURE.read_text())
    assert len(value.encode()) == 1152
    assert value.selectors[0].template_id == 980066
    assert value.selectors[0].coverage_power_id == 429021400


def test_semantic_group_identity_survives_producer_and_manifest_reordering():
    first = manifest()
    changed = replace(first, producer_pid=987, producer_creation=3456,
        selectors=(replace(first.selectors[2], index=0, group=0),
                   replace(first.selectors[1], index=1, group=0),
                   replace(first.selectors[0], index=2, group=1)))
    assert changed.digest != first.digest
    assert changed.group_digest(0) == first.group_digest(1)
    assert changed.group_digest(1) == first.group_digest(0)
    assert first.group_digest(0) != first.group_digest(1)


@pytest.mark.parametrize("offset", [8, 12, 120, 128+20, 128+3*32])
def test_corrupt_header_template_and_unused_records_are_rejected(offset):
    payload = bytearray(manifest().encode())
    payload[offset] ^= 1
    with pytest.raises(ValueError):
        Manifest.decode(bytes(payload))


def test_duplicate_power_cannot_hide_in_another_group():
    value = manifest()
    with pytest.raises(ValueError, match="duplicate"):
        replace(value, selectors=value.selectors + (
            replace(value.selectors[1], index=3, group=0),)).encode()


def test_incomplete_and_noncanonical_manifest_rejected():
    value = manifest()
    for altered in (replace(value, group_count=3), replace(value, selectors=()),
                    replace(value, selectors=(replace(value.selectors[0], index=1),))):
        with pytest.raises(ValueError):
            altered.encode()
    with pytest.raises(ValueError):
        Selector(0, 0, 4, 1, 980066, 429021400, 0).encode()
