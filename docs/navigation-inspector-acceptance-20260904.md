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
45-unit westward candidate ending at LT 88964 / LG 44857. At that preflight no corrected movement
had run yet; the subsequent owner-assisted result is recorded below.
Evidence and update receipts are retained under the existing local VM diagnostics
folder `navigation-inspector-3534418/correction-8210ecf`; earlier captures remain
at their original locations. No captures or packages are included in Git.

## Accepted short walk with measured arrival

After the owner focused the game, installed source `8210ecf` ran one production
A* route from LT 89009.25 / LG 44857.0234375 to LT 88964 / LG 44857 with a
five-unit arrival radius. Four accepted inputs preserved that same absolute
destination; there were no replans, partial routes or direct fallback. The runtime
recorded an arrival candidate at 4,078 ms and confirmed settled arrival at 5,156 ms.
It sent no synthetic stop click. Final position was LT 88963.59375 /
LG 44857.046875, approximately **0.409 units from the target**.

Nine subsequent read-only samples spanned **5.243 seconds**, with LT unchanged
and only **0.015625 units** of horizontal variation. This run did not reproduce
the prior continued movement after reported arrival. The saved capture has
18 measured trail points and all 17 measured-height render segments, zero omitted
lines/trail points and zero dropped observations. It records the actual installed
source and loaded DLL identities. Session: `4957602773149593471`; capture SHA-256:
`51bc1a23efc1ac362153914e05ecbebc291869e1ea1ba1be0f8e5fe2395a494f`.

Normal depth rendering was enabled and x-ray was off. Asked whether the cyan
trail stayed on the ground and covered the route, the owner confirmed that it
**looked good**. The recorded frame also shows the cyan trail in the game scene.
This initially accepted the short arrival and visible-trail check. The later
owner clarification below reopens ground-contact alignment on both flat and sloped
surfaces; stationary arrival remains verified.

Local evidence under `navigation-inspector-3534418/correction-8210ecf` includes
`destination-walk-start.json`, `destination-walk.json`, `destination-post-arrival.json`,
`destination-walk-capture-4957602773149593471.json` and `destination-walk-audit.json`.
Eight original screenshots and their UTC index are in the ignored worktree directory
`artifacts/navigation-inspector/live-20260904/destination-walk-*`.

At that checkpoint, the next todo was to move to a clear nearby slope with the owner and check trail alignment
while rotating the camera. Then compare normal/x-ray against a known obstruction,
exercise the bounded PvE scenarios and measure overlay cost/scene behavior.

## Slope/camera test and revised height acceptance

The owner restarted the session, then positioned the character on a hillside.
The same verified wheel/DLL now runs as PID 3284, creation FILETIME
134330094182597688; panel 9124, listener 6828 and recorder 2528 were reconnected.
Runtime integrity and source/DLL identity passed without reinstalling or copying
older preferences. New evidence is in `navigation-inspector-3534418/resume-20260904-1529`.

A short northward route to LT 88755 / LG 44689 climbed from measured altitude
8.825692 to 23.926771 (**15.101 units**). It confirmed stationary arrival 2.907
units from the five-unit-radius target. Nine subsequent position samples over
4.927 seconds varied only 0.00390625 horizontal units. Thirty-one camera samples
show a 101.740-degree change in forward direction; camera sequences advanced
2948..3012 with zero producer drops and verified, successful scene boundaries.

The route crossed from Vorringia into Sea Dog's Rest. The inspector clears prior-zone
history by contract, so the final capture contains nine positions and eight measured-height
segments from the latter part of the climb. There are no omitted lines or dropped
observations in that context. Session `2905256194675038123`; capture SHA-256:
`127ab0cae61623a1cf3bd57c5654103be2caf1f2d0d5b8d355f9c9f13bf08435`.

**Ground alignment is not accepted.** The owner found camera control difficult and
reported that the line seemed to originate midway up the character rather than
being attached to the hillside. They then clarified that the same height offset
may have existed on the flat walk, where the viewing angle was less revealing.
The earlier short walk still verifies arrival and visible trail coverage; it no
longer supports ground-contact acceptance. Both flat and sloped grounding need
verification after the height source is understood.

