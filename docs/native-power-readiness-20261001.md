# Native power reuse and optional openers — October 1, 2026

## Problem and intended behavior

Installed host 0.3.60/native 1.8.40 completed native NPC death, cleanup and a
strictly later PvE SEEKING frame. The next configured Shot to the Leg submission
entered native code but never produced a positive outbound receipt. The host
correctly polled the same request and cleaned up at its five-second bound. The
user reported a reuse wait message; that report is supporting evidence, not bot
action authority. The original acceptance remains not passed.

Candidate host 0.3.61/native 1.8.41 checks native reuse availability before stance
or power mutation. A positively reuse-blocked optional opener may yield to normal
ATTACK on a fresh frame, retaining the exact engagement, owner and target. Global
recovery remains DEFERRED. Unknown data, generic busy states and already-entered
uncertainty never authorize this fallback. Passing the reuse checks does not prove
all native power prerequisites; the normal native entry still makes final checks.
The implementation is complete and undergoing qualification; it is not installed.

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

Active branch `codex/native-power-readiness-20261001` includes receipt tip
`37e0e1e` from [draft PR #55](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/55).
The combined integration review is
[draft PR #56](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/56),
which targets main. Installed source `f0263c3` remains unchanged.

Host and native independent source reviews found no actionable issue. The actual
two-encounter runner regression covers native death, cleanup, later SEEKING, and
a reuse-blocked second opener followed by ATTACK on the same binding. The direct
native/production differential probe passes 22 cases on each exact client image.

Active: qualify the combined committed source and package. Pending: full
host checks, both native profiles, cross-process wire/history tests, required
original/prepared readiness probes, exact-source packaging, and separate merge
and installation approval. The acceptance recorder must report a skipped opener
as skipped, rather than claiming that two skills queued. Prior failed runs and
the separate successful first-recovery assessment remain preserved.
