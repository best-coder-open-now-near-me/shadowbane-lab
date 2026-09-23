# CI transparency diagnostic policy

The native CI matrix runs required native tests normally, then runs the two
`stretch-diagnostic` probes through `scripts/check_transparency_diagnostics.py`.
There is no job-wide or step-wide failure waiver. Each profile retains both
`stretch-diagnostics.xml` and `stretch-diagnostics.log`, including on gate failure.
The JUnit failures remain failures in the artifact; the classifier does not rewrite
results or claim rendering acceptance.

The currently reviewed counterexamples are:

| Probe | Deferred cases | Cases that must pass |
| --- | --- | --- |
| Effects transparency | Effect behind native alpha, with depth writes off or on | Effect in front, both depth-write modes |
| Selected-cue transparency | Native alpha in front, with depth writes off or on | Native alpha behind, both depth-write modes |

Both existing probes were reproduced in the `full` and `diagnostics-only` profiles
on September 23, 2026. Raw probe output from NVIDIA OpenGL 4.6.0 is retained in
`tests/fixtures/native_transparency/`; these are synthetic framebuffer diagnostics,
not private game captures. The checker requires all four uniquely identified pixel
cases, bounded reference/counterexample colors (two channel levels of rasterization
tolerance), matching effect error math, the exact corresponding assertion count,
and complete fixture/counterexample output. A corrected case may pass instead.
Unknown output, including another assertion inside a known failing executable,
fails the gate. Fixture/output changes require policy review; do not expand the
allowance merely to make CI green.

Selected-cue may also use its existing environment skip: CTest must report
`status="notrun"`, `SKIP_RETURN_CODE=77`, and exactly
`SKIP: context lacks framebuffer objects`. This preserves the hosted Windows
runner's limited OpenGL environment without claiming that the cue ran. Effects
cannot skip. Other skips, disabled/missing/duplicate/unexpected tests, errors,
crashes, incomplete output, and inconsistent CTest exit codes fail the gate.
CTest has a 60-second per-test deadline; the wrapper also bounds the whole run.
Old output files are removed before execution, so launch failures cannot reuse
stale evidence.

Run locally after building the two diagnostic targets:

```powershell
python scripts/check_transparency_diagnostics.py --build-dir build/native-full
python -m pytest tests/test_transparency_diagnostic_gate.py tests/test_package_native_gate.py -q
```

Validation for this change: both native profile probes compiled and their real
results passed classification; an actual CTest return-77 fixture verified skip
metadata; mutation tests reject extra assertions, changed/missing/duplicate pixel
cases, abnormal results and runner failures. This does not alter the package
builder's separate acceptance policy or production rendering. The diagnostic
limitation remains open.

Delivery branch: `codex/diagnostic-ci-gates`. Integrate this change into
`codex/integrate-current-development` ([PR #25](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/25)), then reviewed `main`.
It is not merged or deployed by this checkpoint. Local build evidence remains in
this worktree's ignored `build/diagnostic-gate` and `build/diagnostic-gate-minimal`
directories; the tiny skip-contract fixture is under `build/ctest-skip-contract`.
