# Native power reuse and optional openers — October 1, 2026

## Problem and intended behavior

Installed host 0.3.60/native 1.8.40 completed native NPC death, cleanup and a
strictly later PvE SEEKING frame. The next configured Shot to the Leg submission
entered native code but never produced a positive outbound receipt. The host
correctly polled the same request and cleaned up at its five-second bound. The
user reported a reuse wait message; that report is supporting evidence, not bot
action authority. The original acceptance remains not passed.

Installed host 0.3.61/native 1.8.41 checks native reuse availability before stance
or power mutation. A positively reuse-blocked optional opener may yield to normal
ATTACK on a fresh frame, retaining the exact engagement, owner and target. Global
recovery remains DEFERRED. Unknown data, generic busy states and already-entered
uncertainty never authorize this fallback. Passing the reuse checks does not prove
all native power prerequisites; the normal native entry still makes final checks.
The implementation, package qualification and installation are complete. The new
live recovery gate remains not passed, as recorded below.

## Qualified exact-client boundary

The prepared client is official 1.3.38.13, SHA-256
`0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d`;
the original is
`e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8`.
Addresses below are RVAs and offsets are hexadecimal. Independent review verified
the image and fourteen byte-span hashes retained in private qualification evidence.

- PreparePower at `4E339` compares double client clock `16A2D70` against float
  actor `+67C`. A clock below that value is global recovery.
- At `4E3D9`, native `9A770` tests power-ID membership in actor `+5C8`.
  A null container means no membership. A container references its sentinel;
  each 16-byte node contains next/previous pointers, ID and a predicted deadline.
  The native gate does not use the deadline to grant permission.
- Incoming `ArcRecyclePowerMsg` (table `1156924`, process `38E2D0`) reads
  message `+60` and invokes `9A6A0`, removing every matching power ID. Load/reset
  paths also populate the list. A host timer since the last submission cannot
  reconstruct this membership.
- A listed ID blocks reuse only when the native bypass predicate is false.
  Descriptor `1389560` is `ADMIN_ISADMIN`, table `1141A24`, numeric key `+4`,
  name pointer `+8`, default byte `+10`. Constructor `2B8A80` supplies false.
  Getter `13FAE0` searches the sparse map at actor `+34/+38`, returning the
  matching value's low byte or the fixed default getter `7DFB0`.
- Sparse lookup `86DA0` uses eight-byte key/value slots, empty and tombstone
  markers, and a polynomial probe sequence. Capture must match native lookup
  reachability; finding a misplaced key somewhere in the table cannot establish
  bypass. Duplicate, corrupt, unreadable or changing relevant state is unknown.

The bounded native observer rereads the complete relevant topology and payload,
checks actor/engagement ownership separately, and never mutates the list or forces
a recycle. Global-clock comparisons, actual list lookup, sparse/default bypass,
and recycle removal require exact original/prepared-image conformance probes.

## Host/native contract

Wire geometry remains version 2 (576-byte commands and 384-byte receipts).
Capability `0x40` advertises object power readiness; new configured power openers
require it before obtaining a combat ticket or submitting a combat action. Old services do not gain a hotkey
fallback. Existing STATUS/STOP cleanup remains available across capability loss.

Outcome `POWER_REUSE_BLOCKED = 14` preserves definite NEVER_ENTERED power-action
history without outbound or uncertain bits. Current BOUND ownership requires
CLEANUP_REQUIRED and no closure. Historical STOPPING/BLOCKED remains owned;
CLOSED/NATIVE_STOPPED and RETIRED/SCENE_RETIRED history retains its closure with
zero flags. Only a current, correlated BOUND result maps to policy NOT_READY with
reason POWER_REUSE. Closed or stale history cannot authorize a new action.

The coordinator resolves that action proposal while retaining its exact binding,
Grant and cleanup obligation. The controller skips only the pending configured
optional OPENING ability, recording a separate skipped reason. It must not invent
a queued timestamp, skill-consumption evidence or self-power follow-through
provenance. The next fresh frame still needs normal initiation and target checks
before ATTACK. Manual powers and interrupt actions do not gain automatic fallback.

Entered uncertainty remains one submission plus status polling and bounded native
cleanup. A native refusal after stance or power entry cannot be relabeled as a
safe no-entry skip. A pending skill must not be replaced with another submission.

## Qualification and delivery

