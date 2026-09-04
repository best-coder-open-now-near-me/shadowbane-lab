# Navigation inspector acceptance package — 2026-09-04

The initial acceptance package is built and verified and was deployed into a new,
isolated testing-VM runtime. Live acceptance is in progress; nothing is merged.
The package and hashes below describe the initial e380e0f build. A Python publisher
correction is being packaged after the first joint movement test.

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

Next: validate and install the corrected wheel, restart only inspector helpers,
and repeat the short route while capturing actual published evidence. Keep the
verified game process and DLL running. Movement is confirmed; overlay rendering,
alignment, replay and PvE acceptance remain pending. Private runtime identities,
logs and captures stay in the local VM evidence directory.

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

Current active todo: deliver the publisher correction and resume this bounded live pass. After it passes, review
and integrate PR #27, then retire the inspector worktree/branch when safe.
