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
