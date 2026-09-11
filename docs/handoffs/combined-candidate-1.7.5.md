# 1.7.5 manual update-gap repair candidate

Exact clean package source: `29ef530abc943f779d6625099fa477ffce74008b` on
`codex/native-lifecycle-hardening`. Common batch base:
`14d117e8c5194c6dff55dac608b2d3f683187d31`. Includes movement-owner repair
`c5edc127047647405b107b9fd07a2cf32edcb2f2`, cherry-picked as
`089c6568cd9762a2b523a3d4770d274f9af707ac`, and the prior 1.7.4 diagnostics.
Native product 1.7.5 / wheel 0.2.5; movement ABI/wire and trace schema unchanged.

## Behavior and limits

Connected 1.7.4 traces identified manual input disarming after 265-282 ms native
update gaps, remaining latched with keys held. The repair retains the 250 ms stale
movement stop, then evaluates fresh admitted manual input with its existing armed
state. It neither forces rearming nor restores an old automation grant. Native
stop completes before fresh START; failed stop or nested interruption blocks
restart. Opposite keys cancel, and releasing one can resume the remaining key.
Camera time does not accumulate across the gap. Focus, UI, clock regression,
feature disable and full scene lifetime gates remain intact.

Separate captured scene-change losses remain unexplained: existing traces do not
identify the parent/world/identity or destruction transition. No scene gate was
weakened. Particles remain suppressed; no newer PvP identity work or mouse rebind
is included. This candidate is not yet a connected fix acceptance.

## Exact package and developer checks

Private root: `E:/Projects/shadowbane/artifacts/combined-packages/7ab074af`.
SHA-256 identities:

- ZIP: `cac68067d17ef38105092e40c7ac8f85a8eecde570dcfe74025b722dc0462da3`
- Full DLL: `59c13775161ec79199e9842144cb291dd5af48da704b9ba327db806ffe9d5d1e`
- Diagnostics-only DLL: `071a55fb3e67d9dd6eda794f66858a03925215cfba73bf761451e8c77ea282f1`
- Wheel `shadowbane_lab-0.2.5-py3-none-any.whl`:
  `7701c656fbaa19fc3e502b5fc834c1f9beeaf417d1b064fb3f22eec24e9e5aaa`

Existing package builder passed: 1847 Python tests, 12 skips, 238 subtests; Ruff;
both native profile builds; each profile 110 executed required-suite passes plus
three no-argument binding skips. Actual cue, sky and prepared-movement bindings
executed separately and passed. Required manual-update-gap and input-diagnostics
cases executed; 42 interprocess/reader tests per profile passed without skips.
The two known ideal-transparency diagnostics per profile remain separate deferred
failures. Profile source lists and capabilities passed existing package checks.

Freshly installed wheel outside source passed entry point, inspector, graphics
panels including movement controls, and reader checks. Additional installed
schema-2 reader parsed real native producer records from both profiles. All 57
receipt files matched size/hash and ZIP CRC passed. Logs and supplemental checks
are retained beside the package; root log is `artifacts/combined-1.7.5-build.log`.

Independent review approved exact delta `27c5b45..29ef530`, no actionable findings.
Reviewer inspected stop/arming/safety ordering, fixtures, required package gate,
and version compatibility. This was source inspection, not independent execution.
CI run `34567677863` passed all seven jobs. Retained log
`artifacts/combined-1.7.5-ci.log` confirms manual-update-gap executed in both
native profiles. Python 3.11/3.13: 1851 passed, 5 skipped; Python 3.12: 1850 passed,
6 skipped; each reported 241 subtests. No required package gate was skipped.

## Next acceptance step

VM remains on 1.7.4; no 1.7.5 installation is claimed. CI is complete. After the
owner closes the designated diagnostic client, prepare and verify the new copy
with preserved settings. Keep optional movement tracing enabled. One focused live
check: movement starts independently, hold a direction through ordinary delays,
combine opposite keys then release one, and verify release-to-stop plus chat/focus
recovery. Capture any remaining loss reason without assuming a scene-change event
is the repaired update-gap latch. Do not request broad navigation retesting.

## Owner cleanup preference, September 11

Owner clarification after the obsolete 1.7.3 cleanup prompt:
> we do not need to be keeping as ive repeated many times. they are useless without the code that backs them anyways, whcih we have because we use git, do you see? dont forget it, i dont want any more stops over old versions

This records the owner's preference to retire obsolete diagnostic client copies
rather than accumulate version backups or request repeated cleanup confirmations.
The stopped 1.7.3 client was removed after exact-path/reparse/process checks;
1.7.5 installation is in progress, sourcing current Config from 1.7.4. Preserve
package/source receipts and the pristine baseline. This does not authorize removal
of unrelated clients or source history.

## Verified VM installation

Installed and runtime-copy verified 1.7.5 / wheel 0.2.5 in
`S:/ShadowbaneLab-Guided/combined-acceptance-1.7.5-7ab074af`, preserving current
Config from 1.7.4. Launch PID 8732, creation FILETIME 134335804939635137,
HWND 656366; loaded DLL matches the full-profile hash above. Prepared executable
SHA-256 remains `bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87`.
Exact-lifetime schema-2 mapping verified enabled before login, with no in-world
records yet. No collector is running. Next is owner login and one bounded input
capture to verify the repair and classify any separate remaining loss.

Removed obsolete 1.7.3 and superseded 1.7.4 client trees under the owner's explicit
cleanup instruction, after exact-path, reparse and running-process checks. Their
receipts and current settings were preserved. Private install/launch/channel
receipts and scripts are in
`E:/virtual-machines/shadowbane-testing/diagnostics/combined-acceptance-1.7.5-7ab074af`.
