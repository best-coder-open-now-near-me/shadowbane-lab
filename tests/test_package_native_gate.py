import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "package_builder", Path(__file__).parents[1] / "scripts/build_navigation_inspector_package.py"
)
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)


def results(tmp_path, status="run", failure=None, name=None):
    name = name or next(iter(builder.DIAGNOSTIC_TRANSPARENCY_FAILURES))
    suite = ET.Element("testsuite")
    case = ET.SubElement(suite, "testcase", name=name, status=status)
    if failure:
        ET.SubElement(case, failure)
    ET.SubElement(case, "system-out").text = "expected RGB differs from actual RGB"
    path = tmp_path / "native.xml"
    ET.ElementTree(suite).write(path)
    return path, {name}


def test_default_acceptance_rejects_known_transparency_failure(tmp_path):
    path, required = results(tmp_path, "fail", "failure")
    with pytest.raises(RuntimeError, match="failed"):
        builder.validate_native_results(path, required, diagnostic=False, exit_code=8)


def test_diagnostic_preserves_exact_known_failure(tmp_path):
    path, required = results(tmp_path, "fail", "failure")
    failures = builder.validate_native_results(path, required, diagnostic=True, exit_code=8)
    assert failures == [{"test": next(iter(required)), "status": "failed",
                         "detail": "expected RGB differs from actual RGB"}]


@pytest.mark.parametrize("case", ["unrelated", "skipped", "missing", "error", "duplicate", "exit"])
def test_diagnostic_cannot_bypass_other_gate_failures(tmp_path, case):
    path, required = results(tmp_path)
    suite = ET.parse(path).getroot()
    test = suite[0]
    code = 0
    if case == "unrelated":
        test.set("name", "runtime_lifetime")
        ET.SubElement(test, "failure")
        code = 8
    elif case in ("skipped", "error"):
        ET.SubElement(test, case)
    elif case == "missing":
        suite.remove(test)
    elif case == "duplicate":
        ET.SubElement(suite, "testcase", name=next(iter(required)), status="run")
    else:
        code = 8
    ET.ElementTree(suite).write(path)
    with pytest.raises(RuntimeError):
        builder.validate_native_results(path, required, diagnostic=True, exit_code=code)


@pytest.mark.parametrize("name", [
    "wonderbane_extension_selected_cue_runtime",
    "wonderbane_extension_selected_cue_native_material",
    "wonderbane_extension_effects_runtime",
])
@pytest.mark.parametrize("diagnostic", [False, True])
def test_required_runtime_failures_cannot_be_waived(tmp_path, name, diagnostic):
    path, required = results(tmp_path, "fail", "failure", name)
    with pytest.raises(RuntimeError, match="failed"):
        builder.validate_native_results(path, required, diagnostic=diagnostic, exit_code=8)


@pytest.mark.parametrize("outcome", ["pass", "missing", "skipped", "failure", "error", "duplicate"])
def test_profile_ipc_must_execute_once_and_pass(tmp_path, outcome):
    profile_name = "test_profile_configuration_crosses_real_native_channel_atomically"
    assert profile_name in builder.REQUIRED_MOVEMENT_IPC_TESTS
    suite = ET.Element("testsuite")
    for name in builder.REQUIRED_MOVEMENT_IPC_TESTS:
        if name == profile_name and outcome == "missing":
            continue
        case = ET.SubElement(suite, "testcase", name=name)
        if name == profile_name and outcome in ("skipped", "failure", "error"):
            ET.SubElement(case, outcome)
    if outcome == "duplicate":
        ET.SubElement(suite, "testcase", name=profile_name)
    path = tmp_path / "movement-ipc.xml"
    ET.ElementTree(suite).write(path)
    if outcome == "pass":
        builder.validate_movement_ipc_results(path, "test-profile")
    else:
        with pytest.raises(RuntimeError, match="required native movement IPC"):
            builder.validate_movement_ipc_results(path, "test-profile")


@pytest.mark.parametrize("name", sorted(builder.REQUIRED_TARGETED_ACTION_TESTS))
@pytest.mark.parametrize("outcome", ["pass", "missing", "skipped", "failure", "error", "duplicate"])
def test_targeted_action_gates_must_execute_once(tmp_path, name, outcome):
    suite = ET.Element("testsuite")
    for required in builder.REQUIRED_TARGETED_ACTION_TESTS:
        if required == name and outcome == "missing":
            continue
        case = ET.SubElement(suite, "testcase", name=required, status="run")
        if required == name and outcome in ("skipped", "failure", "error"):
            ET.SubElement(case, outcome)
    if outcome == "duplicate":
        ET.SubElement(suite, "testcase", name=name, status="run")
    path = tmp_path / "targeted-action.xml"
    ET.ElementTree(suite).write(path)
    required = set(builder.REQUIRED_TARGETED_ACTION_TESTS)
    if outcome == "pass":
        assert builder.validate_native_results(path, required, diagnostic=False, exit_code=0) == []
    else:
        with pytest.raises(RuntimeError):
            builder.validate_native_results(path, required, diagnostic=False, exit_code=0)


@pytest.mark.parametrize(
    "name", sorted(builder.REQUIRED_VENDOR_TESTS | builder.REQUIRED_GUARD_TESTS),
)
@pytest.mark.parametrize("outcome", ["pass", "missing", "skipped", "failure", "error", "duplicate"])
def test_vendor_gates_must_execute_once(tmp_path, name, outcome):
    suite = ET.Element("testsuite")
    for required in builder.REQUIRED_VENDOR_TESTS | builder.REQUIRED_GUARD_TESTS:
        if required == name and outcome == "missing":
            continue
        case = ET.SubElement(suite, "testcase", name=required, status="run")
        if required == name and outcome in ("skipped", "failure", "error"):
            ET.SubElement(case, outcome)
    if outcome == "duplicate":
        ET.SubElement(suite, "testcase", name=name, status="run")
    path = tmp_path / "vendor.xml"
    ET.ElementTree(suite).write(path)
    required = set(builder.REQUIRED_VENDOR_TESTS | builder.REQUIRED_GUARD_TESTS)
    if outcome == "pass":
        assert builder.validate_native_results(path, required, diagnostic=False, exit_code=0) == []
    else:
        with pytest.raises(RuntimeError):
            builder.validate_native_results(path, required, diagnostic=False, exit_code=0)
