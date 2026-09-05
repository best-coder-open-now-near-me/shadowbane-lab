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

Remaining todos: reconcile actual shared
changes with the named lifecycle owner; verify the combined source/package;
perform one coordinated connected acceptance covering the live questions above.
No connected-client behavior or performance has been certified by offline tests.

## Verified feature candidate

Draft PR: https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/28

Exact tested/packaged source: `e1add65b4368a3eb1c5a10c1ccd70f23521c4130`.
The subsequent receipt update is documentation only. The feature is outside
both the navigation branch and main pending integration-owner reconciliation.

Local package: `E:/Projects/shadowbane/artifacts/particles-packages/80cb5bc6/navigation-inspector-acceptance.zip`.
It retains the existing package builder's filename and contains the effects
handoff, both native profiles, wheel/sdist, archived source and validation logs.
Package SHA-256: `7913caa2742224cac20bff74f27fd578efcd9c3bb7a64cd954300b37b3845d25`.
Full DLL: `fe09b412634010f52943447450b5283a7f6d44a993fb10ac062f8508c63b2fef`.
Diagnostics-only DLL: `2b50db4d63dc24469c846c371f676e25659a053b23f41a21765ba43a7599a658`.
Wheel: `267417504f7af59fea6a96e92cc277cedd2f72e2d1f5200d509d5525e67ce03e`.
The adjacent `receipt.json` records all component hashes and executed commands.

The exact-source pipeline passed 1,689 Python tests and 223 subtests, with eight
skips. A focused skip audit found seven unavailable symlink-permission cases and
one Tk display condition. Both separate installed-panel smoke tests passed,
including the actual Graphics Lab Effects tab. Ruff passed. Both Win32 Release
profiles passed all 20 native tests. Source membership checks confirm effects are
excluded from the diagnostics-only runtime DLL. CI Python 3.11/3.12/3.13, lint and
PowerShell checks passed at the receipt audit; remote native jobs were still
running (local native checks passed).

Retained local evidence: final package directory `80cb5bc6`, earlier superseded
package `5d2991b4` (source `5957bf9`), and development builds
`E:/Projects/shadowbane/build/particles-full` and `particles-diagnostics`.
These generated artifacts are ignored and were not pushed with source. The
feature worktree remains retained for the combined-candidate verification.
No other checkout was edited; the normal shared checkout remains clean on main.

Integration owner identified: task `01a070ce-f816-7b32-8673-904c6f406c7a`,
branch `codex/native-lifecycle-hardening`, based on the same pinned source.
The exact feature/package hashes and shared-file contract were sent directly.
Confirmed combined pass order: scene composite -> selected cue -> particles ->
navigation -> UI. The cue must restore scene depth, framebuffer, viewport and
camera state before effects draw. Effects never write depth. The owner controls
the combined version, lifecycle admission/drain and original call-through.

Next active todo: receive the owner's combined source/package SHA and verify
this feature against it. Peer coordination with the selected-character feature
has shared the renderer guard and resolver; it does not substitute for the
owner's combined candidate. No manual acceptance is requested until that
candidate is verified.

## Independent combined-checkpoint verification

The integration owner supplied `50ad9e1dd83a67de3bc814a098dc4230b0393299`
from `codex/native-lifecycle-hardening` for feature compatibility verification.
This includes particles `21e884b` and cue `782aead`. It is a dependency checkpoint,
not the final acceptance candidate: required lifecycle/durable-state repairs and
cue material coverage were still in progress when supplied.

The effects developer fetched and archived that exact commit into the feature
worktree's ignored `artifacts/combined-50ad9e1/source`, without editing the owner's
checkout or changing the feature baseline. Independent Win32 builds are retained
at `E:/Projects/shadowbane/build/pc-50ad-full` and `pc-50ad-diagnostics-only`.

Effects core, attachment resolver, runtime and shared scene guard match the
previously verified feature source. The reviewed integration preserves camera
validation, composite -> cue -> effects -> navigation -> UI order, both Graphics
Lab connection/cleanup paths and native source ownership. Project-file checks
confirm each effects runtime source appears exactly once in full and zero times
in diagnostics-only.

