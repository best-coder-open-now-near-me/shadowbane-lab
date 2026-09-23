"""Run deferred native diagnostics, rejecting everything but reviewed counterexamples.

This is a CI classification gate, not rendering acceptance. See
``docs/ci-transparency-diagnostics.md`` for its deliberately narrow policy.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

EFFECTS = "wonderbane_extension_effects_native_transparency"
CUE = "wonderbane_extension_selected_cue_native_transparency"
EXPECTED = {EFFECTS, CUE}
FBO_SKIP = "SKIP: context lacks framebuffer objects"
EFFECT_ASSERTION = "native/effect transparency must respect relative depth"
CUE_ASSERTION = "cue must preserve native transparency on both sides of its depth"
RGB = r"(\d+),(\d+),(\d+)"
EFFECT_SAMPLE = re.compile(
    rf"Native transparency requirement: effect-front=([01]) depth-write=([01]) "
    rf"expected RGB={RGB} late-pass RGB={RGB} absolute error=(\d+)/765 (PASS|UNRESOLVED)"
)
CUE_SAMPLE = re.compile(
    rf"native alpha=\.5 foreground=([01]) depth_write=([01]) "
    rf"expected_rgb={RGB} actual_rgb={RGB}"
)
EARLY_SAMPLE = re.compile(rf"wholesale-early-counterexample depth_write=([01]) early_rgb={RGB}")
TRANSMISSION = re.compile(
    r"Transmission information: identical scene RGBA/depth, required behind blue=(\d+) vs "
    r"(\d+); source alpha is not recoverable from scene snapshots"
)
TIMINGS = (
    "Enabled draw mean (test context, one trail segment): ",
    "Maximum line capacity draw mean (test context): ",
)


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise ValueError(detail)


def near(actual: tuple[int, ...], expected: tuple[int, ...], tolerance: int = 2) -> bool:
    return len(actual) == len(expected) and all(
        0 <= a <= 255 and abs(a - b) <= tolerance for a, b in zip(actual, expected, strict=True)
    )


def classify_output(name: str, output: str) -> int:
    """Return expected assertion count; reject extra checks even in a known failing test."""
    samples = {}
    ancillary = Counter()
    assertions = 0
    unresolved = 0
    assertion = EFFECT_ASSERTION if name == EFFECTS else CUE_ASSERTION
    for line in output.splitlines():
        if line == assertion:
            assertions += 1
            continue
        match = (EFFECT_SAMPLE if name == EFFECTS else CUE_SAMPLE).fullmatch(line)
        if match:
            front, depth = map(int, match.group(1, 2))
            key = front, depth
            require(key not in samples, f"{name}: duplicate pixel case {key}")
            reference = tuple(map(int, match.group(3, 4, 5)))
            actual = tuple(map(int, match.group(6, 7, 8)))
            if name == EFFECTS:
                require(near(reference, (0, 0, 255) if front else (128, 0, 128)),
                        "effects reference fixture changed")
                error = sum(abs(a - b) for a, b in zip(actual, reference, strict=True))
                correct = error <= 6
                require(error == int(match.group(9)) and match.group(10)
                        == ("PASS" if correct else "UNRESOLVED"), "effects error mismatch")
                if not correct:
                    require(not front and near(actual, (reference[0], 0, 0)
                                               if depth else (0, 0, 255)),
                            "unexpected effects counterexample")
            else:
                require(near(reference, (131, 16, 19) if front else (84, 122, 143)),
                        "cue reference fixture changed")
                correct = near(actual, reference, 1)
                if not correct:
                    require(front and near(actual, (127, 0, 0) if depth else (116, 31, 37)),
                            "unexpected cue counterexample")
            require(all(0 <= value <= 255 for value in actual), "invalid pixel value")
            unresolved += not correct
            samples[key] = correct
            continue
        if name == EFFECTS:
            if re.fullmatch(r"OpenGL draw test: [^\r\n]+", line):
                ancillary["context"] += 1
                continue
            timing = next((prefix for prefix in TIMINGS if line.startswith(prefix)), None)
            if timing:
                value = line.removeprefix(timing).removesuffix(" ms")
                require(line.endswith(" ms") and re.fullmatch(r"\d+\.\d{3}", value)
                        is not None and math.isfinite(float(value)), "invalid timing")
                ancillary[timing] += 1
                continue
            match = TRANSMISSION.fullmatch(line)
            if match:
                require(near(tuple(map(int, match.groups())), (191, 64)),
                        "transmission fixture changed")
                ancillary["transmission"] += 1
                continue
        else:
            match = EARLY_SAMPLE.fullmatch(line)
            if match:
                require(near(tuple(map(int, match.group(2, 3, 4))), (142, 61, 72)),
                        "cue early-pass fixture changed")
                ancillary[int(match.group(1))] += 1
                continue
        raise ValueError(f"{name}: unexpected output: {line!r}")
    require(set(samples) == {(0, 0), (0, 1), (1, 0), (1, 1)},
            f"{name}: incomplete pixel cases")
    expected_ancillary = Counter(
        {"context": 1, "transmission": 1, **dict.fromkeys(TIMINGS, 1)}
        if name == EFFECTS else {0: 1, 1: 1}
    )
    require(ancillary == expected_ancillary, f"{name}: missing or duplicate fixture output")
    require(assertions == unresolved, f"{name}: assertion count differs from pixel failures")
    return unresolved


def validate_results(path: Path, exit_code: int) -> list[str]:
    cases = ET.parse(path).getroot().findall(".//testcase")
    require(Counter(case.get("name") for case in cases) == Counter(dict.fromkeys(EXPECTED, 1)),
            "diagnostic tests are missing, duplicated or unexpected")
    failures = 0
    summaries = []
    for case in cases:
        name = case.get("name")
        require(case.find("error") is None, f"{name}: test error")
        require(not case.findtext("system-err", "").strip(), f"{name}: unexpected stderr")
        require(len(case.findall("system-out")) == 1, f"{name}: missing or duplicate output")
        output = case.findtext("system-out", "")
        if case.find("skipped") is not None:
            require(name == CUE and case.get("status") == "notrun"
                    and len(case.findall("skipped")) == 1
                    and case.find("skipped").get("message") == "SKIP_RETURN_CODE=77"
                    and case.find("failure") is None and output.strip() == FBO_SKIP,
                    f"{name}: unexpected skip")
            summaries.append(f"{name}: environment skip (framebuffer objects unavailable)")
            continue
        assertions = classify_output(name, output)
        if assertions:
            failure = case.find("failure")
            require(case.get("status") == "fail" and len(case.findall("failure")) == 1
                    and failure.get("message") == "Failed" and not (failure.text or "").strip(),
                    f"{name}: crash, abnormal failure or inconsistent status")
            failures += 1
            summaries.append(f"{name}: {assertions} reviewed counterexamples (unresolved)")
        else:
            require(case.get("status") == "run" and case.find("failure") is None,
                    f"{name}: unexpected failure without counterexample")
            summaries.append(f"{name}: passed")
    require(exit_code == (8 if failures else 0), "CTest exit does not match diagnostic results")
    return summaries


def run(build_dir: Path, *, ctest: str = "ctest") -> list[str]:
    build_dir = build_dir.resolve(strict=True)
    report = build_dir / "stretch-diagnostics.xml"
    log = build_dir / "stretch-diagnostics.log"
    # Never validate stale evidence if CTest cannot start or aborts before writing a report.
    report.unlink(missing_ok=True)
    log.unlink(missing_ok=True)
    command = [ctest, "--test-dir", str(build_dir), "-C", "Release", "-L",
               "stretch-diagnostic", "--output-on-failure", "--no-tests=error", "--timeout", "60",
               "--output-junit", str(report)]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", timeout=150,
                                check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        partial = getattr(exc, "stdout", "") or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        log.write_text(partial + "\n" + str(exc) + "\n", encoding="utf-8")
        raise
    log.write_text(result.stdout, encoding="utf-8")
    print(result.stdout, end="")
    return validate_results(report, result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        for summary in run(arguments.build_dir):
            print(summary)
    except (OSError, ValueError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        print(f"Transparency diagnostic gate failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
