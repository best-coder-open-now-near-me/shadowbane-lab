# Automatic response authority: client evidence and remaining gaps

## Current qualification scope - October 7, 2026

Server source or protocol documentation is one possible source of evidence, not a
prerequisite for continuing client-side qualification. The September findings
below establish real buffering and attribution gaps, but their request for a
server-session contract was broader than the minimum retaliation requirement.
Automatic response insertion remains disabled; this correction changes no code,
admission rule, runtime setting or gameplay authorization.

The intended evidence is a hostile action that the native client positively
consumes for the exact retained current local victim, attributed to its original
attacker. If that boundary is qualified, uninterrupted connection, message/action
lineage and actor lifetime can establish a current client-applied hostile action
without proving its absolute server generation time. This is not a claim of
server damage, a unique server transaction or a newly generated network packet.
Whether an inspected handler actually supplies this positive hostile-consumption
meaning must be demonstrated; a formatter, animation, process return or object
lookup alone does not supply it.

The existing `targeted_action_trace.cpp` observes original keys at deserialize
return, before receive-queue publication. Its socket type/retirement checks and
decode-spanning `NativeScene` label do not track a connection incarnation or carry
receive identity through retries and deferred actions. The retained local actor
watch detects object/world replacement; it does not date buffered network bytes.
The separate item/power diagnostic lineage is not targeted-action provenance.

The concrete client-only qualification path is:

1. Qualify physical connection construction/retirement and the full receive
   decoder/queue handoff. Give each owned incarnation and received message an
   immutable identity; exclude replay and local producers. Receiver/writer
   wrappers, socket addresses and operating-system handles can be reused.
2. Carry original participant keys and receive identity through process retries,
   deferred-action construction, consumption and disposal. A message ticket must
   not become a pointer-only action ticket; constructor failure, redecode,
   destruction, overflow or a missed transition cannot restore old authority.
3. Identify a specific native hostile-consumption branch. Resolve original victim
   and attacker keys through the native registry while their lifetimes are held;
   the victim must be the exact current local actor. Reject missing-actor fallback,
   synthetic/local producers and unsupported action kinds. Recheck scene and
   retained participants across consumption, then revalidate the proposed attacker
   against current party and target-admission rules before any response.
4. Qualify entry/transfer transitions sufficiently to prevent an old message or
   action ticket from being rebound to a new actor/scene. Unknown crossings remain
   unavailable. A server token or documented ordering contract is needed only if
   the chosen client boundary cannot establish the required current-consumption
   semantics, or if a stronger server-generation claim is required. An active
   socket, first PlayerData or outgoing ReadyToEnter is not a substitute.

Exact-image control-flow and lifetime fixtures can close these gaps offline;
focused observation may then validate a specific unresolved branch. Repeated
generic fight traces cannot prove missing ownership or absence of stale events.
The next source task is hostile-consumption and receive/action lineage
qualification, with explicit rejection of transition/reuse counterexamples.

This documentation correction was reviewed in PR #82 on
`codex/retaliation-client-provenance-20261007`. Its tip `d996c8a` is incorporated
by ancestry into deployment closeout PR #83 for one combined documentation
merge. It does not change the installed .75/.52 runtime or qualify a receiver.

## Historical finding - September 28, 2026

Automatic attack-list insertion remains disabled. Existing native captures prove
actor/victim keys and portions of local lifecycle, but cannot prove that a delayed
server event belongs to the currently controlled character session. This does not
block the independent manually saved attack-list transaction.

The retained September 24 investigation was rechecked against prepared client
1.3.38.11, SHA-256
`7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f`.
All 38 reviewed code-range fingerprints matched. This is static exact-image
evidence, not a new live experiment, server guarantee or current-client release.

## Qualified local ownership

The network owner decodes at RVA `0x4a192d` and publishes to its receive FIFO at
`0x4a19e7`. The process calls at `0x522069` / `0x522159` can requeue the same
referenced message after a nonzero return. Neither a new process attempt nor a
zero return proves a newly applied attack. Message destruction/release are separate
lifetime boundaries; a reused address must never inherit an earlier receive ID.

Targeted-message processing can construct deferred actions (`0x455ea0`), transfer
them to queues (`0x1fa460` / `0x1fa6b0`), consume them through `0x4563e0` and destroy
them through `0x455f80`. The action's `+0x48` link is raw, not a destructor-owned
reference. Missing-actor paths destroy without consuming; a direct path invokes
formatter `0x456f90` without normal consumption. Neither formatting nor destruction
is attack authority. Derived-action constructors and their parent/disposal scopes
still need exact qualification if they become part of an authoritative consumer.

The client has buffered reads beneath the decoder. A recent decoder/capture time,
active socket, fresh reader cursor or outer recorder reset cannot establish when
the bytes entered the server's character-session ordering. TCP/FIFO ordering alone
does not establish that an old-character producer was detached at the transition.

## What the session messages prove

NewWorld invalidates the old local actor. PlayerData owns a decoded player object
and publishes that exact object before sending ReadyToEnter. ReadyToEnter is an
outgoing publication notification; its enqueue does not prove that the server
consumed it or fenced earlier attack producers. No reviewed per-event character
session identifier or mandatory physical connection replacement was established.

A future receiver must retain original receive identity through queue retries,
message/action lineage and destruction, then join successful exact player
publication to the existing movement-watch epoch on the owner thread. Network
threads must never create or rearm that watch. Gaps, missed markers, overflow,
constructor failures, reconnects and callback replacement must invalidate authority.
These local checks are necessary but do not supply the missing server fact.

## Optional evidence for the stronger server-session claim

Server actor-switch and NewWorld/PlayerData send/serialization code, or an
authoritative contract, could prove that old-character targeted-action producers
are detached or drained before new PlayerData is serialized, and that subsequent
events belong to the newly admitted character. An independently verified per-event
session token or mandatory physical reconnect across every supported character
switch could instead establish the boundary.

A passive login/fight trace cannot prove the absence of late old-session events.
Do not request broad repeated gameplay observations as a substitute. Do not infer
hostility from combat chat, proximity, current selection or an ambiguous name.
Keep response insertion disabled until the chosen current-consumption and
attribution contract is qualified. Server documentation is not the only route to
that contract. Continue manual-list work independently.

## Reproducing the offline verification

Keep the image and disassembly private. Whole-file SHA-256 must match the image
above. Convert each reviewed RVA through the PE section table to its raw file offset
and hash exactly the manifest's byte count. The 38 ranges comprise:

- 11 ranges in private `artifacts/pve-pvp-resume-20260924/evidence-manifest.json`;
- 15 in that directory's `session-evidence-manifest.json`;
- 7 in tracked `evidence/pvp/wonderbane-targeted-action-static-20260912.summary.json`;
- 5 in the native-lifecycle worktree's private
  `artifacts/pve-pvp/targeted-action-requeue-summary.json`.

The private reviewed image is retained at
`artifacts/guard-deploy/client-update-20260924/review-prepared-sb.exe`.
The retained `qualification.md` and `session-barrier.md` explain the exact ranges
and their limits. This document publishes conclusions and compact identities only;
it does not export the client, disassembly or private captures.
