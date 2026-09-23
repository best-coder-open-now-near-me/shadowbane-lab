"""Mutation tests for the narrow CI diagnostic policy, using observed native output."""

import importlib.util
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = importlib.util.spec_from_file_location(
    "transparency_gate", Path(__file__).parents[1] / "scripts/check_transparency_diagnostics.py"
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

# Captured from the existing native full-profile probes on NVIDIA GL 4.6.0.
FIXTURES = Path(__file__).parent / "fixtures/native_transparency"
EFFECT_OUTPUT = (FIXTURES / "effects.txt").read_text(encoding="utf-8")
CUE_OUTPUT = (FIXTURES / "cue.txt").read_text(encoding="utf-8")


def report(path, *, cue_skip=False):
    suite = ET.Element("testsuite")
    for name, output in ((gate.EFFECTS, EFFECT_OUTPUT), (gate.CUE, CUE_OUTPUT)):
        skip = cue_skip and name == gate.CUE
        case = ET.SubElement(suite, "testcase", name=name, status="notrun" if skip else "fail")
        ET.SubElement(case, "skipped" if skip else "failure",
                      message="SKIP_RETURN_CODE=77" if skip else "Failed")
        ET.SubElement(case, "system-out").text = gate.FBO_SKIP + "\n" if skip else output
    ET.ElementTree(suite).write(path)
    return suite


def save(path, root):
    ET.ElementTree(root).write(path)


@pytest.mark.parametrize("cue_skip", [False, True])
def test_reviewed_counterexamples_and_exact_environment_skip(tmp_path, cue_skip):
    path = tmp_path / "results.xml"
    report(path, cue_skip=cue_skip)
    summaries = gate.validate_results(path, 8)
    assert "2 reviewed counterexamples" in summaries[0]
    assert ("environment skip" if cue_skip else "2 reviewed counterexamples") in summaries[1]


@pytest.mark.parametrize("name,output", [(gate.EFFECTS, EFFECT_OUTPUT), (gate.CUE, CUE_OUTPUT)])
@pytest.mark.parametrize("mutation", ["extra_assertion", "extra_known_assertion", "missing_case",
                                     "duplicate_case", "changed_case", "missing_fixture",
                                     "duplicate_fixture", "truncated", "bad_error"])
def test_known_test_cannot_hide_additional_failures(name, output, mutation):
    rows = output.splitlines()
    sample_prefix = "Native transparency requirement:" if name == gate.EFFECTS else "native alpha="
    index = next(i for i, line in enumerate(rows) if line.startswith(sample_prefix))
    if mutation == "extra_assertion":
        rows.append("no GL state errors")
    elif mutation == "extra_known_assertion":
        rows.append(rows[0])
    elif mutation == "missing_case":
        rows.pop(index)
    elif mutation == "duplicate_case":
        rows.append(rows[index])
    elif mutation == "changed_case":
        rows[index] = rows[index].replace("0,0,255", "25,25,25").replace("116,31,37", "25,25,25")
    elif mutation == "missing_fixture":
        rows.pop()
    elif mutation == "duplicate_fixture":
        rows.append(rows[-1])
    elif mutation == "truncated":
        rows = rows[:3]
    else:
        rows[index] = rows[index].replace("254/765", "1/765").replace("131,16,19", "999,16,19")
    with pytest.raises(ValueError):
        gate.classify_output(name, "\n".join(rows))


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "error", "crash",
                                     "status", "extra_failure", "extra_output", "stderr",
                                     "skip_effects", "unknown_skip", "skip_failure",
                                     "disabled_skip", "exit"])
