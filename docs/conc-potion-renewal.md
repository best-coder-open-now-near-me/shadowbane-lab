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

Source branch: `codex/conc-potion-early-renewal-20261009`, targeting `main`.
Runtime versions: host `0.3.88`, native `1.8.58`.
The prior installed `.87/.57` release remains active while the combined source,
package and installation are qualified. Package results and live renewal evidence
will be recorded at delivery; this document does not claim live acceptance.

Follow the [deployment policy](deployment-policy.md). Preserve user settings and
journals in place and retain compact source/hash receipts, not rollback runtimes.