Source tracing shows no added vertical lift in either Python geometry or native
`WorldLines`: the renderer receives the player getter's Y unchanged. The exact
getter thunk `0xa3d0` reaches `0xccd50`, which copies the vector at
`[[player+0x4b0]+0]+0x20`. This proves canonical player-position data, not the
semantic claim that Y is foot contact or terrain elevation. Actor-origin height
is a hypothesis to verify, not a reason to subtract an arbitrary constant.

Retained evidence includes `slope-walk.json`, `slope-walk-start.json`,
`slope-post-arrival.json`, `slope-camera-samples.json`, `slope-walk-audit.json`
and `slope-walk-capture-2905256194675038123.json` in the resumed diagnostics folder.
Nine screenshots plus their index remain under ignored `live-20260904/slope-walk-*`.
No additional movement or renderer-offset change has been made.

At that checkpoint, the active todo was to establish the exact player/ground height semantics and durable
surface-placement source, then repeat flat and slope alignment before proceeding
to normal/x-ray occlusion, bounded PvE and overlay cost/scene checks.

## Exact ground-height contract and correction

After the VM restart, the exact `3534418` runtime was verified again as client PID 3544,
creation FILETIME `134330368496400834`, executable SHA-256
`a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8`, installed source
`8210ecf02b1a22c210c341ef0e41bfe710fb33ff`, and loaded DLL SHA-256
`f08f99ea8dc8f8558971e3c00252b20df3ede58e00a723df012e4a14cd9071e7`. New evidence is in
`navigation-inspector-3534418/resume-20260904-1915`.

A bounded read-only probe captured five coherent samples and verified the exact
`ArcLocationInfoImpl` and `ArcCollisionInfoImpl` implementations. Actor-origin Y was about
28.518, client-resolved ground height was 26.25, explicit height was zero and collision minimum
Y was about -2.268. The client equation
`actor_y = ground_y - collision_min_y + explicit_height` reconstructed the canonical origin
with maximum error `7.15e-7`. The collision minimum varied slightly with animation, which
rules out a durable fixed subtraction. The retained receipt is `ground-height-contract.json`.

The implementation now preserves actor-origin altitude for all movement and PvE decisions,
while inspector events use verified resolved ground height when available. Ground enrichment
is optional and falls back without failing the canonical position reader. The full regression suite passes with 1,673 tests, 211 subtests and seven expected skips;
the repository-wide lint gate also passes. Live flat/slope acceptance still requires the corrected package.

Source `96d903675c123b1c5cf1cc4513ac345186bd4eae` built as package `e3ed8b4c`; archive
SHA-256 is `1b0fa714523a724f56648e5a499476a4ed6a362f68696624c40122ebd87d9bcd` and wheel SHA-256
is `322fb969e578568ae7cdcb21992bfc46d89c5d10942e9724fc7643bb137a331e`. The wheel replaced
the Python layer without changing the loaded DLL. Exact client/source/DLL identity passed after
installation. Panel 5200, listener 1352 and recorder 1452 were live with empty error logs.

The corrected owner-assisted slope run started at LT 88512.734 / LG 44654.117 with resolved
ground 0.249 and produced 35 ground-height trail points across an 11.845-unit descent. Session
`1388190087102714464` retained all 38 events and all 35 trail samples with zero omissions or
producer drops. Trail Y ranged from -4.569 to 6.182 in the frozen capture. The owner confirmed
perfect surface placement before reaching water, so **slope ground alignment is accepted**.

The movement result is deliberately not accepted. The client reached water, replanned away from
the requested destination and ended `astar_route_not_found`; the client continued toward its last
bounded click before settling. Its navigation context reports `sparse navigation cells; no terrain
height layer`. This is retained as a focused water/client-server navigation failure, including
`ground-slope-route.json`, `ground-slope-walk.json`, `ground-slope-post.json`, camera samples and
`ground-slope-capture-1388190087102714464.json` under
`resume-20260904-1915/ground-96d9036`.

