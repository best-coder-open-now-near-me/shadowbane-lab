# In-game particles and trails

Status: integrated feature branch; combined-owner candidate and connected acceptance pending.

## Source and ownership

Exact common base: `14d117e8c5194c6dff55dac608b2d3f683187d31`.
Feature branch: `codex/particles-trails`, initially targeting
`codex/navigation-inspector` with dependency on PR #27. The normal project
checkout remains on main. No terrain branches were merged and no shared game
or VM was deployed. The native lifecycle/runtime-hardening developer owns the
combined candidate and its release version; this feature does not independently
retarget, merge, or replace the shared client. Candidate artifacts retain the
baseline extension version and must be identified by exact source and DLL hashes.

Shared changes to reconcile: native CMake source/test lists, `extension.cpp`
start/rollback, `cel_shading.cpp` scene boundary/present invalidation/shutdown,
Graphics Lab tab construction/connection, and the existing package builder.
`scene_draw` extracts the existing navigation GL guard; navigation uses that
same implementation. The selected-character developer is reusing this guard
and the attachment resolver. The graphics-control v2 ABI is unchanged.

## Implemented behavior

One configurable attachment at a time: local-player actor root or selected
character actor root. This is explicitly not a weapon, bone, model-local, or
rendered-silhouette attachment. Height is a world-up offset from that actor root.
The verified native position getter chain is read directly inside the extension,
so moving effects do not depend on a Python observation publisher or script.

Binding checks use the existing native position/zone profile offsets and reviewed
executable hashes. Two reads must agree on actor pointer, native object type and
UUID, position component/location, and current-zone pointer/type/UUID. Unsupported
getters, missing/read-failed pointers, out-of-range/nonfinite positions, incoherent
reads and unknown executables are rejected. UUID is the existing runtime identity;
no separate allocation-generation counter has been proven or claimed.

The runtime supplies emitter particles, button-triggered bursts, and a continuous
ribbon with shared endpoints at turns. Particles use camera-facing quads and
world-space velocity/gravity; ribbon width faces the current camera. Birth times
control expiry/fade. Particle quads and ribbon segments are sorted back to front
within this effect pass. Normal alpha and additive blending are available.

The pass runs at the reviewed world/UI boundary after scene composite and before
navigation/UI. It tests the game's opaque scene depth with LEQUAL, never writes
depth, and preserves graphics state through the existing tested guard. The pass
occurs after the game's translucent draws: it does not reorder those draws with
its own quads. Overlap with water/other translucent game effects therefore remains
a specific visual acceptance question. It is not an x-ray effect.

History clears on attachment loss, identity/zone changes, attachment selector or
height changes, teleport-distance violations, backward time, frame gaps over
250 ms, invalid camera/scene, context changes, disable, and shutdown. There are
no persistent GPU textures/buffers or allocation hooks to retire. Re-enable and
context recovery start new history; old bursts are not replayed.

Hard limits: 1,024 particles, 256 trail samples, 1,280 allocated quad slots,
500 particles/second and 256 particles/burst. Per-frame insertion is bounded.
Lower configured budgets are enforced and eviction/rejection counters are shown
in Graphics Lab. Core storage is fixed-size; no per-frame heap allocation.
The diagnostics-only DLL contains no effects runtime, control mapping, or draw
source. Its test executables may exercise effects independently.

## Controls and launch

Use the integration owner's verified prepared client and launch it through its
normal verified shortcut. Install/use the matching candidate Python wheel.
Open the existing Graphics Lab shortcut, or run:

```powershell
python -m shadowbane_lab.graphics_lab
```

Select the exact client, then **Particles / trails**. Choose the actor-root
attachment. Load **Azure wake**, **Embers**, **Violet ribbon**, or **Burst only**,
then **Apply**. Preset loading edits controls; Apply sends them. **Burst now**
sends a single burst token while enabled. **Disable / clear** clears history at
the next frame. Settings are native for the client lifetime; restarting the
client starts disabled. Closing Graphics Lab leaves the applied settings active.

Parameters include emitter rate, particle lifetime/speed/size/gravity, trail
lifetime/time and distance sampling, width, discontinuity distance, RGB/opacity,
world height offset, particle/sample budgets, burst count and additive blending.
Distance, size, speed and height use the same world units as native positions;
times are seconds. Depth testing is deliberately always enabled.
The tab reports applied/desired sequences, control errors, live counts, budget
drops, rejected attachments, resets, degenerate segments and rejected draws.
An absent effects mapping is reported as unavailable, including older packages.

## Automated validation and packaging

Run the existing `scripts/build_navigation_inspector_package.py` with the
configured build-tools Python. Optional `--output-root` selects a short local
artifact path. It archives the exact clean commit, runs Python tests and lint,
builds/tests both native profiles, verifies effects source exclusion, checks PE
machine type, builds the wheel/sdist, checks effect files, installs the wheel,
and constructs the real Graphics Lab with its effects tab from that installation.
It does not launch or install into the shared game/VM.

Production tests cover expiry, one-shot burst tokens, sampling, budgets,
teleports/gaps/zone and UUID changes, missing attachments, getter rejection,
cleanup, native control acknowledgements/malformed and torn writes, concurrent
shutdown/restart, actual GL effect occlusion, depth preservation, additive and
disabled draws, plus existing navigation state restoration regression tests.

## Consolidated connected acceptance

After owner reconciliation and a successful combined-source package run:

1. Confirm exact source/DLL/client hashes using the normal package verifier.
   Apply Azure wake on local root; move and turn the camera. Particles face the
   camera and the ribbon remains continuous. The origin is the actor root, with
   the explicit height setting; verify it is not being presented as a weapon.
2. Select a moving character and apply selected-root effects. Change/clear
   selection; history must reset. Zone/relog and target disappearance must leave
   no reused-object or cross-zone trail. Check rejected counts when unavailable.
3. Walk behind an opaque tree/wall: hidden effects remain occluded. Check water,
   native translucent effects and UI layering as the remaining ordering question.
4. Exercise all presets, Apply, Burst now, opacity/width/rate and Disable/clear.
   Each burst click applies once; disable clears without stale re-enable history.
5. Teleport and alt-tab/resize or perform the supported graphics reset. Check
   no spanning trail, stale camera placement or graphics-state damage.
6. Compare existing performance telemetry with effects disabled, default, and
   configured maximum budgets during the already-established owner scenario.
   Record frame-time impact and counters. This does not reopen basic navigation,
   obstacle traversal or rune-hunt investigation.
7. With the diagnostics-only package, the tab must report unavailable and no
   effects may appear.

Remaining todos: finish exact feature package receipt; reconcile actual shared
changes with the named lifecycle owner; verify the combined source/package;
perform one coordinated connected acceptance covering the live questions above.
No connected-client behavior or performance has been certified by offline tests.