Both profiles built successfully. Each CTest run passed 23 cases and skipped the
binding CLI test because its private executable argument is not in CTest. The
explicit binding verifier then passed for both builds against the existing
reviewed local client: exact code, both relocations, and every-byte drift
rejection. No executable was copied or deployed. Effects rendering, depth/state
restoration, lifecycle and shared guard regressions passed in the combined build.
Combined Python effects/cue/control/navigation-panel selection passed 54 tests
and 12 subtests with one Tk display skip. Graphics Lab and package-builder lint
passed.

Dependency-build DLL hashes (not final package identities):
- Full: `0ea28e431bad5120de6389b3067aa60e4c34a3a7cda497d5d163534c095a7f6a`.
- Diagnostics-only: `bd8fcc1f15babb32f35537bdd4a29044ce333891d1efd99ffe71bb6b97a084fd`.

Two package-builder review notes were sent to the owner: deduplicate repeated
source-contract names, and isolate the selection-panel smoke test from real
client discovery just as the effects-panel smoke test already does. No effects
compatibility blocker or feature-code fix was found at this checkpoint.

Next active todo: review the owner's final repaired source/package delta and
confirm effects compatibility before consolidated connected acceptance. This
checkpoint result does not certify future lifecycle changes or extend the old
feature-package receipt to a newly combined DLL. Sky/movement rolling additions
remain separately owned and do not reopen completed particle implementation.


## Native transparency requirement: confirmed unresolved

Focused review against owner source `8961fad07ff00c40b511f5b8f9562669069aad39`
confirms a compositing defect, not merely a live appearance question. The existing
WGL regression now includes a reference native-style red alpha-0.5 foreground
quad and a blue particle behind it. Both use actual GL depth/blending and the
production effect renderer; this is a controlled test, not a captured game frame.
The expected RGB is `(127, 0, 128)`. At the current pre-UI effects position:

| Native surface | Actual RGB | Failure |
| --- | --- | --- |
| Depth writes off | `(0, 0, 255)` | Foreground transmission is lost |
| Depth writes on | `(127, 0, 0)` | Behind effect is fully rejected |

Measured on NVIDIA OpenGL 4.6.0 / driver 596.36, independently built from an archive
of the exact combined commit with only the test file overlaid. Source is retained
under ignored `artifacts/combined-8961fad/source`; build is
`E:/Projects/shadowbane/build/pc-8961-full`. Production effects draw and scene guard
are unchanged between the feature head and that checkpoint. The normal regression
passes reference arithmetic and GL restoration but prints `UNRESOLVED`; it does
not assert that this composition is correct. Run the explicit requirement probe:

```powershell
& E:/Projects/shadowbane/build/pc-8961-full/Release/wonderbane_extension_navigation_draw_test.exe --verify-native-transparency
```

It exits 1 for both unmet transmission cases. This is an outstanding acceptance
requirement; the previous green opaque-depth tests do not cover it. Moving all
effects before all native transparent surfaces would invert the error for effects
in front and is not a fix. A durable solution needs native/effect depth ordering
or preserved transparency contributions. No new hook/stage is installed here.

Sky-owner evidence identifies a native sorted world queue at RVA `0x79c730`,
virtual entry draw at `0x79c792`, and comparator thunk RVA `0x19f79 -> 0x1c0dc0`.
The comparator's byte `+0x10` and float `+0x14` meanings are not yet verified as
transparency categories/depth. These are investigation leads, not an approved
binding. Shared hook changes remain integration-owner controlled.

Next active todo: resolve native ordering with the integration owner using reviewed
queue evidence, then verify the repaired combined package before visual acceptance.


