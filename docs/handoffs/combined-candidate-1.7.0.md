# Combined candidate 1.7.0 / 0.2.0

Build source: `89c3b1ecb7087c8da3d1de697b6dfb507682a8f8` on
`codex/native-lifecycle-hardening`. Common base:
`14d117e8c5194c6dff55dac608b2d3f683187d31`. This evidence document is recorded
after the build; its later documentation commit is not the packaged source.
Main is not merged and no VM/client deployment is performed by this handoff.

## Included scope and limitations

Includes native lifetime/rollback/shutdown repairs; manager launch reservation,
exact process ownership and independent renewal; serialized terminal publication;
interprocess learned-map persistence and durable operation transitions; simulator
preflight and planner blocker/indexing repairs. The detailed reproductions,
already-resolved findings and earlier executed regressions remain in
[native-lifecycle-hardening.md](native-lifecycle-hardening.md). Demonstrated
zone/obstacle/rune-hunt navigation is preserved, not re-investigated.

Integrated feature identities:

- Cue fallback owner `76246fe4dc31986593f3789b42d3bbd7576bb51d`;
  root integration `d4adcbfaa9bf0280bc1196c3e54dfc7fb3914679`.
- Particles fallback owner `62755f988c228beb38418c8e0e878d903a288ef0`,
  handoff `51640bf8caddc4a4671cb22d25bb1ccc864a63c0`, lint
  `372e2b843b116e25759c2a611dd07b529378c9b8`, and legacy test correction
  `6c9820b3599dad79ea41801fb01373d2b1365f0c`.
- Movement final owner `2be1a650cde19a46c6301062418f7d9f698d2d10` is retained.
- Sky production verification `4368f13c53601684d0abb67f3d43513561b0bbf4`
  and shared reconciliation `d689fd3fe8c220a73dfb9eea2030948ec959b638` are retained.

Per the September 6 owner decision, world glow and particles/trails are suppressed
because no supported scene path establishes safe foreground composition. Settings
remain requested preferences; controls explicitly report hidden/suppressed output.
Bursts are canceled and trails cleared, without later replay. Off-screen selected
direction, sky, navigation and movement remain independent. Suppressed effects are
deferred visible functionality, not claimed successful rendered features. Ideal
transparency still fails the retained diagnostic probes. Terrain-material repair,
fragment-ledger/atlas experiments, hot unload and competing movement/hooks are excluded.
Native ABI and wire versions are unchanged; product versions are distinct.

## Exact local artifacts

Directory: `E:/Projects/shadowbane/artifacts/combined-packages/6a60ecb6`.

| Artifact | SHA-256 |
| --- | --- |
| navigation-inspector-acceptance.zip | `a18ee470efed959625e05f71d190cb16bee5b83e1167dff9cee87ee813f22591` |
| full/wonderbane-extension.dll | `58e9d5e31fadec47a7b6179bbd2ce09a9f463fb8d202b2e425832b35951b84a2` |
| diagnostics-only/wonderbane-extension.dll | `0d3ab5dd2437c5dba69565b3d0420b4731753b67823ceccdf7201d4ed9ead7f9` |
| dist/shadowbane_lab-0.2.0-py3-none-any.whl | `b49f51d4654f56b3ab5a541536c3a66acc068a5aa8aba9c4b38a984474d3aec9` |

Both DLL resources are 1.7.0.0. `receipt.json` retains commands, source identity,
profile source membership, all logs/XML and individual hashes. All 53 receipt files
were independently checked for size/hash and the ZIP CRC verified. The full DLL
contains intended runtime features/assets; diagnostics-only excludes their runtime
implementations while its developer test executables still exercise them. Earlier
packages `2d90db63`, `fb01364f` and `be2092c3` are on acceptance hold and must not be installed.

## Executed validation

- Exact clean existing builder: local Python 1822 passed, 10 skipped, 238 subtests;
  Ruff passed. Both Win32 VS2022 Release profiles built.
- Each profile: 102 native tests passed; two no-argument private binding tests
  skipped in CTest then executed successfully with the exact reviewed executable.
  Cue/sky binding and sky runtime checks passed. Hardware and actual Microsoft
  OpenGL 1.1 operator gates executed; legacy unsupported nonlinear factor reported
  unavailable individually, with 20 supported cases and no GL errors.
- Each profile: 29 real movement IPC tests passed, zero skips. Installed wheel
  outside checkout passed entry point, inspector, effects, cue, sky, movement,
  conservative-status and trace-reader checks.
