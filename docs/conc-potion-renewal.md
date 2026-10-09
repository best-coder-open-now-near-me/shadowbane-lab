# Concoction renewal before expiry

Greater Concoction Potion now becomes eligible for automatic renewal when its
native coverage has 15 seconds remaining. This allows the approximately ten-second
application to finish with five seconds of margin. It applies to the reviewed
item template `(980066, 0)` with coverage power `429021400`; other buffs keep their
existing missing-coverage policy. Existing saved buff settings need no migration.

## Native evidence and ownership

The copied effect records supply the deadline at `+0x60` against the native clock
at image RVA `0x16a2d70`, for timed classes 0 and 2. The reviewed client `.16`
remaining-time getter at RVA `0x14edc0` matches the previously qualified 96-byte
span, SHA-256
`e9fc3fcab08b854d2cb809a21f6aa0d8fe67b1ad47131b885e1c3e8c8e63a76e`.
The implementation reads the bounded, owner-bound effect snapshot already used
for coverage. It does not derive duration from system messages or first observation.

For repeated records of one descriptor, the longest positively timed coverage
wins. For a power requiring several descriptors, the earliest of their deadlines
determines renewal. Unknown or untimed coverage does not fabricate a countdown.
Elapsed time never changes PRESENT into MISSING; native effect presence still
owns coverage. An elapsed but retained timed record can request renewal without
claiming that the record has disappeared.

The actor publication uses version 3 and publishes optional finite remaining
milliseconds and the positive deadline's exact binary representation. The host
and native admission both require the exact potion and the 15-second threshold.
The sampled countdown may decrease without invalidating an in-flight request;
crossing the renewal threshold or changing the deadline advances the publication
and admission revision. Freshness checks still apply to each capture.
Other covered, partial or unknown alternatives prevent a proactive replacement;
ordinary ready alternatives remain usable when the whole group is missing.

A covered renewal reserves each required descriptor's old deadline in the native
application journal. Continuing old coverage cannot confirm the new application:
every matching descriptor must advance beyond its own deadline. The original
submission and this obligation survive host reconstruction. Native interruption evidence can resolve
the exact interrupted submission. Host policy also excludes early renewals from
its legacy presence-only reconciliation, so an old effect cannot cause repeated
potion consumption while the new application is pending.

Timing is only a scheduling hint. Item availability, stationary entry, player
takeover, local action settlement and shared combat ownership retain their normal
meaning. Starting 15 seconds early supplies margin; movement, missing inventory
or other genuine inability to apply can still produce a gap.

## Delivery

PR #136 merged normally at `d35bab594e0e903aac1b9f51872ec3e6ef3d0ee8` after
all 15 hosted checks passed at feature head
`7760803f11cd57c272f84ce5bf1b6ecb73763931` on
`codex/conc-potion-early-renewal-20261009`.

The exact qualified release is `00e6ae75a95f63d723f78db49097d716d1425f31`
on `codex/conc-potion-release-20261009`, with host `0.3.88`, native `1.8.58`
and the installed graphics composition. Qualification passed 5,901 host tests
(41 skips), both native profiles, and 74 movement / 86 combat / 233 actor IPC
cases per profile. Six installed desktop cases and the actual worker handshake
also passed. Independent verification checked 136 artifacts, 108 stages and
484 modules. The builder receipt is
`eb0da0bd9bb90f646a2a032028cd6c3e24fcebefc1c71a657e2ca876fc5e1184`;
private captures and binaries remain outside the repository.

Interrupted host preparation has been repaired and the new `.88` environment
passed its installed validator for all 484 modules. The preparation receipt is
`5f3e1a1deaabeb84b11cc1e7e52b46961e06a0e60d0ee77d38b5d2ca17d981dc`.
The exact old manager and worker have since exited through the reviewed stop
phase. Native quiescence was verified and no independent old-host dependency
remains. The manager-stopped receipt is
`636e7a497e16a181783d8d4c563418ed9a63042cfc205cb3cc5517617dce48d5`,
with completion `reviewed_phase_completed`.

The game remains open with the prior `.57` DLL. Bot upkeep is stopped while the
user closes that client; runtime replacement and live acceptance remain pending.
Next: install and verify activation after client closure, then resume and observe
the native covered-renewal submission and each required descriptor's deadline
advancement. Successful qualification does not itself demonstrate live renewal
continuity.

Follow the [deployment policy](deployment-policy.md). Preserve user settings and
journals in place and retain compact source/hash receipts, not rollback runtimes.
