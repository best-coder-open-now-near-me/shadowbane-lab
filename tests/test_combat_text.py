"""Localization lookup identity and source qualification regressions."""

import hashlib

import pytest

from shadowbane_lab.client_extension import combat_text


def test_unreviewed_resource_is_rejected():
    with pytest.raises(ValueError, match="reviewed official"):
        combat_text.compile_combat_text(b"modified resource")


def test_changes_only_translation_values_and_preserves_utf16(monkeypatch):
    rows = [f'"{key}" "{key.removeprefix("Power:")}"' for key in combat_text.replacements()]
    rows.append('"UnrelatedKey" "Unrelated value"')
    original = ("\ufeff" + "\r\n".join(rows) + "\r\n").encode("utf-16le")
    monkeypatch.setattr(combat_text, "DATA_STRING_SHA256", hashlib.sha256(original).hexdigest())
    result = combat_text.compile_combat_text(original)
    assert result.startswith(b"\xff\xfe")
    text = result.decode("utf-16")
    assert text.endswith('"UnrelatedKey" "Unrelated value"\r\n')
    assert len(text.splitlines()) == len(rows)
    for key, value in combat_text.replacements().items():
        assert f'"{key}" "{value}"' in text
        assert value.count("\\n") == 1
        assert "%DAMAGEVAL%" in value
        assert "%TARGETNAME%" in value or "-> You" in value


def test_missing_translation_is_rejected_even_with_reviewed_digest(monkeypatch):
    original = b"\xff\xfe" + '"other" "value"'.encode("utf-16le")
    monkeypatch.setattr(combat_text, "DATA_STRING_SHA256", hashlib.sha256(original).hexdigest())
    with pytest.raises(ValueError, match="exactly one"):
        combat_text.compile_combat_text(original)
