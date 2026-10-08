"""Release marker checks must not confuse content identity with runtime readiness."""

import hashlib
import json
from dataclasses import replace

import pytest

from shadowbane_lab import cli
from shadowbane_lab.cli_commands import client_inspection
from shadowbane_lab.client_extension import distribution as subject
from shadowbane_lab.client_extension.bootstrap_author import WONDERBANE_1_3_38_14_PROFILE
from shadowbane_lab.client_observation.build_compatibility import native_layout_is_compatible
from shadowbane_lab.integrity import FileRecord


@pytest.fixture
def baseline(tmp_path):
    (tmp_path / "cache").mkdir()
    files = {}
    for name, data in (("sb.exe", b"official"), ("cache/CObjects.cache", b"objects")):
        (tmp_path / name).write_bytes(data)
        files[name] = FileRecord(name, len(data), hashlib.sha256(data).hexdigest())
    return replace(
        subject.WONDERBANE_BASELINE,
        official_executable=files["sb.exe"],
        prepared_executable=FileRecord("sb.exe", 8, hashlib.sha256(b"prepared").hexdigest()),
        objects_cache=files["cache/CObjects.cache"],
    )


def inspect(tmp_path, baseline, variant="official"):
    return subject.inspect_distribution(tmp_path, variant=variant, baseline=baseline)


def test_exact_markers_are_read_only_and_do_not_qualify_runtime(tmp_path, baseline):
    settings = tmp_path / "ArcanePref.cfg"
    settings.write_bytes(b"user settings")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    report = inspect(tmp_path, baseline)
    assert report["markers_match"] is True
    assert report["scope"] == "executable_and_objects_cache_only"
    assert {"extension_package", "server_compatibility", "live_capabilities"} <= set(
        report["not_evaluated"]
    )
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("name", ["sb.exe", "cache/CObjects.cache"])
@pytest.mark.parametrize("damage", ["missing", "same_size", "larger", "directory"])
def test_changed_or_missing_content_fails_closed(tmp_path, baseline, name, damage):
    path = tmp_path / name
    original = path.read_bytes()
    path.unlink()
    if damage == "same_size":
        path.write_bytes(b"x" * len(original))
    elif damage == "larger":
        path.write_bytes(original + b"x")
    elif damage == "directory":
        path.mkdir()
    report = inspect(tmp_path, baseline)
    assert report["markers_match"] is False
    check = next(c for c in report["checks"] if c["expected"]["relative_path"] == name)
    expected = {"missing": "unreadable", "same_size": "hash_mismatch",
                "larger": "size_mismatch", "directory": "unreadable"}
    assert check["status"] == expected[damage]


def test_variants_are_not_interchangeable(tmp_path, baseline):
    assert inspect(tmp_path, baseline, "prepared")["markers_match"] is False
    (tmp_path / "sb.exe").write_bytes(b"prepared")
    assert inspect(tmp_path, baseline, "prepared")["markers_match"] is True
    assert inspect(tmp_path, baseline)["markers_match"] is False
    with pytest.raises(ValueError, match="variant"):
        inspect(tmp_path, baseline, "automatic")


def test_mutation_after_first_hash_invalidates_entire_inspection(tmp_path, baseline, monkeypatch):
    original_hash = subject.hash_file

    def changing_hash(path, **kwargs):
        result = original_hash(path, **kwargs)
        if path.name == "CObjects.cache":
            (tmp_path / "sb.exe").write_bytes(b"changed after hashing")
        return result

    monkeypatch.setattr(subject, "hash_file", changing_hash)
    report = inspect(tmp_path, baseline)
    assert report["markers_match"] is False
    assert report["checks"][0]["status"] == "changed_during_inspection"


def test_unreadable_file_does_not_abort_remaining_checks(tmp_path, baseline, monkeypatch):
    original_hash = subject.hash_file

    def denied_hash(path, **kwargs):
        if path.name == "sb.exe":
            raise PermissionError("denied")
        return original_hash(path, **kwargs)

    monkeypatch.setattr(subject, "hash_file", denied_hash)
    report = inspect(tmp_path, baseline)
    assert report["markers_match"] is False
    assert report["checks"][0]["status"] == "unreadable"
    assert report["checks"][1]["status"] == "matched"


def test_cache_indirection_is_rejected(tmp_path, baseline, monkeypatch):
    from shadowbane_lab.integrity import paths

    original = paths.is_reparse_point
    monkeypatch.setattr(paths, "is_reparse_point", lambda p: p.name == "cache" or original(p))
    assert inspect(tmp_path, baseline)["checks"][1]["status"] == "unreadable"


def test_bundled_executables_have_existing_reviewed_adapter_support():
    baseline = subject.WONDERBANE_BASELINE
    assert baseline.official_executable.sha256 == WONDERBANE_1_3_38_14_PROFILE.source_sha256
    assert native_layout_is_compatible(
        baseline.official_executable.sha256, baseline.prepared_executable.sha256,
    )


@pytest.mark.parametrize("matches", [False, True])
def test_cli_reports_marker_result_with_exit_status(
    tmp_path, baseline, monkeypatch, capsys, matches,
):
    if not matches:
        (tmp_path / "cache/CObjects.cache").unlink()
    monkeypatch.setattr(
        client_inspection, "inspect_distribution",
        lambda directory, variant: inspect(directory, baseline, variant),
    )
    result = cli.main([
        "client", "inspect-distribution", str(tmp_path), "--variant", "official", "--json",
    ])
    assert result == (0 if matches else 2)
    report = json.loads(capsys.readouterr().out)
    assert report["markers_match"] is matches
    assert "server_compatibility" in report["not_evaluated"]


def test_cli_missing_directory_is_json_failure(tmp_path, capsys):
    result = cli.main([
        "client", "inspect-distribution", str(tmp_path / "absent"),
        "--variant", "official", "--json",
    ])
    assert result == 2
    assert json.loads(capsys.readouterr().out)["markers_match"] is False
