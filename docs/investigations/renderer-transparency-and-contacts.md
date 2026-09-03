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

Material-ownership checkpoint `154c13a` is committed and pushed. Validation:
1,426 Python tests passed, 7 privilege-dependent skips, 211 subtests; Ruff passed;
12/12 native tests passed for both profiles. Live coverage and cost remain unmeasured.

### Truthful accent controls

The panel labels interior accents as black and fixed at one pixel and exposes
their on/off switch, not the ineffective width slider. The rim-tint explanation
distinguishes the depth pass from interior accents. Existing preset and live ABI
versions remain supported. On panel load, legacy width values below one become
an unchecked accent switch; all other widths become one pixel. This preserves
effective appearance without rewriting preset files or automatically applying
settings to a valid client. Re-enabling accents then works through the switch.

Independent accent color and variable width are deferred, not claimed delivered.
Color needs a separately validated alpha-preserving path, not simply removal of
the existing black logic operation. The current release keeps that path intact
so the transparency regression test does not also introduce new color behavior.

### Pre-release import audit

The exact frozen 55fb client has 96 OpenGL imports and does **not** directly
import glPopAttrib. The initial checkpoint incorrectly made that new hook
mandatory; pre-release validation caught this before a VM deployment. It is now
optional, with separate storage for the renderer's required restore helper and
the optional client's original function. Native tests cover absent optional
imports, mismatched present targets, and helper-only rollback. A hash-attributed
import-table fixture prevents adding mandatory hooks this reviewed client lacks.
The audit also added guards for its material, texture-generation, depth, and
other imported source-state setters. Texture-upload hooks remain telemetry-owned.

This narrows the original causal claim: attribute restoration is a general
cache-coherence hazard, but direct client glPopAttrib use is not evidenced on
this build. Display-list execution and actual object/pass attribution remain
the relevant live checks. Optional import hooks do not claim to intercept
dynamically resolved functions or reconstruct arbitrary display-list programs.

### Release 1.6.11 identities

- Full-renderer DLL: `219f9eb64b87f09bfcd2985f58dd9cb0adaf7ea7ed74ee46fc4052acccfa2a97`.
- Diagnostics-only DLL: `77a6383c3aa20219651ccf720aa2015b4bf01a61540783b5cf82b9472e03f0e2`.
- Patched executable stays `a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8`.
- The reviewed restrained-cel texture overlay is unchanged.

The host can validate bootstrap authoring but cannot complete this frozen client's
package dry-run: its baseline manifest is bound to the guest UNC path. The path
identity check rejected the host-local alias; no manifest was rewritten to bypass
it. Guest publication must run its normal dry-run before creating a new isolated
runtime. Neither the running client nor the plain VM has been changed.

Final host validation: 1,437 Python tests passed, 7 privilege-dependent skips,
211 subtests; Ruff passed; all changed PowerShell scripts parsed; full and
diagnostics-only Win32 Release builds and 12/12 CTest tests per profile passed.
Bootstrap authoring retains the expected patched executable identity. These
checks include package-boundary tests, not a claim of guest publication or visual
acceptance.

## Acceptance queue

1. COMPLETE: state-coherence tests and both native profiles; checkpoint pushed.
2. COMPLETE: source-owned transparency/feature replay policy and truthful accent controls.
3. COMPLETE: host Python/native/package-boundary/source checks; version 1.6.11.
4. ACTIVE: guest publication/dry-run and testing-VM-only retest after explicit
   keyboard/mouse handoff. Preserve current
   settings, capture exact process identity, pass toggles and per-frame evidence,
   and restore settings afterward. User controls login, movement and the camera.
5. Inspect the affected transparent object and foot-contact response separately.
   Compare against normal settings without replacing global edge thresholds.

The plain VM remains untouched. No performance improvement or live visual fix is
claimed before the corresponding capture. Keep source checkpoints, VM release
identity, observed results, and remaining work distinct in every update.
