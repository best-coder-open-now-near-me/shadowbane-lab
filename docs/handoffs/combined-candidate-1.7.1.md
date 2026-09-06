# Visible selection candidate 1.7.1

Build source: `becc58fdb4b1ae51fa6c82617c42dceea41a9e94` on
`codex/native-lifecycle-hardening`, original base
`14d117e8c5194c6dff55dac608b2d3f683187d31`. Native product 1.7.1.0;
wheel 0.2.1. ABI and wire versions unchanged. Main is not merged; no deployment
or connected acceptance is claimed. Later documentation commits are not build source.

## Included change and review

All prior hardening, movement, sky, indicator and navigation integration from the
[1.7.0 handoff](combined-candidate-1.7.0.md) remains included. Cue owner source
`2a9997316f0a11739e439d6aef71320ae020f790` is included as `60ca292`;
shared original-draw wiring, combined pixels and package gates are `e569717`.
`becc58f` scopes the deliberately short publisher test timeout to its held generation;
normal publication uses the production wait. Production timeout remains unchanged.

Selection now changes supported native material RGB during the original draw,
preserving native alpha, depth, blend, fog and foreground ordering. It does not
replay character geometry. Color and strength controls affect that material;
the obsolete radius slider is removed while saved wire compatibility remains.
No observed supported draw or unsupported material is reported explicitly.
Immediate/list submissions, custom programs, occupied texture stages and unsafe
query/context states retain native rendering. Off-screen direction is independent.
Particles/trails remain unavailable because their transparency is unresolved;
this release does not claim their visible delivery. The old late-mask cue APIs
remain diagnostic only. Their retained ideal-transparency failures do not describe
the new native-material path.

Particles owner independently approved the exact integration source and the final
test-only delta, with no actionable issue. Cue owner independently built/tested
`e569717`: native material, runtime, pipeline and query gates passed without skips,
plus 23 Python checks. That execution and the independent source review are separate
from root's exact final package gates.

## Validation and identity

Exact package directory: `E:/Projects/shadowbane/artifacts/combined-packages/e0fe50db`.
All 53 receipt files independently match size/hash; ZIP CRC passed. Both DLL
resources report 1.7.1.0. Superseded `9337cfc8` is on acceptance hold.

| Artifact | SHA-256 |
| --- | --- |
| navigation-inspector-acceptance.zip | `42d02a7e751c571924895baf2bee784578d6dff1726463a5e38635e81bf27ff8` |
| full/wonderbane-extension.dll | `7877d747c622fb0cea64befcc119abf9a20e55dc04b2e11139ea97ab340ec58a` |
| diagnostics-only/wonderbane-extension.dll | `7be752e107bd2eb3d035ff62b3cb649674e142274585bce1b368ea966f8fa36a` |
| dist/shadowbane_lab-0.2.1-py3-none-any.whl | `57e6c910f9a84b9ac619fc9eedaf8e087724574cda42da482908b13073d2a20b` |

Existing builder completed both fresh VS2022 Win32 profiles with verified source
membership. Each profile: 103 executed native passes, two no-argument private
binding skips then successful explicit checks against the reviewed executable;
29 real movement IPC passes with no skips. XML confirms native-material's 32
visible cases and combined render executed and passed in each profile. The two
old ideal-transparency diagnostics fail per profile and remain recorded separately.
Installed wheel outside checkout passes entry point, all Graphics Lab panels,
visible/no-eligible cue status and trace-reader checks. Exact commands, logs and
source membership are in `receipt.json` and `logs/`.

[Hosted CI 34033869036](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34033869036)
passed all seven jobs for exact `becc58f`: Python 3.11/3.12/3.13, Ruff,
PowerShell syntax, both Win32 native profiles and diagnostic artifact retention.
Hosted GPU/private binding skips are covered by the executed local exact-package
gates above; skipped checks are not counted as executed passes. Full CI log retained
at `artifacts/visible-selection-final-ci.log`.

Local final-source Python: 1830 passed, 11 skipped, 238 subtests. Ruff passed.
The exact package build's 1080p/46-draw fixture uses the shipped material path: all-enabled steady
median 3.817 ms versus 0.680 ms without cue; cue-only 3.178 ms; 4 bytes tracked
material texture, released on each transition. First-frame/warmup/ranges are at
`artifacts/visible-selection-final-cost-1080.log` in the integration worktree.
These synthetic host measurements do not establish live VM performance.

## Consolidated acceptance update

The existing **Test new integration features** task coordinates the complete
candidate. Follow the isolated-runtime preparation, exact lifetime verification,
installed-wheel launch, movement/navigation and restoration procedure in the
[existing acceptance handoff](combined-candidate-1.7.0.md#single-coordinated-acceptance-procedure),
substituting the verified 1.7.1 DLL and 0.2.1 wheel identities above.
Do not reuse the old hash-pinned launcher or overwrite a running/shared client.
This handoff does not expand deployment authority.

Replace the old hidden-glow acceptance with a visible-selection check: enable cue,
select/clear/change the character, adjust color and strength, and verify that only
the selected character changes visibly. Check normal equipment/material coverage,
one nearby foreground overlap, off-screen direction, and disable/re-enable.
A nonzero submission count is diagnostic evidence, not proof that the owner sees
an acceptable highlight. If no highlight appears, record the exact status and
selected identity; do not accept suppression as completion or repeat broad captures.

Retain already completed independent feature checks. With sky/navigation and cue
together, inspect foreground/UI, scene transition and normal exit, and record one
matched existing-telemetry performance sample with cue on/off. Only rerun the short
previously demonstrated obstacle route if combined behavior warrants it. Particles
are excluded visible functionality, not an acceptance prerequisite for this cue update.
Remaining live questions are character material coverage/appearance, foreground
quality and actual combined frame cost; previous uncompleted movement/device/client
isolation questions remain with the same testing task.