def test_report_inconsistencies_fail(tmp_path, mutation):
    path = tmp_path / "results.xml"
    root = report(path)
    case = root[0]
    code = 8
    if mutation == "missing":
        root.remove(case)
    elif mutation == "duplicate":
        root.append(ET.fromstring(ET.tostring(case)))
    elif mutation == "unknown":
        case.set("name", "unexpected_new_stretch_test")
    elif mutation == "error":
        ET.SubElement(case, "error")
    elif mutation == "crash":
        case.find("failure").set("message", "Exception: Access violation")
    elif mutation == "status":
        case.set("status", "notrun")
    elif mutation == "extra_failure":
        ET.SubElement(case, "failure", message="Failed")
    elif mutation == "extra_output":
        ET.SubElement(case, "system-out").text = "other failure"
    elif mutation == "stderr":
        ET.SubElement(case, "system-err").text = "other failure"
    elif mutation.startswith("skip") or mutation in {"unknown_skip", "disabled_skip"}:
        case = root[0] if mutation == "skip_effects" else root[1]
        case.set("status", "notrun")
        ET.SubElement(case, "skipped", message="Disabled" if mutation == "disabled_skip"
                      else "SKIP_RETURN_CODE=77")
        if mutation != "skip_failure":
            case.remove(case.find("failure"))
        case.find("system-out").text = (
            "SKIP: unknown reason" if mutation == "unknown_skip" else gate.FBO_SKIP
        )
    else:
        code = 1
    save(path, root)
    with pytest.raises(ValueError):
        gate.validate_results(path, code)


def test_fixed_cases_can_pass_without_retaining_expected_failures(tmp_path):
    path = tmp_path / "results.xml"
    root = report(path)
    for case in root:
        output = case.find("system-out")
        output.text = "\n".join(line for line in output.text.splitlines()
                                if line not in {gate.EFFECT_ASSERTION, gate.CUE_ASSERTION})
        output.text = output.text.replace("late-pass RGB=0,0,255 absolute error=254/765 UNRESOLVED",
                                          "late-pass RGB=127,0,128 absolute error=0/765 PASS")
        output.text = output.text.replace("late-pass RGB=127,0,0 absolute error=128/765 UNRESOLVED",
                                          "late-pass RGB=127,0,128 absolute error=0/765 PASS")
        output.text = output.text.replace("actual_rgb=116,31,37", "actual_rgb=131,16,19")
        output.text = output.text.replace("actual_rgb=127,0,0", "actual_rgb=131,16,19")
        case.set("status", "run")
        case.remove(case.find("failure"))
    save(path, root)
    assert all(summary.endswith(": passed") for summary in gate.validate_results(path, 0))
    with pytest.raises(ValueError, match="CTest exit"):
        gate.validate_results(path, 8)


def test_runner_retains_output_and_classifies_real_ctest_contract(tmp_path, monkeypatch):
    def fake_run(command, **kwargs):
        assert command[command.index("--timeout") + 1] == "60"
        assert "--no-tests=error" in command
        assert kwargs["timeout"] == 150
        report(Path(command[-1]), cue_skip=True)
        return SimpleNamespace(stdout="CTest complete\n", returncode=8)

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    assert len(gate.run(tmp_path)) == 2
    assert (tmp_path / "stretch-diagnostics.log").read_text() == "CTest complete\n"


@pytest.mark.parametrize("mode", ["launch", "timeout", "missing", "malformed"])
def test_failed_runner_never_uses_stale_success(tmp_path, monkeypatch, mode):
    path = tmp_path / "stretch-diagnostics.xml"
    report(path)

    def fake_run(*args, **kwargs):
        assert not path.exists()
        if mode == "launch":
            raise OSError("cannot launch CTest")
        if mode == "timeout":
            raise subprocess.TimeoutExpired("ctest", 150, output=b"partial output")
        if mode == "malformed":
            path.write_text("<testsuite>")
        return SimpleNamespace(stdout="incomplete run", returncode=8)

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    with pytest.raises((OSError, subprocess.TimeoutExpired, ET.ParseError)):
        gate.run(tmp_path)
    assert (tmp_path / "stretch-diagnostics.log").is_file()
