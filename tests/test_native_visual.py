import hashlib
import struct

import pytest

from shadowbane_lab.client_extension.native_visual import decode_visual, moonfire_tint


def sample():
    particle = bytearray(256)
    struct.pack_into("<I", particle, 0, 11)
    struct.pack_into("<I", particle, 224, 123)
    for i in range(5):
        struct.pack_into("<4f", particle, 96 + 16 * i, 1.0, 0.2, 0.1, i * 0.2)
    return struct.pack("<IfIf", 2, 3.0, 0, 0.25) + particle + struct.pack("<If", 1, 0.5) + bytes(56)


def test_tint_preserves_alpha_timing_binding_texture_and_other_effect():
    original = sample()
    candidate = moonfire_tint(
        original, source_sha256=hashlib.sha256(original).hexdigest(), effect_index=0
    )
    allowed = {16 + 96 + 16 * i + j for i in range(5) for j in range(12)}
    assert len(original) == len(candidate)
    assert all(
        a == b for i, (a, b) in enumerate(zip(original, candidate, strict=True)) if i not in allowed
    )
    assert candidate != original
    visual = decode_visual(candidate)
    assert visual.duration == 3.0
    assert visual.effects[0].attached_bone == 11
    assert visual.effects[0].texture_id == 123
    assert visual.effects[1].kind == "lightning"
    assert struct.unpack_from("<3f", candidate, 16 + 96 + 16) == (1.0, 1.0, 1.0)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        sample()[:-1],
        sample() + b"x",
        struct.pack("<If", 2048, 0),
        struct.pack("<IfIf", 1, 0, 9, 0),
        struct.pack("<If", 0, float("nan")),
    ],
)
def test_unknown_or_incomplete_layout_is_not_editable(payload):
    with pytest.raises(ValueError):
        decode_visual(payload)


def test_digest_effect_selection_and_color_are_checked():
    p = sample()
    digest = hashlib.sha256(p).hexdigest()
    for index in [-1, 2, True, 1]:
        with pytest.raises(ValueError):
            moonfire_tint(p, source_sha256=digest, effect_index=index)
    with pytest.raises(ValueError, match="digest"):
        moonfire_tint(p, source_sha256="0" * 64, effect_index=0)
    invalid = bytearray(p)
    struct.pack_into("<f", invalid, 16 + 96, float("nan"))
    with pytest.raises(ValueError, match="Nonfinite"):
        moonfire_tint(
            bytes(invalid), source_sha256=hashlib.sha256(invalid).hexdigest(), effect_index=0
        )


def test_geometry_layout_and_opaque_streams():
    body = bytearray(108)
    struct.pack_into("<II", body, 0, 500, 4)
    payload = struct.pack("<IfIf", 1, 2.0, 2, 0.0) + body
    effect = decode_visual(payload).effects[0]
    assert (effect.kind, effect.texture_id, effect.attached_bone) == ("geometry", 500, 4)
    with pytest.raises(ValueError):
        decode_visual(b"\x78\x9c\x01\xf3\x03\x0c\xfc\x78")
