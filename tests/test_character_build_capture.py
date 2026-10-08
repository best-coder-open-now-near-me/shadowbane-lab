import struct
from unittest.mock import patch

import pytest
from test_native_character_session import setup_session

from shadowbane_lab.character_capture import build as b


def fixture(tmp_path):
    m, session = setup_session(tmp_path)
    def words(a, *values):
        m.put(a, struct.pack("<" + "I" * len(values), *values))
    words(m.player + 0xBA8, *([0] * 19))
    head = 0x21000000
    words(m.player + 0xBF4, head, 0)
    words(head, 0, 0, head, head)
    sh = head + 256
    nodes = [sh + 256 + i * 64 for i in range(5)]
    words(m.player + 0xCB0, sh, 5)
    words(sh, 0, nodes[0], nodes[0], nodes[-1])
    for i, (node, token) in enumerate(zip(nodes, sorted(b.STAT_NAMES), strict=True)):
        words(node, 0, nodes[i-1] if i else sh, 0, nodes[i+1] if i < 4 else 0,
              token, 95, 100, 0, 0, 150, 0xFFFFFFFB)
    item = 0x22000000
    words(m.player + 0xBA8 + 4, item)
    words(item, m.base_address + 0x1142748)
    words(item + 0x10, 100, 0, 200, 30)
    words(item + 0xD8, 0, 0, 0, 0)
    m.put(item + 0x5CC, struct.pack("<ff", 20, 30))
    words(item + 0x6B8, 1)
    words(item + 0x744, 7)
    words(item + 0x58C, 0, 0, 0)
    with patch.object(b, "verify_build_image"):
        reader = b.NativeCharacterBuildReader(session)
    return m, reader, words, item, head, nodes


def test_current_slots_stats_and_distinct_stack_charges(tmp_path):
    m, reader, words, item, *_ = fixture(tmp_path)
    result = reader.observe()
    assert len(result["equipment"]) == 19
    assert result["equipment"][1]["item"]["stack_quantity"] == 1
    assert result["equipment"][1]["item"]["charges_remaining"] == 7
    assert result["attributes"][0]["wire_adjustment"] == -5
    words(m.player + 0xBA8 + 4, 0)
    assert reader.observe()["equipment"][1]["item"] is None


def test_applied_runes_come_from_current_tree(tmp_path):
    m, reader, words, _, head, _ = fixture(tmp_path)
    node, rune = 0x23000000, 0x23001000
    words(m.player + 0xBF4, head, 1)
    words(head, 0, node, node, node)
    words(node, 0, head, 0, 0, 4, rune)
    words(rune, m.base_address + 0x1143278)
    words(rune + 0x10, 3001, 0, 9001, 13)
    assert reader.observe()["applied_runes"] == [
        {"role": "discipline", "role_id": 4, "template_id": 3001, "object_key": [9001, 13]}
    ]


def test_item_effect_token_and_rank(tmp_path):
    m, reader, words, item, *_ = fixture(tmp_path)
    vector, effect, definition = 0x24000000, 0x24001000, 0x24002000
    words(item + 0x58C, vector, vector + 8, vector + 8)
    words(vector, 123, effect)
    words(effect, definition)
    words(effect + 0x10, 20, definition + 0x5C)
    words(definition, m.base_address + 0x1147930)
    words(definition + 0x14, 123)
    assert reader.observe()["equipment"][1]["item"]["effects"] == [{"token": 123, "rank": 20}]


@pytest.mark.parametrize("fault", ["cycle", "count", "parent", "vtable", "nan",
                                   "vector", "duplicate", "stat", "short", "changed"])
def test_invalid_or_changing_records_are_rejected(tmp_path, fault):
    m, reader, words, item, head, nodes = fixture(tmp_path)
    if fault == "cycle":
        words(nodes[-1] + 12, nodes[0])
    elif fault == "count":
        words(m.player + 0xCB4, 6)
    elif fault == "parent":
        words(nodes[1] + 4, head)
    elif fault == "vtable":
        words(item, m.base_address + 0x1143278)
    elif fault == "nan":
        m.put(item + 0x5CC, struct.pack("<f", float("nan")))
    elif fault == "vector":
        words(item + 0x58C, 0, 8, 8)
    elif fault == "duplicate":
        words(m.player + 0xBA8 + 8, item)
    elif fault == "stat":
        words(nodes[0] + 16, 0)
    elif fault == "short":
        del m.memory[item + 0x744]
    elif fault == "changed":
        original = m.read
        calls = 0
        def changing(a, n):
            nonlocal calls
            if a == item + 0x744:
                calls += 1
                if calls > 1:
                    words(a, 8)
            return original(a, n)
        m.read = changing
    with pytest.raises(b.BuildReadError):
        reader.observe()


def test_unreviewed_image_cannot_enable_reader(tmp_path):
    m, session = setup_session(tmp_path)
    with pytest.raises(ValueError):
        b.verify_build_image(m.executable_path, m.executable_sha256)
