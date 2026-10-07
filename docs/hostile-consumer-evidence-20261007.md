# Current-client hostile consumption: concrete follow-on boundaries

This read-only October 7 audit follows [the response provenance correction](pvp-response-provenance.md).
It identifies a native state-update path and the ownership work needed before it
could authorize a response. Automatic retaliation remains disabled. No hooks,
gameplay settings, deployed binaries or client state changed.

## Exact image evidence

The private verifier checks the complete original and prepared 1.3.38.14 images:

| Image | SHA-256 |
| --- | --- |
| Original | `e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e` |
| Prepared | `78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903` |

All 38 previously recorded receive/session/action ranges and all five defense-route
ranges match on **both** images. Four additional ranges also match each other:
the complete defense handler, its conditional victim-health update, the setter
thunk and the complete setter. This establishes code identity and static control
flow, not executed conformance or hostile-action authority.

Reproduction and the compact receipt remain private under
`artifacts/hostile-consumer-20261007/verify-boundaries.py` and
`boundary-verification.json`. Receipt SHA-256:
`6144b49df8961129cf598ccb531623643b259c579d47ce6f98f8de63ca1ea611`.
The receipt records input manifests, exact byte counts and hashes; no client bytes
or disassembly are published. Historical disassembly remains in
`artifacts/pve-pvp-resume-20260924` and the native-lifecycle worktree's
`artifacts/pve-pvp`. Their older server-contract prerequisite is superseded by
the current provenance document; their concrete buffering counterexamples remain.

## Consumer boundary and its limit

All addresses below are RVAs. Native deferred-action consumption calls
`0x4563e0` from `0x1fab9c`. It resolves participant reference slots, dispatches
action kind `+0x10` through table `0x45681c`, and then updates the actor's current
action link. Kind 21 dispatches through `0x4567c9` and thunk `0x22eb2` to
handler `0x45cd90`. That handler also accepts related defense kinds and remaps
7/8/9 to 20/21/22; those values must not be treated as interchangeable evidence.

The concrete state-update candidate occurs **before** the kind-specific wording:

- The handler takes its victim from action `+0x4c` and rejects a missing victim
  or failed native type-mask test before normal work.
- At `0x45cf33..0x45cfab`, it compares victim current health `+0x5cc` against
  action scalar `+0x18`. Subject to native comparison/type conditions, call
  `0x45cfa7` invokes thunk `0x19105`, then setter `0x9e9f0`.
- The setter writes victim `+0x5cc`, using maximum health `+0x5d0` as its upper
  bound. The routine occupies `0x9e9f0..0x9ea1f`. This is an actual client state
  write, not a string or display observation. It does not necessarily decrease
  health; malformed/nonfinite inputs and no-change paths need explicit treatment.
- The later kind-21 branch at `0x45d8f4` compares the victim with global local
  actor `0x16a2d98`, then formats wording. That comparison is useful attribution
  evidence but the formatting branch itself is not a hostile application gate.
- Handler return value 1 is also used after early rejection at `0x45dd99`.
  Successful return alone therefore cannot mean that the state-update path ran.

A victim health write alone does not identify its attacker or establish why the
health changed. A narrowly qualified health-decrease case could support current
client-applied hostile consumption only when joined to the exact supported
message/action branch and retained participants. It would not cover blocked or
missed attacks that leave health unchanged, nor establish server damage or kill
credit. No raw kind, scalar, return value or nearby actor is sufficient alone.

## Ownership path for the next coherent source slice

Implement one complete provenance path through these boundaries, with typed
unavailable results for unsupported cases. Do not ship a receive-only hook as
retaliation authority.

| Boundary | Concrete site | Required preserved fact |
| --- | --- | --- |
| Network decode and queue handoff | `0x4a192d`, `0x4a19e7` | Owned physical connection incarnation, immutable receive ID, successful full decode and queue publication |
| Targeted message processing | `0x3ae020`, dispatch calls `0x522069` / `0x522159` | Original actor/victim keys at message `+0x80/+0x88`; same ticket through retries |
| Action construction | `0x455ea0`; message sites `0x3ae16a`, `0x3ae28f`, `0x3ae306`, `0x3ae3d0`, `0x3ae4bd` | Independent action token scoped to that exact processing attempt and original message ticket |
| Queue transfer and consumption | `0x1fa460`, `0x1fa6b0`, `0x1fab9c` | The same owned action, original participants and valid local scene through consumption |
| Supported state-update branch | `0x45cd90`, conditional call `0x45cfa7` | Actual branch execution, exact retained current local victim, supported original attacker and pre/post native state |
| Retirement | Message `0x3adf60`; action `0x455f80`; scene/connection retirement | Invalidate tokens before reuse; never adopt a later object with the same address/key |

The five construction sites do not all imply the same behavior. The direct path
at `0x3ae1a1` invokes formatter `0x456f90` and bypasses normal consumption. The
missing-attacker fallback at `0x3ae454` substitutes the victim key; it cannot
identify an attacker. Both must remain unavailable. Action `+0x48` is a raw link,
not a destructor-owned reference; only an independently live, qualified action
ticket can supply parent lineage. Derived constructors require separate exact
qualification before inclusion; globally adopting every constructor would admit
unrelated local producers.

Use existing retained actor/world lifetime evidence on the owner thread. Network
callbacks must not create or rearm that lifetime. Publish copied identities and
proof state through one native provenance owner; the host should not reconstruct
authority by joining diagnostic rows on keys or timestamps. Any eventual response
still needs current exact target/party admission through the shared actor owner.

## Remaining evidence and next todo

The bounded next qualification work is an exact-image fixture for the selected
consumer branch and its complete connection/message/action lifetime path:

1. Prove the supported constructor-to-handler field mapping and actual branch
   execution, including a finite victim-health decrease, no-change/early-return,
   missing-attacker fallback and formatter-only negatives. Instrumented fixture
   dependencies must be named; a mocked handler cannot establish its semantics.
2. Qualify physical stream construction/close and full-decoder ownership. The
   known teardown `0x7f4ce0` closes receiver socket `+0x3c`; this does not yet prove
   every retirement/replacement path. Reject unobserved or crossed lifetimes.
3. Exercise queue retry, destruction without consumption, reentrant construction,
   raw linked-action reuse, duplicate consumption, actor replacement, and ring/token
   exhaustion. No transition or lost observation may relabel an old ticket.
4. Join the positive native state-update fact to original retained participants
   through that path. Only then assess whether the chosen branch supplies the
   required current-client hostility semantics. Do not demand absolute server
   generation time unless a stronger product claim actually requires it.

This is sufficient to start concrete offline implementation qualification without
requesting server source or another generic fight trace. It is not yet sufficient
to enable automatic response insertion. This document is delivered on
`codex/hostile-consumer-evidence-20261007` in PR #84, targeting `main`. It includes
merged PR #83 (`ae7f72d`) and the prior provenance correction. Deployment and
sustained buff validation remain separate work.
