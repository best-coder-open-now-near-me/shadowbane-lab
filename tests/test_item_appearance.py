import hashlib
import struct
import zlib

import pytest

from shadowbane_lab.client_extension.item_appearance import (
    build_item_appearance_cache,
    redirect_item_render,
)
from shadowbane_lab.world_data.cache import CacheArchive


def item(name, render, kind=9, scale=1.0):
    return (
        struct.pack("<III", 0x434C4E54, kind, len(name))
        + name.encode("utf-16le")
        + struct.pack("<B2f3fII", 0, 1, 100, scale, scale, scale, 0, render)
        + b"gameplay-and-animation-tail"
    )


def archive(path, rows):
    data = bytearray(16 + len(rows) * 20)
    for i, (key, payload) in enumerate(rows):
        stored = zlib.compress(payload)
        struct.pack_into("<IIIII", data, 16 + i * 20, *key, len(data), len(payload), len(stored))
        data.extend(stored)
    struct.pack_into("<IIII", data, 0, len(rows), 16 + len(rows) * 20, len(data), 0)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def test_redirect_preserves_every_other_byte():
    a, b = item("sword", 11), item("katana", 22)
    result = redirect_item_render(a, b)
    assert result == item("sword", 22)
    assert len(result) == len(a)


@pytest.mark.parametrize(
    "donor", [item("x", 22, kind=3), item("x", 22, scale=2), item("x", 0), b"bad"]
)
def test_reject_incompatible_donor(donor):
    with pytest.raises(ValueError):
        redirect_item_render(item("a", 11), donor)


def test_candidate_preserves_untargeted_and_source(tmp_path):
    source, output = tmp_path / "source.cache", tmp_path / "candidate.cache"
    rows = [((0, 1), item("a", 11)), ((0, 2), item("b", 22)), ((0, 3), b"opaque data")]
    digest = archive(source, rows)
    receipt = build_item_appearance_cache(
        source, output, source_sha256=digest, target_key=(0, 1), donor_key=(0, 2)
    )
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    assert receipt["verified_resources"] == 3
    with CacheArchive(output) as c:
        target = c.entries[0]
        assert target.is_compressed
        stored = output.read_bytes()[target.data_offset : target.data_offset + target.stored_size]
        # Model the native loader, which calls zlib for this resource even when
        # a permissive archive reader would accept equal stored/raw lengths.
        assert zlib.decompress(stored) == item("a", 22)
        assert [c.read_resource(e) for e in c.entries] == [item("a", 22), rows[1][1], rows[2][1]]
    with pytest.raises(FileExistsError):
        build_item_appearance_cache(
            source, output, source_sha256=digest, target_key=(0, 1), donor_key=(0, 2)
        )
    with pytest.raises(ValueError, match="digest"):
        build_item_appearance_cache(
            source, tmp_path / "bad", source_sha256="0" * 64, target_key=(0, 1), donor_key=(0, 2)
        )
    with pytest.raises(FileExistsError):
        build_item_appearance_cache(
            source, source, source_sha256=digest, target_key=(0, 1), donor_key=(0, 2)
        )


def test_failure_removes_only_new_candidate(tmp_path):
    source, output = tmp_path / "source.cache", tmp_path / "candidate.cache"
    # Corrupt an untargeted compressed resource; the builder must reject the whole cache.
    digest = archive(
        source, [((0, 1), item("a", 11)), ((0, 2), item("b", 22)), ((0, 3), b"untargeted" * 10)]
    )
    raw = bytearray(source.read_bytes())
    raw[-1] ^= 255
    source.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):
        build_item_appearance_cache(
            source, output, source_sha256=digest, target_key=(0, 1), donor_key=(0, 2)
        )
    assert not output.exists()
    assert source.read_bytes() == raw