The first dry-flat harness invocation requested a four-unit arrival radius, which the command
contract rejected before input. The character did not move and the frozen water failure remained
intact. The corrected invocation used the required five-unit radius and created fresh session
`2005051010612397357`. It moved 18.555 units over dry flat terrain, kept resolved ground height
at 26.25, and confirmed stationary arrival 1.412 units from the destination. All ten trail samples
and all nine events were retained with zero omissions or dropped observations. The owner
confirmed the cyan line remained at the character's feet for the whole walk. **Flat and slope
ground alignment are accepted.** Evidence is retained as `ground-flat2-*` under the same
`ground-96d9036` folder.

## Tree-obstacle diagnosis and recovery correction

The first normal-depth tree run used the owner's identified tree immediately north of the
character. Session `4060971429726872299` moved about two units before stalling against the tree,
then retained 67 trail samples and 77 events with no producer drops or omissions. It recorded
nine replans, eight stalls and eight escape plans before the bounded session timeout. The owner
confirmed that the character hit the tree and that the learned blocked-cell box appeared.

That capture exposed an execution-order defect rather than a missing stall detector. The
low-level controller planned a physical escape, but the A* wrapper intercepted the first escape
decision and replanned before its input was dispatched. Because the deliberately short test goal
shared the learned 20-unit cell, the planner also excluded the goal cell from blockers and kept
returning the same northward click. The result is retained under
`ground-96d9036/obstacle-tree-north`; it is diagnostic evidence, not an accepted obstacle pass.

The owner enabled x-ray and session `7565812963352424179` retained 62 trail samples and 70 events
with no producer drops. It reproduced the same recovery-order defect and timed out after seven
replans. The run is retained under `ground-96d9036/obstacle-tree-north-xray`. X-ray visibility was
not accepted before attention moved to correcting recovery.

The source correction applies the owner's durable rule to both `/go` and `/pve`: record the last
meaningful measured ingress direction, make the first stall-recovery click its exact reverse,
physically dispatch that backtrack, and then replan from the backed-out position around the learned
blocker. If no ingress sample exists, recovery reverses the active route segment.

Source `46ab5369265a3c07ac9971cd42230e9a526bdc97` built as package `fc54d331`; archive
SHA-256 is `89b44e206eebfdebc4ede11fa47d2af72f01f28f2c68660583e8bafa7007f9a0` and wheel
SHA-256 is `e732592e462201e25fc0d796aa8b3d38f4e2da62d2607fcd61093b4fa85e18bd`. The full
Python suite passed with 1,673 tests, 211 subtests and eight expected skips; Ruff, both VS2022
Win32 Release profiles with 18 native tests each, source/wheel packaging, installed entry point
and actual Tk panel also passed. The full DLL remains byte-identical to the loaded DLL at
`f08f99ea8dc8f8558971e3c00252b20df3ede58e00a723df012e4a14cd9071e7`.

The wheel replaced only the Python layer in the same exact testing runtime. Client PID 3544,
creation FILETIME `134330368496400834`, executable/DLL identity and inspector channel passed
after installation. Panel 9124, listener 7324 and recorder 8984 were verified with empty error
logs. At the tree collision the optional ground query was unavailable while canonical actor
position remained coherent, exercising the intended non-failing fallback.

Normal-depth session `238701332475333700` used an 80-unit northward goal so the tree's cell was
an intermediate blocker. After the confirmed stall, the controller physically moved 11.934 units
south from LG 45045.832 to LG 45033.898 before the learned-obstacle replan. The final plan retained
learned cell `(4440, 2253)`, routed west through `(88790, 45050)` and then north around it. The run
used one replan and no direct fallback, retained all 42 trail samples and 31 events with no
omissions or producer drops, and confirmed stationary arrival 4.15 units from the goal. The owner
visually confirmed the backtrack and detour as very successful. The roughly 27-unit westward arc
was the adjacent center on the 20-unit planning grid and was accepted as conservative but bounded.
**The south-to-north physical backtrack and learned-obstacle A* recovery scenario is accepted.**
Evidence is retained under
`resume-20260904-1915/recovery-46ab536/tree-intermediate-normal`.

