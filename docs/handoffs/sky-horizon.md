# Sky and horizon integration

Feature branch: `codex/sky-horizon`, worktree `.worktrees/sky-horizon`.
User-pinned start: `0c807ee774859cc3f17f9ebc04d3f0a900bd0428`.
Consumed shared owner dependencies through `44d926166220a0e5254ec90e6c21914d273270b0`
(merged as `d689fd3`).
PR destination: `codex/native-lifecycle-hardening`, then owner-reviewed integration
into `main`. No shared client/VM replacement, main merge or deployment is authorized.
PR: https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/30
The feature is wired in source; combined acceptance packaging remains gated.

## Rendering evidence and agreed stage

Read-only executable SHA256 `feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff`.
The existing reviewed Display routine explicitly sets clear color RGBA(0,0,0,1)
at RVA7980e3..7980ee, then clears at RVA798109. Its sky stage enqueues a native
ArcSky render wrapper; it is not an immediate sky draw. ArcSky virtual+0xc resolves
to RVA552570. Wrapper vtable11641d8 virtual+4 resolves via thunk22327 to5524a0.
The wrapper updates the native sky and enters its shader, then calls shader virtual+0xc
at5524dc (return5524df). ArcShaderSky vtable1162b34 Draw slot1162b40 resolves via
a213 to4f6010. Its empty layer list returns without drawing. Native optional cloud,
sun and sky geometry depend on layer and asset state; displayed color alone cannot
attribute a missing asset. No game archives are modified.

Owner approved the separate background stage in the existing task channel:
fresh independently verified current-frame camera upload -> reviewed main clear ->
background -> native world -> unchanged composite/cue/effects/navigation/UI order.
Existing camera publication still requires matching clear/pre-UI observations.
The sky path observes existing LoadMatrixf adapters at exact return51b1df/51bbb2,
verifies both complete source routines (including alternate branches), and requires
MODELVIEW stack1, no display list/immediate primitive, same context and byte-identical
view at clear. No prior-frame camera or pending published camera is accepted.
A current verified local actor/zone is required. Failed authority/state/asset checks
leave the native sky untouched. The alternate early return in camera routine51b4a0 occurs only when the local
player pointer is absent and delegates to51a9e0 (thunk1b932); neither routine
skips its upload for a stationary camera. Connected hook coverage remains a package
acceptance check, not a relaxed camera fallback.

After a successful early paint, only the exact native sky shader invocation from
the reviewed wrapper is suppressed. Native sky update and shader enter/exit remain.
No late depth-mask sky, world depth write, navigation/picking geometry, FBO copy,
extra present hook, or competing state guard is introduced. Sky is a bounded 64x32
screen mesh sampling an authored infinite-distance directional field; translation
is absent, camera rotation/projection and configurable yaw are retained. Horizon
haze joins the current fog color by default. It contains no finite decorative terrain.

## Content and lifetime

`assets/sky-horizon/clear-day.json` is the authored palette and cirrus layout.
`clear-day.sky` is the 520-byte packaged RCDATA201 asset, SHA256
`c4143315072e94413db211cc81164121ce8331af2a4497ab8229ac611cac73ce`.
Native startup verifies this identity and the complete reviewed binding. Graphics
Lab controls and package identity gates are wired; final combined package checks
remain in progress. Default startup is disabled.
Native settings use an exact PID/creation channel and reject torn/invalid settings.

All callbacks share RenderCallbackLease; startup/stop share RenderLifecycleMutation.
Original call-through survives stop. Generation/context/frame invalidation discards
observations. No persistent GPU objects exist; immediate rendering uses the single
scene_draw guard and leaves original depth/state intact. The pinned module owns RCDATA.
Shared edits are identified in cel_shading, CMake and scene_draw contract. The owner
extracted scene_context as a single pinned handler independent of cue startup; sky
requires its successful idempotent installation. Missing readiness refuses startup.
Context switches, failed switches and A/B/A reuse invalidate the sky observation.

## Checkpoint validation

Full Win32 VS2022 build passed. 26 native tests passed/skipped as declared (24 passed,
2 private-binding tests skipped in ordinary CTest). Sky binding was separately run
against the private executable: exact routines, both relocation directions and every
byte corruption rejected. Real-WGL sky test also passes: production asset/render,
unchanged depth and state, later translucency/alpha cutouts, wrong viewport/draw
target/FBO exclusion; private mapped-client startup, controls, stale camera refusal,
native call-through and stop/restart. No executable bytes or private capture is source.
Task outputs remain under ignored `artifacts/sky`; no shared VM changes.

