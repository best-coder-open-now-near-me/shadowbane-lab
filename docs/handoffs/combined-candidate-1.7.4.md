# 1.7.4 retained movement diagnostics candidate

Exact package source: `d06d0b1494f1d673220dd4baa77e4fc9461bdb1c` on
`codex/native-lifecycle-hardening`. Common batch base remains
`14d117e8c5194c6dff55dac608b2d3f683187d31`; previous installed package source is
`04b7bdb298606f381618e8a66537955d7451b426` (1.7.3 / wheel 0.2.3).
New native product version is 1.7.4, wheel 0.2.4. Movement command ABI/wire is
unchanged. Optional diagnostic mapping is explicitly schema 2 with a new name;
the reader supports schema 1 explicitly for 1.7.3.

Included movement owner checkpoint: `02bca40924776a8f213223ba219a75182e63064e`,
cherry-picked as `75b60f404a43919ad64a0dcd7ef9b823831f34b2`. Shared mandatory
package gates are `d06d0b1`. Also includes the previously integrated cold-start
and reversal regression coverage. This is diagnostic instrumentation, not a
claimed fix for intermittent diagonal input loss. No mouse rebind, movement
policy change, new particles, or newer PvP identity work is included.

## Verified local package

Private root: `E:/Projects/shadowbane/artifacts/combined-packages/916ab918`.
SHA-256 identities:

- ZIP: `70e977851d355d9bf9f192a9d1f33cc31223c1815b3b8eaf54fb05f31b9cf5b8`
- Full DLL: `c90e295e2e0d85bcc67e0ac6ece773e1a1ab4ec41abb76a574a448222e11f0ed`
- Diagnostics-only DLL: `9629b8db65b0f291e7ecece7a78c4e4f5a6945c7c3f12a9506cd303fb4a41d1b`
- `shadowbane_lab-0.2.4-py3-none-any.whl`:
  `797bc71988f7a33acd3e93525c63134ccbdfa1a51d8ed3a4504583a0d90d8eb7`

Existing package builder ran against the clean exact commit. Python: 1845 passed,
12 skipped, 238 subtests. Ruff passed. Each native profile: 109 executed passes,
three no-argument private-binding skips; actual cue, sky and prepared-movement
binding checks executed separately and passed. Both required input-diagnostics
cases executed. Each profile's interprocess/reader suite: 42 passed, zero skips.
The two known ideal-transparency diagnostic failures per profile remain deferred;
they are not required runtime failures or evidence that particles are usable.

Installed wheel entry point and inspector/effects/cue/sky/movement controls passed
outside the source checkout. An additional installed-reader check parsed actual
native-produced schema-2 records from both profiles, including retained UI loss
with diagonal mask 9 and 256 retained events. ZIP CRC and all 57 receipt file
sizes/hashes verified. Private supplemental evidence: `installed-input-verification.log`,
`verify-installed-input.py`, and the two native-produced input trace fixtures.
Builder log: integration checkout `artifacts/combined-1.7.4-build.log`.

Independent review: existing particles owner task approved the exact source delta
`eaa6472..d06d0b1` with no actionable findings. Scope included callback/lifecycle
ownership, retained-loss coherence, reader identity/torn reads, and package gates.
This was independent source inspection, not an independent execution of tests.
CI run `34565362791` passed all seven jobs: quality, PowerShell syntax, Python
3.11/3.12/3.13 and both native profiles. The retained CI log confirms both new
native diagnostic cases executed and passed in both profiles:
`artifacts/combined-1.7.4-ci.log`.

## Remaining targeted observation

The installed VM remains 1.7.3; this receipt does not certify installation or a
connected fix. CI is complete; next use the designated diagnostic client only.
Enable `WONDERBANE_MOVEMENT_TRACE=1` at its next controlled launch, preserve its
settings and exact lifetime receipt, and collect with the packaged schema-2 reader
as documented in `docs/investigations/native-input-diagnostics.md`.

One focused observation remains: hold one direction, add a perpendicular direction,
and report an actual intermittent loss. Inspect retained key delivery/suppression,
stop reason, armed/gate state and native update interval. Do not interpret earlier
sampled gates as contemporaneous with a later callback. Do not change the user's
native keybindings or ask for another broad navigation run. Independent WASD
startup was demonstrated in the previous selection-only-click run; no new claim
of a first-click prerequisite is justified by that evidence.

## September 11 diagnostic installation

After the owner closed the diagnostic game and panel, verified no remaining game
or panel process. Removed only the explicitly resolved, non-reparse, stopped
1.7.2 client backup under the owner's existing backup-removal approval. Preserved
1.7.3 and copied its current Config into a freshly prepared 1.7.4 client through
the existing prepare-copy / verify-launchable-copy paths. Installed wheel 0.2.4
and verified exact source/package files before launching.

New designated VM root: `S:/ShadowbaneLab-Guided/combined-acceptance-1.7.4-916ab918`.
Launch receipt: PID 516, creation FILETIME 134335782020581173, HWND 525300.
Loaded DLL matches the full-profile hash above; prepared executable SHA-256 is
`bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87`.
`WONDERBANE_MOVEMENT_TRACE=1` is enabled only in the diagnostic launch environment.
The exact-lifetime schema-2 mapping is verified enabled. Before in-world login,
no update/input records or consistently published movement status were observed;
this does not establish an in-world startup failure. Next: owner logs in, then
verify native updates and start the bounded schema-2 input capture. No collector
is running yet and no connected movement fix is claimed.

Private installation, launch and channel receipts/scripts are retained under
`E:/virtual-machines/shadowbane-testing/diagnostics/combined-acceptance-1.7.4-916ab918`.

## Captured in-world loss causes

Schema-2 capture `diagonal-input-20260911-053336.jsonl` retained actual manual
owner losses with reason `stalled` at native intervals 266, 282, 266 and 265 ms.
Event 134 held backward (mask 2); policy changed from armed 197 to inhibited 64,
then 196 with the key still held. Subsequent opposite-key mask 3 remained disarmed.
Configured-key suppression remained active and original-delivery mask was zero.
This identifies a transient-update safety latch, not evidence of native binding
conflict. Another loss (398) was `scene_changed`, requiring separate investigation;
its reported input gates/interval were from the preceding sample.

Second capture `opposite-input-20260911-053804.jsonl` retained new `stalled` losses
530 and 552 while holding right (mask 8), and 707 while holding backward (mask 2),
all at 266 ms. New scene-change event 475 advanced scene 2 to 3. Earlier events
also appear as retained ring history and must not be counted as new recurrences.
The user reported reproducing the latch. The movement owner received these exact
non-address event summaries and private local capture paths for focused repair,
including opposite-key release-one semantics and a distinct scene-change audit.
No timeout increase, auto-resume policy, or connected fix is claimed. Current next
todo is the owner's focused source repair and regressions, followed by root
integration/package checks. The second bounded collector was still completing
when this evidence checkpoint was recorded; no further reproduction is needed.