Approved [PR #56](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/56)
head `a1557938a695ef4d3a82ed6b67bb19a709975e95` passed all 15 hosted checks and merged
at `88af7953461cc6311c0bcc79b8fb0162013cfd54` on October 1, 19:24:23 UTC.
Included [PR #55](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/55)
was marked merged at 19:24:25 UTC. The completed readiness and initiation receipt
branches were retired after their tips were verified in main. The new receipt
branch is `codex/native-readiness-deployment-20261001`; unfinished owner-liveness
work is isolated on `codex/native-owner-liveness-20261001`, both targeting main.

Host and native independent source reviews found no actionable issue. The actual
two-encounter runner regression covers native death, cleanup, later SEEKING, and
a reuse-blocked second opener followed by ATTACK on the same binding. The direct
native/production differential probe passes 22 cases on each exact client image.
The Windows cross-process test exercises the production command mapping, host
lease, queue and controller ledger with a synthetic action backend. It verifies
reuse-blocked replay/status without re-entry, same-binding ATTACK, denial of new
actions after capability loss, and STOP plus retained closed action history.
This test performs no game effects; native power legality is covered separately.

Exact package source is `29c9728abf6ef13cf90eb7dcba9a73c19d634ce7`, in private
`artifacts/b41/2d632561`. Later receipt-only commits do not change that source stamp.
The independent verifier checked 64 build steps and 90 artifact hashes against the
Git archive, wheel RECORD/source, native version resources and exact client images.

| Qualification | Result |
| --- | --- |
| Complete host suite | 4,383 passed, 788 subtests passed, 36 skipped; Ruff passed |
| Each native profile | 205 passed; all 105 required native gates passed |
| Each profile's real movement/combat IPC | 72 / 86 passed, no skips |
| Readiness probes | 22 cases on each original/prepared image, for both profiles |
| Private acceptance recorder | 90 offline tests and independent source review passed |
| Private deployment helpers | 12 offline tests plus ownership/path/retirement checks passed |

The three native tests requiring private images skip in the generic CTest run and
pass in the separate exact-image steps. The two previously deferred renderer
transparency diagnostics still fail in each profile; their findings remain recorded
and are not readiness or combat gate passes.

| Artifact | SHA-256 |
| --- | --- |
| Package | `1e268aec3c391a442a6243f188cae90adb9047211195de308c62ca3fce82d168` |
| Receipt | `ab7552393f85f19542406430ca1627070310b0cc4d2157e9a21e3f34126d19d4` |
| Full DLL | `311207009781f206dcecc33cb3ee52e820d707c40db2115e03e90465d59108cc` |
| Host wheel | `1a0b6509adc0482be0144053a3baa18a78bda7adb9f13aa6796b7c01a44506c9` |

Installation verified 455 host modules, 9,570 preserved files and exactly one DLL
inventory change. Manager PID 7092 was healthy. Five shortcuts and startup preflight
passed. Launch at 19:29:46.9919521 UTC verified PID 9224, creation FILETIME
`134353565789124161`, HWND `7209758`, and the qualified DLL above. Both clients'
executables and official data remained unchanged. Compact installation and launch
receipts are retained privately under `artifacts/bot-deploy/20261001-b41/receipts`,
with independent `package-verification.json` alongside them.

Retirement verified the .60 host's 2,100 files (47,660,291 bytes) against installed
RECORD/source and scaffold ownership. That host and two exact .40 guest payload
files totaled 50,349,138 bytes removed. Four exact obsolete host/share staging
binaries totaled 5,377,694 bytes, recorded in `obsolete-staging-removal.json`.
Settings, jobs, dependency wheels and failed-run diagnostic evidence remain in
place; no rollback copies were created or retained.

### Live result and remaining work

Run `npc-recovery-readiness-e622dab2634a4d9ca042a7c3dbdc3cdf` is **not passed**.
SELF_POWER request 1 queued for NPC key `(23887,37)` under engagement 1 and Grant
3/scene 1. ATTACK request 2 never entered and had no outbound receipt. Native owner
replacement to generation 4/NONE stopped the host; exact STOP request 3 subsequently
confirmed CLOSED/NATIVE_STOPPED with mode 1, action state 1 and no combat target.
No combat owner or manual-list entry remained. There was no watchdog, helper error,
proposal rejection, second encounter or demonstrated live reuse fallback.

Passive schema-3 `owner-loss-passive-9224.jsonl` retained the actual revocation:
`stalled` reason 8, tick 302842953, interval 297 ms, generation 3 to 4/NONE, scene 1,
keys 0 and gates 247. The user reported no interaction. The native update-gap branch
exceeded the 250 ms movement discontinuity threshold; this evidence does not prove
what caused the delayed client update. The prior `existing_action` diagnostic alone
is not evidence of a new cooldown or initiation failure.

Active next work is a durable owner-liveness correction that distinguishes exact
current leased service work from stale movement while preserving actual lease,
scene, focus, UI and manual-input invalidation. It is not yet completed or installed.
After qualification, fresh identity/readiness and bounded live acceptance remain
required. The revised recorder reports skipped openers separately; this run did
not exercise that fallback. Prior failed runs and the successful first-recovery
assessment remain preserved. Automatic retaliation and server-effect claims remain
outside this gate.