## Active todos

- [x] Camera routine coverage investigation and native integration regression checks.
- [x] Graphics Lab sky/horizon/orientation/intensity/restore controls and persistence.
- [x] Shared context extraction, asset/wheel/sdist identity and both-profile build/exclusion tests.
- [x] Feature PR targeting the integration owner.
- [x] Verify sky against owner's combined source `c2f9c997870760bb1a347bd3a6006199038265b8`.
- [ ] Active: combined acceptance package after the required shared transparency gate passes.
- [ ] Focused connected acceptance: appearance, translation/rotation, horizon/fog,
      foliage/water, UI/minimap, toggles/context transitions and performance.


## Actual native sky observation

The existing read-only guest channel inspected the running reviewed client PID5212.
It reported an initialized ArcSky with one layer, a non-null texture object for that
layer, and all three optional native texture object pointers present. This rules out
an absent sky object/empty layer list in that observation; non-null texture objects
alone do not certify their GPU uploads or archive contents. The implementation does
not diagnose missing terrain or claim archive repair. Native clear is black, native
sky runs separately with fog disabled, and subsequent world geometry uses fog.
The replacement therefore owns the native background stage and joins the world fog
transition, instead of guessing a clear-color edit from the screen color.
Read-only script and unmodified output remain privately at
`artifacts/sky/read-native-sky.ps1` and `artifacts/sky/native-sky-observation.json`.
No new injection, client launch, input, archive change or VM deployment was used.

## Controls and connected acceptance

After the integration owner has a green exact-source combined package and performs
the authorized installation, use that package's Python environment:

```powershell
python -m shadowbane_lab.graphics_lab
```

Select the exact connected process, then open **Sky / horizon**. **Clear-day defaults**
loads the authored appearance; **Enable** validates/applies it. Orientation is degrees;
intensity changes appearance brightness, horizon elevation/width tune the fog transition,
and cirrus/sun/fog matching are separate controls. **Disable** ignores invalid pending
field edits and returns to native sky on the next frame. **Restore original** also
resets the sky settings. Neither command changes unrelated graphics/navigation settings.
**Save appearance** writes an atomic JSON preset with asset identity; **Load appearance**
loads it without changing the connected client until Apply. Startup defaults disabled.

Focused acceptance, once for the combined package:

1. Verify source, both DLL profiles, native resource and installed control identity
   from the normal package receipt. Confirm the sky channel is ready and applied
   sequence catches desired; require repeated successful draws while stationary.
2. Enable the default outdoors. Rotate/yaw/pitch and walk without rotating: the
   horizon/cloud field rotates with view and remains stable under player translation.
   Check overhead/backwards views for seams; orientation should rotate the field.
3. Look across distant terrain and fog with defaults, then adjust horizon transition
   and intensity. No terrain is added or concealed as a repair. Terrain, buildings
   and actors must retain their existing depth and visibility.
4. Inspect alpha-tested leaf holes, foliage edges, water/translucent objects and
   native particles. Sky is behind all world submission. Verify the combined cue,
   effects and navigation with the owner's existing accepted traversal scenario.
5. Check UI text, minimap, selection panels and previews; sky must stay out of their
   targets. Disable, enable, restore, relog/zone, resize and supported context changes;
   no stale scene sky, context errors or stuck native-sky suppression may remain.
6. Compare existing frame timings with sky disabled/default/enabled. Record the sky
   tab's background microseconds and refused frames along with normal telemetry.
   Rejection must be explainable (absent scene/context/camera); no guessed fallback.
7. Diagnostics-only DLL contains no sky resource/runtime and offers no sky channel.

Both Win32 profiles build. Sky/core/context real-WGL tests and private native binding
and runtime tests pass. The full Python checkpoint before the newest shared merge
passed1727 tests,9 skips,223 subtests;66 targeted sky/graphics tests passed. Exact asset
ownership was checked in both DLLs: present once in full and absent from diagnostics.
The real wheel/sdist carry exact content; the installed Graphics Lab sky tab opens.
These are development validations, not a substitute for the combined package gate.