The first x-ray return used a goal only about 14 units beyond the collision and repeated the known
goal-cell exclusion case; session `4873700326468364340` is retained as a rejected harness run.
Extending the destination farther south produced session `2218625880244719481`: it physically
backed 12.879 units north, learned cell `(4440, 2252)`, replanned west, retained all 48 trail
samples and 37 events, and arrived 2.84 units from the goal with one replan. The owner was not
watching the overlay, so this verifies the reverse-direction machine path but not x-ray visibility.

The next observed x-ray run approached the same tree from farther south. Session
`7641079418200662238` retained all 178 trail samples and 123 events, but timed out after eight
backtracks and eight replans. The owner saw the character repeatedly hit the tree and backtrack
instead of turning. Its final plan exposed the direction-dependent defect: the nearly due-north
route learned `(4441, 2253)`, the northeast cell, while the tree corridor was `(4440, 2253)`.
When the 15-unit probe remained in the current cell, the fallback treated any nonzero cross-axis
delta as a full diagonal step; a sub-unit LT rounding difference therefore moved the blocker east.

The source now selects the fallback neighbor by the first grid boundary crossed by the continuous
movement ray. The exact live coordinates learn `(4440, 2253)`, while a true corner crossing remains
diagonal; an end-to-end controller regression proves the replacement plan contains a side detour.
The full suite passes with 1,677 tests, 211 subtests and seven expected skips; Ruff also passes.
This correction needs a source checkpoint before the owner's selected local 10-unit subgrid
refinement and the next live x-ray pass. Foliage is rare but forms dense patches, so refinement
must preserve every occupied or uncertain coarse foliage cell across all of its subcells. It may
tighten the path around a patch boundary but cannot infer unobserved gaps inside it.

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

Current active todo: checkpoint the boundary-crossing correction, add a local 10-unit refinement
around the first learned-blocker detour, then repeat the observed x-ray pass. After that, run
bounded PvE and overlay cost/scene checks, review and integrate PR #27, and retire the inspector
worktree/branch when safe.

## Refined tree route and tighter initial backtrack

The current-version client ran the locally refined route from LT 88826.32 / LG 45039.13 to an
80-unit northward goal. Session `5218318916770432677` recorded one stall, one physical backtrack
and one replan. The final plan used `astar_refined_final` with 10-unit cells, retained learned
cell `(8882, 4504)`, and routed through `(88805, 45025)` and `(88805, 45065)` before the goal.
All 46 trail points and 36 events were retained with no omissions or producer drops. The run
settled 0.79 units from the goal. The owner visually confirmed that the refined route granularity
was good and that the x-ray diagnostic was visible, but found the initial pullback as broad as the
earlier recovery. Its destination was still capped by the general 50-unit click distance and the
measured retreat was about 13.6 units.

Source `7e719d6fa2a524574e1813a0f76cfe1634b2440f` gives the first physical
`escape_backtrack` decision its own 10-unit destination limit. The general click limit and later
escape maneuvers are unchanged. Exact controller, A*, and PvE regressions cover the new distance
and its interaction with a smaller global click cap. Package `776defa9` passed 1,685 Python tests,
211 subtests and eight expected skips; Ruff; both Win32 build profiles with all 18 native tests;
wheel/source packaging; and installed entry-point and Tk panel gates. Its wheel SHA-256 is
`711bfe1c653a9c8b742d85ff6b80aaedcd9cf4df11b5ef1d47e340d6dd8266ef`.

The wheel was installed into the same running client without replacing the executable or native
DLL. Client PID 1940 and creation FILETIME `134330468660427387` remained unchanged. The verified
executable SHA-256 is `bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87`;
the loaded DLL remains
`65c67e8e05397b8acab5f3e01a4e566a1f7c75fcec99250c5a7bcb77ffee8fd2`.

