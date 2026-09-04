# Navigation inspector acceptance package — 2026-09-04

The initial acceptance package is built and verified and was deployed into a new,
isolated testing-VM runtime. Live acceptance is in progress; nothing is merged.
The package and hashes below describe the initial e380e0f build. The Python publisher
correction below is installed. The native display correction below is installed and running after the owner
closed the previous client. Its actual loaded DLL and installed source identities
match the verified package. The renewed display check confirmed persistence,
minimap clearance, hiding and reopening the actual saved failure. A separate
verified camera-correction package is recorded below; its live check is pending.

## Source and review

- Tested source: e380e0fbaa0a24b81c84d4d45482e5f7d0c05682.
- Published branch: codex/navigation-inspector.
- [Draft PR #27](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/27)
  targets codex/integrate-current-development while PR #25 is open.
- Source includes the complete publisher, native overlay, desktop controls,
  saved-evidence replay and package builder. The separate terrain material repair
  is absent. The runtime correction below changes Python publisher code after this
  initial package; its replacement wheel must carry its own source identity.
- The normal checkout is clean on main at 047147dfe468670458486a806d03b03284824dd1.
  Retain the inspector worktree for acceptance/review.

## Verified gates

The builder exported the exact committed source into an isolated local artifact
directory, stamped that source revision into the acceptance wheel, and stopped
on any failing gate. This successful run completed:

- Full Python suite: 1,641 passed, 7 skipped; 211 subtests passed (36.66 seconds).
- Ruff across source, tests and the package builder.
- Visual Studio 2022 Win32 Release full and diagnostics-only builds; all 18
  native tests passed in each profile. Both DLLs independently verify as x86 PE.
- Generated DLL project inspection: all four inspector runtime sources belong
  exclusively to full; diagnostics-only has none of them.
- Wheel built from the fresh source distribution; native sources, golden wire
  fixture, source identity and builder are present in the source distribution.
- Wheel installed without dependency downloads into a new environment; installed
  entry point and real hidden Tk panel initialization/cleanup passed.
- All receipt file sizes and SHA-256 hashes rechecked after packaging.

The real OpenGL harness used NVIDIA OpenGL 4.6.0 / driver 596.36. The full profile
measured 0.176 ms per simple enabled draw and 0.486 ms at the 16,384-line capacity.
These synthetic numbers are not live-game performance acceptance. Tests also
exercise ordinary occlusion versus dashed x-ray, preserved scene depth, a
nondefault GLSL program, multiple texture units and restored graphics state.
Full test output is included in the package's native LastTest logs.

## Package and hashes

Local artifact directory, relative to the inspector worktree:
artifacts/navigation-inspector/7a7795e3/.

The file navigation-inspector-acceptance.zip includes the full and diagnostics-only
DLLs, wheel, source distribution, committed source archive, source/contract
identity, generated project evidence, test logs, receipt and live handoff.

Acceptance ZIP SHA-256: da87758e9285074dfa63f9eb838dd0571ad016eca7c7fba4c3145d35b98ef52c

| Artifact or contract | SHA-256 |
| --- | --- |
| full/wonderbane-extension.dll | 107b105c7bbe74ed4deaf3a495e34520267a6b30c31a96e4154013b9fd4a48ba |
| diagnostics-only/wonderbane-extension.dll | 0e43b77d20954c7f84e5d9947cd93467dca2a14d4fd6557230809e8f5f4d8b7c |
| dist/shadowbane_lab-0.1.0-py3-none-any.whl | f984863cac109b61326b1c155fec67916e6d18d7b87ed35accbd6eef30ff22a0 |
| dist/shadowbane_lab-0.1.0.tar.gz | 961d77d6db82fd93c9567ac780354ae961aeea93f04b16908909c2e8db2cae87 |
| source/src/shadowbane_lab/navigation_inspector/protocol.py | ff0ba6fd62e55ea6693c5b892838f19278dbfb688c3f7235e9c150966738f330 |
| source/native/wonderbane_extension/navigation_protocol.h | aa73842e438bc5ea3392441d2314c60a3cc2411b7df102453697ded78082ad8d |
| source/tests/fixtures/navigation-inspector-v1.hex | b79f08bc09766db3e36f241ee46360d5f8a448792bf8457f18f1a73c2eb16640 |

The receipt.json file records all included file hashes, sizes, exact commands and
successful exit codes. The source archive and build logs stay local; only source
and documentation were pushed. Reproduce with the committed
scripts/build_navigation_inspector_package.py and the prerequisites in
[inspector usage](navigation-inspector.md). No game executables or private captures
are part of this archive.

## First live findings and correction

The prepared copy and actual loaded full DLL matched the receipt. The inspector
panel armed the client. The first chat destination was inside the default 75-unit
arrival radius and therefore produced no clicks. Repeating the bounded movement
with an explicit 5-unit radius produced five accepted clicks, completed within
roughly 4.4 seconds of dispatches, and was visually confirmed by the owner.

The overlay did not receive evidence: attachment compared the observation
profile's original executable hash with the actual prepared client's hash. The
verified native position reader already owns the accepted runtime identity. Both
travel and PvE now pass that reader to the optional inspector session. A second
fix drains queued terminal evidence when an immediately completed run closes.
Regression tests cover reader binding and a real Windows mapping with delayed
startup and immediate session close.

The replacement wheel at bb8462b97c68b77fe5e990b77e4213a7f8092b7a passed all
package gates: 1,642 Python tests, seven skips, 211 subtests, Ruff, both Win32
profiles with 18 native tests each, source packaging and installed-panel checks.
Its wheel SHA-256 is 686007917bcfb50186a1bc79ff0344682324b21666f9d9acd303e731db5fb6f5;
package SHA-256 is cd55e49992a5a2f1b20a57ecc8364c3bc39c8539f09a44450ceb8999ca010980.
Local evidence is under artifacts/navigation-inspector/1f6ad5a8/. Both rebuilt
DLLs were byte-identical to the initial package, so only the wheel and helpers
needed replacement; actual runtime identity was rechecked without restarting the
client.

The next bounded route found no A* route from the current terrain cell and issued
zero clicks. This produced a real automatically frozen capture containing the
blocker/cost map, failure, measured position and exact runtime identity. The owner
and screenshots confirmed the in-game projected map appeared. It was obscured by
the minimap and disappeared when the producer's two-second lease expired. The
same capture reported WORLD CAMERA UNAVAILABLE; world alignment is not accepted.

The native display correction centers the map and retains validated projected
evidence after expiry. It keeps world placement disabled when stale or the zone
is unknown/changed. The native reader applies identity-checked panel visibility
and layer controls even without a producer. Native tests cover this lifecycle,
corrupt/torn controls, cross-language control bytes, actual OpenGL placement,
stale x-ray suppression, preserved depth and restored graphics state.

The replacement client is now running. Persistence, minimap clearance and hiding
passed the renewed live check below. World-camera ownership, alignment and PvE
acceptance remain pending.
Private runtime identities, logs and captures stay in the local VM evidence
folder; they are not published source.

## Verified native display package

The display correction is built from 18bcf6dc0606bb9086c88d7e3073a65a0f7fc091 on codex/navigation-inspector.
The package is local at artifacts/navigation-inspector/6c7397e3/ and has been
transferred, with all 27 receipt files rechecked, to the testing VM staging share.
The owner closed the previous client. Its test helpers were retired, allowed
mutable preferences were preserved, and runtime integrity was checked again.
The replacement is now running with this exact full DLL and installed source
identity verified through its actual process/module channel.

Validation: full Python run 1,641 passed, eight skipped, 211 subtests passed.
The extra skip was a Tk initialization failure in the replay/return-live test;
that exact test passed on a focused rerun in the same exported source. The
separate installed-wheel Tk panel gate also passed. Ruff, both VS2022 Win32
Release profiles, all 18 native tests per profile, wheel from source distribution,
installed entry point, and receipt verification passed.

| Artifact | SHA-256 |
| --- | --- |
| full/wonderbane-extension.dll | f8049ce56c749db68aaab7d728175e4a89fbfb2e5727a62e569e15a5d9c1eb3d |
| diagnostics-only/wonderbane-extension.dll | 0e43b77d20954c7f84e5d9947cd93467dca2a14d4fd6557230809e8f5f4d8b7c |
| dist/shadowbane_lab-0.1.0-py3-none-any.whl | 516491cf84e09bbd72e1d7f8984b886d3559b41dddc0f64f1ee1ff21b0b38d78 |
| dist/shadowbane_lab-0.1.0.tar.gz | 1c2e140b07fb86ed4199b20e500016f73d0dcdf7ae8c06414615f462cade1a8d |

Acceptance ZIP SHA-256: 398e388d670ac96163746e4136ba85d4ee6aa8792d59d1405e07c2e2e56615b4.

The replacement isolated client passed the production prepared-copy and runtime
verification gates in the testing VM. The older installation remains preserved.
The launch copied only allowed mutable preferences after logout and verified
the full DLL hash before starting. Loaded-module verification then confirmed
the actual running DLL hash. All runtime evidence remains private.

## Verified live display check

The owner logged into the replacement client. Window/HUD geometry matched the
previously verified local calibration. The exact client was armed, and a bounded
15-second route attempt ran with a five-unit arrival radius. The planner rejected
the route before input: zero clicks, one controller step, and a real frozen
A* failure capture. The capture includes its blocker/cost map and exact source
and loaded DLL identities. The starting cell and neighboring cells are marked as
model blockers; this does not prove physical collision in the visible terrain.

Screenshots through twelve seconds show CAPTURE / PROJECTED ONLY near the top
center, clear of the minimap, after the producer lease expired. The owner then
unchecked Show in game and confirmed the map disappeared. Read-only control
inspection and a subsequent game screenshot independently confirmed it was hidden
while the same frozen capture remained available. The actual saved failure was
reopened through the installed wheel's Tk panel with no live channel or input
adapter. These checks accept the display corrections, not the full navigation
inspector or PvE behavior.

The current graphics-status evidence contains zero accepted camera samples.
World-trail placement therefore remains unavailable. Existing historical renderer
traces were inspected in place after the owner explicitly approved access.
No historical trace files were copied. Their 537 and 1,505 draws contain 40 and
54 attributed terrain submissions respectively, with one consistent terrain
model-view per capture. Offline inspection of the exact frozen executable shows
the world queue at RVA `0x79C730` pushes model-view before its submissions and
restores it afterward (`0x79C738` / `0x79C7F1`). The old depth-one per-draw observer
therefore cannot accept those nested terrain submissions. These historical traces
explain the observer limitation; they are not current-client acceptance evidence.

The correction captures the outer camera at the reviewed main clear and requires
the identical restored camera at the reviewed pre-UI boundary. Context, projection,
viewport, scene validity, and stack depth must all agree. Synthetic regressions
cover nested object transforms and rejection of changed/invalid/expired scenes.
The current running client still uses `18bcf6d`; the camera correction needs a
new verified package and joint visual check before acceptance.

All screenshots, the live capture, visibility observation and installed-panel
replay result remain in the private local evidence locations recorded by the
artifact registry. The inspector panel remains connected with Show in game off;
the bounded command listener is available, with no active movement run.

## Verified camera-correction package

Source `35344185240b6de61ec24ab3b8460959bf78a575` is pushed on
`codex/navigation-inspector` in draft PR #27. The complete package build passed:
1,642 Python tests, seven skips, 211 subtests; Ruff; both VS2022 Win32 Release
profiles with 18 native tests each; wheel from source distribution; fresh installed
entry point and actual Tk panel. All 27 receipt entries were independently
verified against both disk files and archive contents.

Local package: `artifacts/navigation-inspector/b704181b/navigation-inspector-acceptance.zip`.
ZIP SHA-256: `35a88dcc9d4dc295916c2bf0c439ad7eff8e48fe91712ad93ba62a724f6a52cf`.

| Artifact | SHA-256 |
| --- | --- |
| full/wonderbane-extension.dll | f08f99ea8dc8f8558971e3c00252b20df3ede58e00a723df012e4a14cd9071e7 |
| diagnostics-only/wonderbane-extension.dll | 83752e380d34da5abf0b18e6f44dfa3b6db2ef7a8b3b12d258b73c424ff755e1 |
| dist/shadowbane_lab-0.1.0-py3-none-any.whl | 758d93231a791e142cb6bb671138f4f8e0b751970a9b975b89c2feadc6e8683c |
| dist/shadowbane_lab-0.1.0.tar.gz | 985206c909d51b7890c70d599bef638cec324e841aa6be949afe462500706dc7 |

The owner authorized this update for the existing local testing VM. The separate
`S:\ShadowbaneLab-Guided\20260904-inspector-3534418` runtime was prepared through
the existing reviewed baseline/bootstrap path and passed runtime verification.
After the owner closed the previous game, the verified replacement launched as
PID 8652 / creation FILETIME 134330013610671584. Its actual loaded DLL hash is
`f08f99ea8dc8f8558971e3c00252b20df3ede58e00a723df012e4a14cd9071e7`, installed
source is `35344185240b6de61ec24ab3b8460959bf78a575`, and its inspector channel
is available. The allowed HUD preferences were preserved and runtime integrity
was rechecked before launch. Only the identified prior inspector/listener helpers
were stopped; previous installations and saved captures remain intact. The
subsequent login, camera and trail findings are recorded below.

## Live camera and first trail check

The owner logged into the verified `3534418` client in Sea Dog's Rest. The full
renderer reports `reviewed-main-scene-boundaries` camera evidence: its 256-sample
ring was full, sequence advanced from 505 to 2,283, and producer drops stayed at
zero. The sampled scene had one verified main scene/boundary, no invalidation,
no late world draws, and a successful pre-UI composite.

After the owner focused the game, `/go 88712 44857 --radius 5` reported completion
using the production A* route: four clicks, no replans or direct fallback, and one
position sample within five units. The subsequent overshoot below invalidates
that completion claim. The saved capture has 12 measured trail positions and 13 events. Its
geometry contains all 11 world-height trail segments, with zero omitted lines,
trail omissions or dropped observations. Capture SHA-256:
`0185547c71dbf0cdf954af261ec9d080f22b4c4aa8bf3ffca06a930a24d7a8f7`.

The screenshots show cyan world-trail portions on the road, but the owner reports
that only the first short segment was visible. **Trail visibility is not accepted.**
The planned normal/x-ray comparison is paused until destination execution and
actual arrival are verified. No height or depth rule
has been changed to conceal the finding. The projected capture remains available
after the producer lease expires; stale evidence cannot draw world lines.

Local evidence is retained under the current VM diagnostics folder: `short-test.json`,
`short-walk-segment-audit.json`, `recordings/short-walk-4526109934204037937.json`,
and `graphics-status-in-world.json`. Timed PNGs and their UTC index are in the
worktree's ignored `artifacts/navigation-inspector/live-20260904/camera-walk-*`.
The current helpers are panel 3316, listener 6312 and recorder 7696. No movement
command remains active.

## Owner-confirmed destination overshoot

The owner confirmed that the character kept walking without manual movement.
The run reported LT 88708.140625 / LG 44857.0234375 at 3,422 ms, but subsequent
read-only samples found it stationary at approximately LT 89009.25 / LG 44857.02:
about 301 units beyond the reported endpoint. No second automated route ran.
The x-ray comparison was armed but has not started.

The owner clarified the actual client behavior: a click specifies a destination;
new clicks replace that destination, and immediate stopping in place is not a
reliable operation. Code inspection finds that `DecisionInputCompiler` normalizes
all movement vectors to the full calibrated minimap radius, discarding waypoint
distance. `compile_movement_stop` sends a center click, and `TravelRunner` returns
as soon as that input is accepted, without observing a stationary arrival. Neither
input acceptance nor a sample inside the arrival radius proves completion.
The recorded trail ends with that premature return, so the apparent short trail
must be reassessed after the movement lifecycle is corrected. A depth defect has
not been demonstrated by this run.

The production correction must preserve bounded world destinations through the
minimap projection, verify its current scale/geometry rather than fit a guessed
ratio to this overshoot, observe stationary arrival, and keep capturing until the
run actually settles. Cancellation must describe destination replacement and
remaining movement honestly. The same actuator is used by PvE; its acceptance
remains blocked by this finding.

Local evidence: `motion-before-xray.json`, `short-test.json`,
`listener.stdout.jsonl`, and the original capture above. The read-only investigation
and `before-stop-investigation.png` remain in the ignored live artifact directory.

## Destination correction source checkpoint

Read-only live evidence verified the minimap content center `(1815,119)`, zoom
`2.078929901123047`, and the native 0.13 base scale. Source checkpoint `ab9b367`
adds the guarded minimap reader. The following correction wires travel/PvE to
bounded absolute LT/LG destinations, preserving distance and rejecting uncertain
geometry or unusably coarse zoom. It removes the unverified center-click stop.

Completion requires fresh positions inside the arrival radius and a 0.25-unit
horizontal envelope for 600 ms, with a four-second settling deadline. The trace
continues throughout that interval. PvE consumes coherent observation frames and
preserves normal combat dispatch while checking settling; an opener followup on
the first arrival-candidate tick has a dedicated regression. New approach input
supersedes the pending check. Cancellation ends automation and reports that the
last clicked destination may still complete.

Focused regression checks pass. The previous full source run passed 1,667 tests
with 7 skips and 211 subtests; exact final-source counts, native/profile gates and
package receipts must come from the committed package build. No corrected wheel
or DLL has been deployed yet, and the overshoot/visibility acceptance remains open.

## Exact getter preflight correction

The `c9f3e16050d4cc579a6d1935750bd3bea0c70e0c` package passed 1,668 Python tests,
7 skips, 211 subtests, Ruff, both Win32 profiles (18 native tests each), wheel/source
packages and the installed panel. All 27 receipt entries matched disk and ZIP.
Package: `artifacts/navigation-inspector/c21a4f9f`; ZIP SHA-256
`73d6658df2a36332358113a141b1c3e1b4cd10e2f9dcc57c9825dfffca0c8bd0`.
The native DLLs are byte-identical to the accepted camera package.

The verified wheel was installed into the existing testing runtime without changing
PID 8652 or its loaded DLL. Its read-only live preflight rejected the minimap before
any movement: the content rectangle getter is not the generic getter assumed in the
initial fixture. The actual vtable `0x1169ec0` slot `+0x1c` points to `0x8ddc`, and
offline review of the frozen executable proves its direct jump to `0x56c3e0` copies
four rectangle integers from `this+4`. The guard and fixture are corrected to this
exact getter; the old generic slot is explicitly rejected. No guard was disabled.

The replacement package and repeated read-only preflight are required before any
walk. The prior helper pair was stopped for the update, the recorder had expired,
and no game restart or further movement occurred. Local evidence remains in
`navigation-inspector-3534418/correction-c9f3e16`, including the failure receipt.

## Verified destination package and running update

Current installed source: `8210ecf02b1a22c210c341ef0e41bfe710fb33ff`.
The exact committed package passed 1,668 Python tests (8 environment skips,
211 subtests), Ruff, VS2022 Win32 Release full and diagnostics-only builds,
18 native tests in each profile, wheel/source-package gates, installed entry point
and actual Tk panel. All 27 receipt entries matched disk and archive contents.

Local package: `artifacts/navigation-inspector/6555aa2c/navigation-inspector-acceptance.zip`.
ZIP SHA-256: `e88f7e937548f74d260384c6e85e0da1eb95b53f85fb0652cc69d607952ef9d7`.

| Artifact | SHA-256 |
| --- | --- |
| full/wonderbane-extension.dll | f08f99ea8dc8f8558971e3c00252b20df3ede58e00a723df012e4a14cd9071e7 |
| diagnostics-only/wonderbane-extension.dll | 83752e380d34da5abf0b18e6f44dfa3b6db2ef7a8b3b12d258b73c424ff755e1 |
| dist/shadowbane_lab-0.1.0-py3-none-any.whl | eb3897868be53b419cae1600328aeed4060ce2e13a02a3c9e971dd93ebd1ce19 |
| dist/shadowbane_lab-0.1.0.tar.gz | 9345e9fe6144d895ec17c6906ea0cb72bc9cad95138194605ecbdfabe646d103 |

Both native DLLs are byte-identical to the deployed camera package; the native
source tree is also unchanged. The wheel was updated in the existing runtime
`S:\ShadowbaneLab-Guided\20260904-inspector-3534418` without restarting the game.
The actual loaded DLL hash, installed source, PID 8652, creation FILETIME
134330013610671584 and native channel were verified after installation.
The corrected installed minimap reader passes against content rectangle
`(1713,17,1917,221)` and scale `0.27026087723288583` pixels per world unit.
Existing calibration files were verified and preserved rather than recreated.

The reconnected helpers are panel 3744, listener 9880 and recorder 8580. Camera
sequence reached 25,642 with 256 samples and zero drops. A read-only route check
found the player at LT 89009.2578125 / LG 44857.0625 in Sea Dog's Rest and a
45-unit westward candidate ending at LT 88964 / LG 44857. No corrected movement
has run yet. Fresh owner focus and stationary-arrival/trail validation are next.
Evidence and update receipts are retained under the existing local VM diagnostics
folder `navigation-inspector-3534418/correction-8210ecf`; earlier captures remain
at their original locations. No captures or packages are included in Git.

## Remaining acceptance pass

Use the [developer/owner handoff](handoffs/navigation-inspector.md) for the exact
sequence. The initial DLL and wheel were deployed together through the existing
prepared-client process. Verify the unchanged loaded DLL hash and replacement
wheel source identity in a new inspector capture.

1. Connect the exact testing client before /go; check open ground, slope and
   camera rotation. Confirm measured-trail alignment and ordinary/x-ray depth.
2. Capture the known tree/wall clipping route. Compare raw search, actual movement
   route, estimated clearance, original/learned blockers and real movement.
3. Exercise /pve approach, stall/replan, camp return and cancellation. Freeze,
   save and reopen one failure so the developer and owner can explain it together.
4. Compare overlay off/on cost and verify terrain, transparency and UI behavior.

Planned paths remain explicitly projected because final terrain elevation is
unavailable. Verify the measured LT/LG-to-world transform before accepting world
alignment. If the separate terrain repair is added, it requires its own verified
source and one combined boundary-tile check.

Current active todo: verify stationary arrival with the installed destination correction;
then compare normal/x-ray trail coverage and complete slope
and camera-rotation alignment, the bounded PvE scenarios and overlay cost/scene
checks. After the remaining live pass, review
and integrate PR #27, then retire the inspector worktree/branch when safe.
