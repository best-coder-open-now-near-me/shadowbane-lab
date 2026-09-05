# Shared testing and acceptance plan

Scope:
The completed particles/trails, selected-character glow and indicator,
sky/horizon, native WASD/controller/click-drag controls, and runtime-hardening
changes, together with the existing navigation and PvE behavior they affect.

Group-operation coordination and Colab research remain separate design work.
Do not invent acceptance requirements for features we have not implemented
or launch paid compute as part of this client acceptance.


## 1. PIN THE COMPLETE CANDIDATE

The integration owner assembles one exact source revision containing the
completed features and repairs. Freeze that candidate during its test pass;
ongoing development continues in separate worktrees.

Build and verify the actual DLLs, Python wheel, settings panels, assets,
and launcher through the existing package process.

Record the source used to build each artifact. A later documentation-only
commit may record results but must not be misidentified as the build source.
Earlier individual-feature receipts do not certify the combined package.

Use the agreed test runtime. Preserve the known-good installation and a
verified restoration procedure. Do not overwrite unrelated clients.


## 2. FINISH DEVELOPER-OWNED VALIDATION BEFORE OWNER TESTING

Run the applicable existing automated gates against the combined source,
including installed-package checks outside the source checkout.

Exercise the production implementations, not parallel mock implementations.
Required checks must actually execute. Report environmental skips and
unavailable checks explicitly; do not disguise a known failure as an
expected failure or issue a successful package receipt through it.

Obtain one independent review of the combined integration:
shared hooks, scene ordering, context/resource ownership, native movement
execution, manual/automation arbitration, and package/profile membership.

Feature owners fix their own findings; the integration owner reconciles
shared changes. Do not open another general architecture-cleanup project.


## 3. TEST INTERACTIONS AND TRANSITIONS, NOT ONLY HAPPY PATHS

Automate applicable cases using existing infrastructure:

Rendering:
Each visual feature disabled and enabled, relevant combinations, and all
enabled together. Check camera authority, framebuffer/viewport restoration,
depth preservation, foliage cutouts, translucent materials, native water/
effects ordering, UI separation, and resource cleanup.

Movement:
WASD, controller, and click-drag use the same native ownership and stop
contract. Check release, opposing inputs, diagonal behavior, chat/text entry,
inventory dragging, focus loss, device disconnection, and multi-client
isolation. Camera-only input must not cancel navigation.

Automation takeover:
Begin /go or /pve, take manual movement control, then deliver delayed old
commands and cancellations. Old automation must not regain control or
cancel a newer owner's work. Releasing manual input must not unexpectedly
resume the old route.

Lifecycle:
Rapid selection changes, missing targets, identity reuse, scene transitions,
disable/re-enable, panel reconnect, worker failure, and supported graphics
context changes. Check that one subsystem's failure does not unnecessarily
disable unrelated functionality.

Measure combined frame-time cost and resource retention using existing
instrumentation. Separate startup/warm-up from steady operation. Check
repeated transitions for accumulating memory, handles, mappings, or threads.

These are internal engineering checks, not additional owner-facing demos.


## 4. RUN ONE COORDINATED CONNECTED-CLIENT ACCEPTANCE SESSION

Before the session, provide the installed candidate identity, exact controls,
a short route through the checks, and the specific remaining live questions.
Identify any required second client or controller in advance.

Use ordinary gameplay to cover several requirements at once:

- Launch normally and verify that feature-disabled behavior is preserved.
- Traverse representative terrain while rotating the camera. Inspect sky,
  horizon, particles, trails, selection cues, foliage, water, and UI together.
- Change and clear targets, including a moving target and one behind cover.
  Check silhouette coverage and the off-screen indicator's turn direction.
- Exercise all three manual movement methods, release/stop, and camera input.
- Start existing navigation, take manual control, and explicitly restart it.
  Include a suitable PvE encounter when needed to verify the affected handoff.
- Exercise relevant interruption/recovery cases and confirm the intended
  settings remain usable afterward.

Reuse the owner's demonstrated zone-traversal/rune-hunt scenario where useful.
This is regression and new-feature acceptance—not a request to prove basic
navigation from scratch. Do not repeat a long route for every feature.

Capture package identities, relevant diagnostics, and observed failures once.
Do not require the owner to assemble a forensic report afterward.


## 5. CLOSE FAILURES WITHOUT RESTARTING EVERYTHING

For each failure, record expected versus observed behavior, the exact
candidate, a reproduction, and the responsible owner.

After a fix, rebuild and rerun the applicable automated gates. Repeat the
affected live checks and any connected behavior the change could invalidate.
Do not restart unrelated owner acceptance unless its evidence is invalidated.

Never mark an unobserved behavior as passed. Keep separate:
automated validation, owner-observed acceptance, and unresolved limitations.

Finish with one acceptance record identifying the accepted package, enabled
features, remaining limitations, and restoration instructions.

The target is one consolidated first acceptance pass—not a guarantee that
no defect will need a focused retest. Retesting should follow actual findings,
not deliberately incomplete feature deliveries.
