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

Independent reviews passed. The production input regressions cover ordinary and
delayed updates, physical keyboard and captured world drag, configured remapping,
modifiers, opposing keys, camera-only input and neutral rearming. Native intent
recognition can revoke pending automation without admitting camera or movement
writes or requiring the basis/terrain queries that pending cleanup blocks.

Exact package source is `7f37ff53e181288ce1ae695f2e2699ecf2bb8ff2`, in private
`artifacts/b42/d87717cd`. Later documentation commits do not change that stamp.
The earlier `c85a17d` qualification was stopped after review added mandatory native
owner-service and mouse gates; its partial logs remain, and it was not qualified.

| Qualification | Result |
| --- | --- |
| Complete host suite | 4,397 passed, 788 subtests passed, 37 skipped; Ruff passed |
| Each native profile | 205 passed; all 107 required native gates passed |
| Each profile's real movement/combat IPC | 73 / 86 passed, no skips |
| Power-readiness image probes | 22 cases on each original/prepared image in each profile |
| Package verification | 64 steps and 90 indexed artifacts verified against Git archive, ZIP and wheel |
| Private acceptance/deployment helpers | 90 / 12 offline tests passed; PowerShell/path checks passed |

The three native private-image cases skip in the generic suite and pass through
separate exact-image steps. Both previously deferred renderer transparency
findings remain recorded per profile; they are not combat gate passes.

| Artifact | SHA-256 |
| --- | --- |
| Package | `ee9d05db8475637512499918e10755d294815ff41e3153d27fe2bbb102086e4c` |
| Receipt | `0bc6084f3913c30f39bdb4cb7c21ebc1a9abb5eebac5fc097e5f87877a02a6aa` |
| Full DLL | `4a7fce6cd64cd3619fc937d30eee1291052e5f0f9f8054eee39c43f7b4d40dd2` |
| Host wheel | `d17461b1c232a252e9cba95618263194bdb3875b17b7925606da2e763320ff22` |

The combined [draft PR #58](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/58)
includes all of PR #57. Active: merge/install approval after hosted checks pass,
then closed-client installation and fresh identity/readiness before bounded live
acceptance. Earlier approval covered PR #56. The installed .61/.41 remains
unchanged. Automatic retaliation remains disabled.

Parallel automatic buff preparation is isolated on
`codex/native-buff-preparation-20261001`, based on this source tip. Its native
actor/effect/item authority is under qualification; no automatic buff action or
new runtime deployment has been performed by that lane.
