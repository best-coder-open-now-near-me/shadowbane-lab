# Native service ownership across delayed updates - October 1, 2026

## Observed failure

Installed host 0.3.61/native 1.8.41 queued Shot to the Leg, then lost the native
movement Grant before ATTACK entered. The original bounded acceptance remains
not passed. Passive schema-3 telemetry retained the exact cause: generation 3 to
4/NONE, reason `stalled`, a 297 ms owning-update interval, key bits zero and
valid foreground/native/scene gates. The user reported no interaction. This
identifies the policy that revoked ownership, not what delayed the client frame.
See the [installed readiness receipt](native-power-readiness-20261001.md).

## Ownership boundary

Candidate host 0.3.62/native 1.8.42 distinguishes a delayed client frame from a
lost producer. A service-only native obligation may keep its exact Grant across
a delayed update only with fresh proof of the original pinned native service,
current producer lease, owner thread and native lifetime. The permissive cleanup
admission predicate is not sufficient proof.

Active navigation and unknown owners retain the existing 250 ms discontinuity
policy. A failed stop preserves whether its obligation was service-only before
movement/activity flags were cleared; a stale route cannot acquire that status.
Pending cleanup grants no movement or new native action. Clock regression, lease
loss, scene replacement, focus/UI loss and player takeover remain cancellation
boundaries. Delayed frames integrate zero camera time. Nothing reacquires the
Grant, replays a skill, changes hotkeys or uses system-message text.

## Delivery and remaining work

The focused branch is `codex/native-owner-liveness-20261001`, targeting main.
It includes the full receipt tip `22c0baf` from
[draft PR #57](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/57).
Main remains `88af795`; the installed .61/.41 runtime is unchanged.

Initial qualification passed 40 native controls/runtime tests, all eight actual
Windows movement-session IPC tests, 263 package-gate tests and Ruff. Production
DLL compilation passed. The new mandatory cross-process case exercises 297 ms
updates with live producer heartbeats during active service and pending cleanup;
missing/skipped/failed/duplicate execution is rejected by the package gate.

Independent review found and corrected a pending-cleanup takeover case. Pending
automation still observes configured keyboard, controller/cancel and drag intent
through the common input interpretation. Qualified player intent revokes the bot
while preserving its original unresolved cleanup; it issues no camera or movement
write and does not resume held input after cleanup. New regressions cover ordinary
and delayed updates, remapping/modifiers, opposing keys and camera-only input.
Production input sampling is covered as well: pending cleanup does not hide
physical keys, and captured world drags retain focus/UI/capture/threshold guards.
Revoking automation from input intent requires neither a camera basis nor a
terrain pick; those remain prerequisites for actual native movement.

Independent source review is complete. Active: complete exact-source package
qualification for both native profiles. The combined review is
[draft PR #58](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/58).
Merge and installation require approval after qualification; earlier approval
covered PR #56. Fresh identity/readiness and bounded live acceptance follow an
approved installation. Automatic retaliation remains disabled.