- Two ideal-transparency diagnostic failures/profile retained explicitly. These
  do not certify visible glow/particles and cannot bypass required runtime tests.
- Final hosted CI: all seven jobs passed for exact 89c3b1e, including Python
  3.11/3.12/3.13, Ruff, PowerShell, both native builds/required tests and retained
  diagnostic artifacts: [run 34029430594](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34029430594). Hosted native GPU/private-binding skips are explicitly
  covered by the executed local package GPU gates and private binding checks.
- Independent review: movement owner reviewed e84a40a integration (61 Python tests,
  12 subtests and two rebuilt runtime gates passed, no integration defect). Later
  runtime is unchanged; particles owner independently reviewed final 04b42d5 legacy
  registration/override isolation and the final 89c3b1e diagnostic-upload path; no issue
  found. Subsequent changes are test
  fixtures, test capability checks, package gate registration and evidence only.

The 04b42d5 synthetic 1080p/46-node host harness (unchanged runtime/test source
in 89c3b1e): baseline median 0.100 ms,
navigation 0.207 ms, sky 0.574 ms, navigation+sky 0.658 ms; cue mask allocation zero
in those configurations. The direct-renderer all-four diagnostic path is 3.014 ms
and 16,588,800 cue bytes, but bypasses production suppression and is not the live
candidate's cost. First/warmup/steady samples and ranges are retained at
`artifacts/hardening-evidence/04b42d5-combined-cost-1080.log`. These host measurements
do not establish a connected VM frame-time budget.

## Single coordinated acceptance procedure

The existing Sol task **Test new integration features** owns the coordinated live
pass with the owner. Use this exact candidate for the coordinated acceptance pass. No broad navigation rerun and no repeated diagnostic character captures.

1. Prepare only the agreed isolated runtime through existing `client_extension
   prepare-copy`; preserve the known-good installation. Use the reviewed immutable
   baseline and its exact bootstrap manifest, the full DLL above and the installed
   0.2.0 wheel. Verify with `verify-launchable-copy`, then record executable path/hash,
   PID plus creation FILETIME and loaded DLL path/hash. Do not reuse an old hash-pinned
   launcher, diagnostic receipt, or overwrite a running/shared client. Deployment
   authority remains with the owner; this source/package handoff does not expand it.
2. Open Graphics Lab using that wheel's Python:
   `python -m shadowbane_lab.graphics_lab`. Select the exact intended client.
   Start with existing settings recorded and manual movement disabled. Verify normal
   mouse selection, camera, inventory, map and UI behavior.
3. Enable selected cue; select/clear/change an on-screen target and move it off-screen,
   including behind the camera. Expect an appropriate off-screen direction, no world
   glow and the explicit hidden-glow status. Enable particles/trails and request a
   burst: expect suppression status, no particles or trails, and no later burst/history
   replay after toggles or scene/context transition. Native foreground remains intact.
4. Test sky appearance, orientation/horizon/intensity controls, camera translation
   and rotation, foliage/water and UI/minimap. Disable and Restore original must
   restore native sky without changing navigation or other settings.
5. Use Movement controls in Graphics Lab or Ctrl+Alt+F10 when chat/modal UI is closed.
   Follow the compact table in [native-movement-controls.md](../native-movement-controls.md):
   WASD/remapping, chosen XInput controller movement/camera, X1 hold-drag and release,
   real stop, chat/focus/modal safety, neutral re-arm, disconnect/reconnect and exact
   two-client isolation. A gamepad and second client are needed; mark unavailable
   cases pending rather than passed.
6. Reuse one short representative part of the already demonstrated route with an
   obstacle. Take over manually during /go and /pve; no old move/stop may reclaim or
   cancel newer ownership. Release must not resume automation; resume explicitly.
   Camera-only input must preserve the route. No new basic navigation investigation.
7. With sky/navigation/indicator and requested suppressed effects together, record
   one matched stationary/moving performance sample using existing telemetry; compare
   toggles, transition/disable/re-enable and normal exit. Watch for flicker, resource
   growth, stuck motion or effects on the other client. Restore recorded preferences
   and close only the recorded isolated lifetime; no broad process-name kill/hot unload.

Record observed results and exact artifact identities once. Remaining connected
questions are appearance/camera alignment, indicator direction, suppression/status,
manual/automation ownership, device/UI/focus isolation, interruption recovery and
actual frame/resource cost. Automated checks do not mark any of these live questions
passed. Route a specific failure to its existing owner and retest affected behavior.
