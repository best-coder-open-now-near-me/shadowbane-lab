# Sky and horizon integration

Feature branch: `codex/sky-horizon`, worktree `.worktrees/sky-horizon`.
User-pinned start: `0c807ee774859cc3f17f9ebc04d3f0a900bd0428`.
Consumed shared owner dependencies through `8961fad07ff00c40b511f5b8f9562669069aad39`.
PR destination: `codex/native-lifecycle-hardening`, then owner-reviewed integration
into `main`. No shared client/VM replacement, main merge or deployment is authorized.
This is an unfinished source checkpoint, not an acceptance package.

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
Shared edits are identified in cel_shading, CMake, scene_draw contract and existing
context-change callback; integration owner reconciles them.

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
- [ ] Active: shared context extraction, package identity and both-profile validation.
- [ ] Feature PR and owner's combined source/package verification.
- [ ] Focused connected acceptance: appearance, translation/rotation, horizon/fog,
      foliage/water, UI/minimap, toggles/context transitions and performance.