Read-only queue follow-up confirms the comparator thunk was originally reported
as VA `0x419f79` (image base `0x400000`), therefore RVA `0x19f79`.
RTTI identifies shared comparator users including `ArcCharacterRenderWrapper`
(vtable RVA `0x1149ed0`), `ArcRenderQueueCallback` (`0x1149e88`), sky, line lists,
and start/end rendering and lighting pass wrappers. Queue insertion at RVA
`0x4d9830` invokes virtual `+8`; traversal at `0x79c730` invokes virtual `+4`.
Metadata constructor `0x51c420`, called with wrapper+8, initializes category and
float key to zero, and installs a default shader pointer. Sky enqueue `0x552570`
retains these defaults. The comparator sorts nonzero-category unequal float keys
descending, then shader priority/address and other address tie breaks. The actual
world-distance calculation and material category assignment remain unverified.
Because pass markers also use this comparator, arbitrary insertion based solely
on the byte and float would risk breaking multipass renderer boundaries.

Read-only inspection scratch is retained at
`artifacts/combined-8961fad/inspect_queue.py`; it reads the existing private binary
in place and emits only selected disassembly/addresses. No executable or capture
is committed. Full cross-feature GPU cost and repaired-stage correctness remain
unmeasured; the existing harness timing of navigation alone is not evidence of
combined cue/sky/effects performance.


The requirement probe now covers front and behind effects against both native
depth-write modes. Front effects produce the correct blue pixel in the current
late pass; the same two behind cases remain red. A separate early-pass reference
confirms that moving every effect earlier incorrectly blends native red over a
front particle. Normal GL regressions pass; the explicit transparency gate still
exits 1. Production effects/guard sources are identical in owner checkpoint
`8cf0683e944081bd5fa8b09d77dfa2e7aa8a0ada`; this comparison does not constitute a
full build or package verification of that checkpoint.

Further static evidence from the cue developer was independently checked:
character enqueue `0x1cb100` delegates to `0x1c4340`, which calls metadata writer
`0x1c4150`. That writer obtains the category through `0x1c3380`: render+0xcc less
than `0.995` yields true, otherwise linked material fields/guards determine it.
It writes zero to wrapper+0x14 immediately before tree insertion. This is evidence
of a material/opacity category, not proof of a usable spatial ordering key.
A scan of x87 floating writes did not establish a later native depth-key writer;
integer copies or other paths have not been ruled out.

The exact missing contract for a native queue correction is a reviewed per-entry
depth/material ordering and draw boundary covering the contributing transparent
geometry while preserving native pass markers. A retained-transmission approach
would instead need complete blended-fragment capture (including display lists,
immediate draws, shader alpha) and bounded handling of distinct effect depths.
Neither contract is currently verified. This is not a request for the owner to
approve an approximation or repeat navigation testing.


## Bounded queue preparation review

Read-only call-graph follow-up found traversal thunk RVA `0x15a0f` targeting
`0x79c730`, with direct callers `0x797a2c` (auxiliary/global queue at RVA
`0x16aaec8`) and `0x79817e` (main queue at current EBX+0xf8).
The main sequence is sky virtual enqueue at `0x798139`, preparation via thunk
`0x1d9e4 -> 0x1ca470`, object virtual+0xc enqueue loop
`0x79815c..0x798172`, then direct traversal at `0x79817e`.
There is no separate re-sort or key-rewrite call between that enqueue loop and
traversal. This does not rule out behavior inside the virtual enqueue/draw calls.

Preparation `0x1ca470..0x1ca962` resizes and initializes wrapper pools, resets
used counters, and configures shader records. The inspected instructions do not
assign camera-depth keys. Pass marker constructors `0x4e1c20`, `0x4e1cd0`,
`0x4e1d80`, `0x4e1e90` use category zero and shader priorities -10000, +10000,
+1000, +2000 respectively. Callback shader constructor `0x4eff30` stores that
priority at shader+8, which the shared comparator reads. Thus pass markers cannot
be treated as a general spatial transparency boundary.

This bounded path has not yielded a certified correction. The remaining missing
fact lies in virtual enqueue/draw material behavior and a complete spatial merge
contract; another main-loop late/early hook would not resolve it. The cue developer
owns the non-overlapping `0x1c3380` material / `0x1cb700` character-draw review.
The integration owner received these exact paths. No new hooks, production
changes, live observation, build, or deployment were made for this read-only
follow-up. Required transparency probes remain red.