## Current combined-package blocker

The integration owner's required particle/native-transparency test reproduces a
foreground-water ordering failure unrelated to early sky painting. The effects owner
is investigating that stage. Do not bypass this required test, certify an earlier
package against current source, or ask for connected acceptance before the combined
package passes. Root asked this lane to defer the full package run until that gate is
repaired. Source and targeted installed-wheel checks are published for integration;
there is currently no sky acceptance ZIP or authorized deployment.

Retained task artifacts: `artifacts/sky/nf` and `nd` native builds/logs, `dist` and
`installed` for wheel/sdist validation, and private observation scripts/output. The
initial `artifacts/sky/full` is a superseded automatic-toolchain build and is not a
validated package. The normal project checkout remains on main; this feature worktree
is retained for the pending combined package verification. No other worktree is changed.


## Combined source verification: c2f9c99

The integration owner merged sky4368f13 and cue8967438 at
`c2f9c997870760bb1a347bd3a6006199038265b8`. Sky implementation, assets, controls,
shared state guard and context handler are byte-identical to the verified feature
source. Reviewed intervening cel_shading and extension startup changes; sky continues
to use the independent early stage, original camera publication and shared lifetime.
Feature branch fast-forwarded to this source for verification; implementation is now
included in the integration destination, while package acceptance remains pending.

Rebuilt full and diagnostics-only from that exact combined source. Each profile
passed startup, scene-context, cel-shading, sky-core and real-WGL sky tests. The
argument-free binding test reports its expected private-input skip; explicit private
sky binding and sky runtime invocations separately passed in both profiles. Checked
exact one-time source/resource inclusion in full, complete exclusion in diagnostics,
and matching packaged asset bytes. Connected sky/graphics controls:45 tests passed.

Development DLL identities (not acceptance-package identities):

- Full:498688 bytes, SHA256 `dcc60fdca816049563ad20fc35d1b482b2feacf0394215cf9ed2e518bf39f2dd`.
- Diagnostics:233984 bytes, SHA256 `146756a70087fa10d9a993fcde4c71e72573e9e82a9090a6cbed6b68be2c57f6`.

Exact local verification record: `artifacts/sky/combined-c2f9c99-verification.json`.
Build logs: `artifacts/sky/combined-nf-build.log` and `combined-nd-build.log`.
No combined acceptance ZIP was built or certified because the owner's required
particle/native-transparency gate still fails. No deployment or connected visual
acceptance occurred. Next active todo: owner repairs that gate and supplies a green
exact-source package, then verify sky content/control identity and run the focused
connected acceptance above. Retain this worktree until those checks are complete.

## Shared combination assertions: source 2289bd7 plus focused sky tests

Consumed the integration owner's shared acceptance plan and combined fixture at
`2289bd7b9277bcccd3bbc50821eee2b6dcb1bc36`, preserving this lane's published
verification record through a merge. Extended the existing `CombinedProbe` in
`navigation_draw_test.cpp`; no separate matrix or executable was retained.

The non-timed path now verifies complete depth-buffer equality immediately around
sky and around later feature composition, visible sky only when enabled, native
alpha holes, native depthless alpha blending over sky, preservation of those regions
through all feature combinations, and final UI/minimap-region pixels. These native
submissions are controlled fixtures, not connected foliage/water acceptance. The
shared 16 combinations, three cleanup cycles, allocation limits, and separate
first-frame/warmup/steady timing paths remain in place. No runtime code changed.

Validation: Win32 Release combined-render and navigation-draw tests pass in both
full and diagnostics build configurations (no skips). The diagnostics DLL remains
unchanged; production render functions are linked only into its test executable.
The required full-profile effects-native-transparency test was explicitly run and
still fails the two behind-effect cases; front-effect cases pass. That gate was not
removed, weakened, or bypassed. No package or deployment was attempted.

PR30 is a merged implementation checkpoint. The new fixture delta is published on
`codex/sky-horizon` for the owner to integrate into `codex/native-lifecycle-hardening`;
it is not included by that historical PR. Active todo remains the green
combined package gate, followed by exact package/content verification and the one
coordinated connected acceptance pass under `docs/combined-testing-acceptance.md`.
The provisional duplicate matrix source and build products were removed; existing
`artifacts/sky` development validation material remains local and is not a package.
