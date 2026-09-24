"""CLI integration uses the real bounded reader and a synthetic process image."""
from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from shadowbane_lab.cli import main
from shadowbane_lab.client_observation.native_health import WindowsReadOnlyProcessMemory
from tests.test_native_vendor_recipe_catalog import recipe_fixture


@pytest.mark.parametrize("fail", [False, True])
def test_recipe_list_cli_closes_exact_process_and_reports_reader_failure(fail, capsys):
    memory = recipe_fixture()
    memory.close = Mock()
    if fail:
        memory.executable_sha256 = "0" * 64
    with patch.object(WindowsReadOnlyProcessMemory, "open_for_process",
                      return_value=memory) as opened:
        status = main(["client", "observe-native-vendor-recipes",
                       "--process-id", "988", "--json"])
    opened.assert_called_once_with("sb.exe", 988)
    memory.close.assert_called_once_with()
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is (not fail)
    assert (status == 0) is (not fail)
    if not fail:
        snapshot = result["snapshot"]
        assert snapshot["command_admitted"] is False
        assert len(snapshot["recipes"]) >= 2
        assert all(row["template"]["object_type"] == 0 for row in snapshot["recipes"])
        assert len({row["template"]["object_id"] for row in snapshot["recipes"]}) == len(
            snapshot["recipes"]
        )


def test_recipe_list_cli_text_displays_actual_names_and_typed_keys(capsys):
    from shadowbane_lab.client_observation.native_vendor_recipe_catalog import (
        read_native_vendor_recipe_catalog,
    )
    expected = read_native_vendor_recipe_catalog(recipe_fixture())
    memory = recipe_fixture()
    memory.close = Mock()
    with patch.object(WindowsReadOnlyProcessMemory, "open_for_process", return_value=memory):
        assert main(["client", "observe-native-vendor-recipes", "--process-id", "988"]) == 0
    text = capsys.readouterr().out
    for row in expected["recipes"]:
        assert row["display_name"] in text
        assert f"[{row['template']['object_id']}:0]" in text
    assert "Current list only" in text
    memory.close.assert_called_once_with()


def test_recipe_list_cli_reports_attachment_failure(capsys):
    with patch.object(WindowsReadOnlyProcessMemory, "open_for_process",
                      side_effect=OSError("process exited")):
        assert main(["client", "observe-native-vendor-recipes", "--process-id", "988",
                     "--json"]) != 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert "process exited" in str(result)
