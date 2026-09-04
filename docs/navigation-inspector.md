# Navigation inspector

Review branch: codex/navigation-inspector. [Draft PR #27](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/27)
targets codex/integrate-current-development while PR #25 is open. The feature base
is f2a5ca137b6d524c52bc492cc83081ee55929c71. The separate terrain material repair
is not included. The normal project checkout remains on main.

## Use the inspector

Install the acceptance wheel into the same Python environment that runs the
travel/PvE listener, and use the matching full-profile extension in the testing
client through the existing prepared-client deployment process. Diagnostics-only
deliberately has no inspector channel or draw hook.

Run shadowbane-navigation-inspector, choose the exact client, and Connect before
starting /go or /pve. The process identity includes PID, creation time and executable
hash. A second panel or publisher cannot claim the same client. With no armed
panel, ordinary movement does not start an inspector worker.

The panel and in-game legend distinguish raw search, the route currently owned by
movement, estimated clearance, original map blockers, learned blockers, costs,
objective/arrival radius, measured trail and real controller events. A failed
replacement search does not erase the route movement continues to follow.

Toggle layers independently. Character radius, uncertainty and margin are
operator estimates in world units; they do not change movement policy. Red
corridor segments overlap captured original blocker cells. A clear corridor only
means the captured model permits it. Costs/density do not identify exact trees.

Planned geometry uses a labeled projected map because final world terrain
elevation is not yet observed. Only measured trail vertices enter the world view.
Normal world lines use scene depth without writing it. X-ray is dashed purple,
distinct from the cyan visible trail. LT increases right and LG up in the
projected panel. World coordinates are X=LT, Y=measured altitude, Z=-LG;
alignment still requires the coordinated live check.

Freeze captures the current evidence; terminal failure freezes automatically by
default. Resume returns to live collection. Zone changes invalidate frozen live
placement. Producer/zone leases expire after two seconds, including frozen data.
The captured map remains inspectable in the desktop panel and near the top center
of the game, clear of the minimap. Once placement expires it is explicitly labeled
CAPTURE / PROJECTED ONLY and cannot draw any world trail, even with x-ray enabled.
The panel's Show in game and layer controls continue working after the producer
exits; closing or disconnecting the panel hides the in-game capture. Opening a
saved capture never publishes it into the game.

Save capture writes a bounded JSON file without overwriting an existing capture.
Default storage is LocalAppData/ShadowbaneLab/diagnostics/navigation-inspector.
Open capture supports layer toggles, pan/zoom and clearance reanalysis offline.
Evidence and source lists provenance, revisions, omissions and identities.
Return to live rebinds controls to the current live session.

## Source and build evidence

Capture identity records the installed acceptance wheel's source commit and
package version. At session start the worker enumerates the selected client's
loaded modules and hashes the actual extension's backing DLL. This is a file
identity, not a relocated memory hash. Missing or ambiguous module identity is
explicitly unavailable; a candidate DLL or package receipt is never substituted.

Run scripts/build_navigation_inspector_package.py from a clean committed tree
with Python 3.11+, build, setuptools>=77, wheel and the project test dependencies.
CMake and Visual Studio 2022 C++ Win32 are required; --cmake accepts an exact path.
The script exports that commit into a new ignored artifacts/navigation-inspector
directory. It runs full Python/Ruff gates, both Win32 Release builds and native
tests, verifies runtime source ownership in generated DLL projects, and builds
the wheel from the freshly generated source distribution.

The acceptance wheel includes the source commit metadata. The source distribution
contains native sources, the wire fixture, scripts and handoff. A fresh environment
installs the wheel with no dependency downloads and checks the installed entry
point and actual hidden Tk panel. Receipts contain source, profile, DLL, package,
contract and validation-log hashes. The archive contains source and both profiles;
no client executable, private capture, credentials or VM installation is included.

## Verification and remaining work

Planner/controller observer failure, active-route ownership, exact clearance
geometry, bounded snapshots, real Windows channel lifecycle and Tk replay are
tested. The native hidden-window OpenGL harness checks real occlusion, x-ray,
unchanged depth and state restoration with a nondefault GLSL program and multiple
texture units. Its measured costs are synthetic, not live-game acceptance.

- [x] Immutable planner/controller capture and behavior isolation.
- [x] Bounded history/replay, clearance audit and wire contract.
- [x] Windows transport, native channel and live travel/PvE ownership.
- [x] Native drawing, depth/state tests and desktop controls/replay.
- [x] Loaded-module identity and reproducible acceptance-package builder.
- [x] Build the committed source and verify the [acceptance package and receipts](navigation-inspector-acceptance-20260904.md).
- [x] Live projected-map persistence, minimap clearance, hiding and real saved-failure replay.
- [x] Correct camera ownership and verify both packaged profiles (3534418).
- [x] Current-client camera samples (3534418).
- [x] Correct bounded destination execution, build and install source 8210ecf; verify the live minimap preflight.
- [x] Short flat and slope walks: measured stationary arrival; flat trail coverage observed (8210ecf).
- [ ] Active: verify the ground-height source and correct/validate placement on both flat and sloped terrain. The owner reports a possible body-height origin.
- [ ] Normal/x-ray occlusion, bounded PvE and overlay cost/scene checks in the [developer/owner live pass](handoffs/navigation-inspector.md).

Draft PR #27 is the integration destination; a push is not an accepted merge.
Retain the task worktree until the live pass and integration are complete.