Watched session `5119146404273284310` then approached the same tree from LT 88829.55 /
LG 45039.87. It encountered two physical blockers while resolving the route. Both backtrack
destinations were exactly 10.00 units from their stall positions. The first produced 11.10 units
of measured retreat; the second produced 6.77 units before the next escape/replan transition.
The final refined plan retained cells `(8882, 4504)` and `(8884, 4506)` and cleared the tree.
All 51 trail points and 56 events were retained with no omissions or producer drops. The owner
accepted both pullbacks as tight enough.

That run crossed within 0.41 units of the goal, then continued to a stationary point 5.52 units
away and correctly ended `arrival_not_settled` for the five-unit radius. The boundary miss is
retained separately from the accepted recovery behavior. Private evidence is under
`resume-20260904-1915/refinement-e8b24b5/tree-backtrack-10-confirmation`.

Next todo: run a cold and warm pair through a dense foliage patch. The cold pass starts with an
isolated empty learned map and must recover from first contact. Restart the production listener
from the saved schema-2 map before the warm pass, return to the same approach, and verify that
the remembered 10-unit cells shape the first route without repeating those contacts. Bounded PvE
and the remaining overlay cost/scene checks follow.

## Dense-terrain persisted-memory acceptance

The owner placed the character at LT 85984.69 / LG 71111.93 on the edge of a dense foliage
patch in Ashfell Plain. A read-only terrain probe selected the southbound corridor from measured
client data: all eight 20-unit center cells and 23 cells across its three-cell width carried
uncertain object-density cost, while the north and west corridors carried none. Both accepted
passes used the identical five-unit-radius destination at LT 85985 / LG 70972.

The cold pass ran through the production chat listener with an isolated nonexistent learned-map
path. It made ten accepted clicks, encountered one physical stall, issued one exact 10-unit
backtrack and performed two pathfinding replans before arriving 3.047 units from the goal. It
atomically wrote schema 2 with coarse parent `(4298, 3554)` and refined 10-unit cell
`(8597, 7109)`. Inspector session `2107490049288739348` retained all 60 trail points and 37 events
with no omissions or producer drops. Preserved capture SHA-256:
`ed3a01a7101c2735af7d9a856bacd028af81532e9d3e4c2032328cbed8174df3`.

The listener and recorder were then stopped and recreated against that exact saved file. Startup
verified schema 2, 20-unit parent size, 10-unit refined size, one parent and one refined blocker.
The loaded map SHA-256 was
`d4f86ccdc32e5d289a66d2a902459b03c612bfc4db208363ce007d9f4ea35ddd`.
After the owner returned to the recorded starting side, the warm pass made five accepted clicks,
with zero stalls, zero backtracks and zero pathfinding replans, and arrived 3.155 units from the
goal. The map hash remained byte-for-byte unchanged, proving avoidance from loaded memory rather
than relearning. Session `8352064271430055971` retained all 39 trail points and 16 events with no
omissions or drops. Preserved capture SHA-256:
`f431ebacd38e6d403a5eb0beed54b75cad282322aa201ea0f09d785532c9cc26`.

The loaded refined child remains in schema 2; the warm route's initial global plan conservatively
avoided its 20-unit parent and used waypoint `(85970, 70990)` before the final destination. The
owner accepted that behavior after observing both successful passes. **Cold obstacle recovery,
persisted memory across listener restart and warm dense-terrain avoidance are accepted.**

The isolated test listener was retired. The normal source-verified listener, recorder and panel
were restored as PIDs 1704, 8688 and 7900 against unchanged client PID 1940. Private maps, logs,
receipts and captures remain under `refinement-e8b24b5/dense-memory-7e719d6`.

Next todo: exercise bounded `/pve` approach, a real stall/replan using the shared recovery path,
camp return and cancellation. Then finish overlay cost/scene checks, review and integrate PR #27,
and retire the inspector worktree and branch when safe.
