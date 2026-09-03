# Transparency, contact lines, and accent controls

## Scope correction: 2026-09-03

The user confirms the outer outlines around the body are present. Do not carry
the earlier missing-body-silhouette observation forward as a current failure.
Remaining concerns are lines crossing transparent parts, the under-foot contact
line, and interior-accent controls that do not behave as their labels suggest.

Source baseline: `codex/client-convergence-v2@920ba0f`, extension 1.6.10.
Saved evidence: `outline-ab-20260903T081150511480Z` under the testing VM's
`diagnostics/guided-session-20260903` directory. The original capture finished
world drawing at ordinal 317, composited at boundary 318, and reported no late
world draws. This scene does not reproduce the old premature-composite bug.
The saved comparison predates the user's red-rim setting. Its all-live-effects-off
reference still uses the patched texture package, not a pristine client.

## Confirmed code findings

- The fixed-function mirror introduced by `ce90ad6` is not updated by OpenGL's
  internal display-list execution or attribute restoration. Compiled commands
  bypass the executable's imported setter hooks. `GL_COMPILE_AND_EXECUTE` can
  also change real state while renderer draw instrumentation is dormant.
- A mirror is context-owned, not merely thread-owned. A context switch on the
  same thread must invalidate an otherwise valid snapshot.
- Fixes `004a4c8` and `07d9b73` remain included: cutout preservation and UV-safe
  array feature edges were not lost. However, stale alpha-test state can select
  the unclipped path. This is a code-level defect, not yet attribution of the
  user's particular transparent object.
- Interior feature edges currently disable blending and use black color logic.
  Alpha cutouts and genuinely alpha-blended materials need separate policies.
- The interior width control accepts 0.5–3.0, but the implementation suppresses
  values below 1 and clamps everything else to exactly one pixel. There is no
  independent feature color. The dark-scene rim tint belongs to the adaptive
  depth composite and does not recolor bright-surface ink or interior features.
- The outer pass uses inverse-depth curvature, not only depth discontinuities.
  Weak response where feet meet terrain is plausible, but not yet confirmed by
  an affected-scene response capture. Do not broaden this into missing body
  depth or claim normal/class buffers are proven necessary by that observation.

## Implementation checkpoints

### State coherence

Invalidate after client attribute restoration, display-list playback and list
completion. Adopt a fresh snapshot at the next legal draw observation, and bind
that snapshot to its OpenGL context. Do not query state inside glBegin/glEnd or
while recording a display list. Regression tests exercise the actual private hook
adapters against a fake OpenGL backend without injecting into a game process.

The ordinary-frame refresh budget remains one. Additional refreshes require a
counted valid-to-invalid state boundary in the same frame. Native publication
and the diagnostics consumer use this allowance; valid restores no longer wake
the status writer every frame, and unaccounted per-draw refreshes still fail.
Older captures without this policy keep their original one-refresh limit.

This checkpoint repairs subsequent observations. It is not sufficient to replay
features for a list that changes and restores state around individual geometry:
that needs a source-state ownership policy, not a post-list snapshot guess.
No test package is released from this checkpoint alone.

State-coherence checkpoint `52f6606` is committed and pushed. Validation:
1,421 Python tests passed, 7 local privilege-dependent skips, 211 subtests;
Ruff passed; 12/12 native tests passed for full and diagnostics-only profiles.

### Material ownership

Feature replay now requires a captured list with stable source state belonging
to the current OpenGL context. Recorded texture/alpha/color/transform commands,
nested list calls, unsupported captured vertex submissions, and array submissions
inside lists invalidate that proof. The original draw remains intact; opaque
interior ink and the inherited-lighting wrapper are not applied to mixed-state
lists. This deliberately trades unsupported accent coverage for correct material
ownership; it is not a claim that all display-list materials are reconstructed.
The exact pre-UI depth composite is unchanged.

Opaque interior accents no longer force their way onto blended materials,
including depth-writing translucent draws. Cutout edges require unambiguous
endpoint UVs; a shared geometric edge with conflicting face UVs is not replayed
using one face's coverage. Neutral known lists avoid unnecessary state refreshes.

Four additive per-frame counters report accent draws, skipped blended draws,
skipped unowned-source draws, and skipped missing/ambiguous-UV segments. The
diagnostics consumer validates these as a complete group when present, while
continuing to read older captures. These counts support pass attribution; they
are not semantic actor/material IDs and do not establish the observed object's
cause before the next live capture.

## Acceptance queue

1. COMPLETE: state-coherence tests and both native profiles; checkpoint pushed.
2. ACTIVE: source-owned transparency/feature replay policy and truthful accent controls.
3. Complete Python, native, package and source checks; distinct versioned release.
4. Testing-VM-only retest after explicit keyboard/mouse handoff. Preserve current
   settings, capture exact process identity, pass toggles and per-frame evidence,
   and restore settings afterward. User controls login, movement and the camera.
5. Inspect the affected transparent object and foot-contact response separately.
   Compare against normal settings without replacing global edge thresholds.

The plain VM remains untouched. No performance improvement or live visual fix is
claimed before the corresponding capture. Keep source checkpoints, VM release
identity, observed results, and remaining work distinct in every update.
