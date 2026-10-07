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

### Executed constructor and health-prefix fixture

`native/wonderbane_extension/hostile_health_consumer_probe.cpp` now executes a
bounded subset of the exact original and prepared .14 images. It is a separate
`EXCLUDE_FROM_ALL` executable, never linked into the extension. Build target
`wonderbane_extension_hostile_health_consumer_probe` with the existing Win32
MSVC configuration, then pass one of the two hash-qualified image paths. No game
process, socket, input, runtime hook or application setting is used. Unknown
images are rejected before any native bytes become executable.

The fixture runs 20 cases per image. Complete image hashes and explicit spans
protect the copied code. It executes both argument-transfer blocks ending at
`0x3ae28f` and `0x3ae306`, the full constructor `0x455ea0..0x455f48`, native key
copy/inequality routines, the defense prefix `0x45cd90..0x45cfab`, and complete
health setter `0x9e9f0..0x9ea1f`. The prefix ends at `0x45cfac` and uses the
original early-return epilogue. Everything after that boundary is excluded.

The executed mapping is:

| Message field | Action field | Transfer |
| --- | --- | --- |
| `+0x80` / `+0x88` | key `+0x08` / key `+0x28` | Original attacker/victim key values, without proving current objects |
| Primary `+0x90`, secondary `+0xa0` | kind `+0x10` | Secondary kind 8 is remapped to 21 by the defense prefix |
| Primary `+0x94`, secondary `+0xa4` | scalar `+0x14` | Subsequently overwritten by the prefix's notification kind |
| Primary `+0x98`, secondary `+0xa8` | health scalar `+0x18` | Constructor argument eight; consumed as floating-point bits |
| Primary `+0x9c`, secondary `+0xac` | scalar `+0x1c` | Copied independently of health |

The constructor initializes participant reference slots `+0x38/+0x4c` to null.
The fixture supplies the victim separately; constructor keys alone do not prove
retained participant identity. The native prefix reads the health scalar and
uses an approximately 0.001 comparison tolerance. Cases cover a finite decrease,
unchanged health, a sub-tolerance difference, an increase and maximum clamp,
negative values under both type predicates, zero, NaN and both infinities.
Notably, a NaN new scalar does not reach the setter in these cases; positive
infinity clamps to maximum, while negative infinity can be written for the
non-special type. These are native observations, not acceptable hostile-event
inputs: eventual evidence must require finite, meaningful pre/post state.

Kind 7 also reaches the same health write (remapped to 20). Thus a setter call
or decrease does not by itself prove kind 21 or hostility. Null victim and failed
type test return 1 without a write. The original missing-attacker substitution
slice `0x3ae454..0x3ae45c` substitutes the victim key when the attacker is missing;
that result cannot attribute hostility. The formatter-only call-site slice
`0x3ae189..0x3ae1a5` invokes the instrumented formatter and never the qualified
health-prefix entry. The fixture does **not** execute or characterize the full
formatter implementation.

Every replaced or excluded dependency is explicit:

| Dependency | Fixture treatment and limit |
| --- | --- |
| Type query thunk `0x5e61` | Instrumented masks `0x2000`, `0x10`, `0x10000`; validates victim subobject address but does not qualify real RTTI/type semantics. `0x10` is false, excluding equipment branches. |
| Reference retain `0xb2b7`, copy `0x25a8b`, virtual release | Instrumented exact-pointer callbacks; native release clears the local slot before callback. This proves call ABI/ordering, not reference ownership or destruction safety. |
| Notification `0x27395` | Instrumented argument/count capture, with no UI effects. Local-attacker notification `0x19e66` is skipped by a fixture global; it is not qualified. |
| Setter thunk `0x19105` | Instrumented call count forwards to the complete original setter; no mocked health computation. |
| Participant bind thunks `0x79f0`, `0x1ca4e`; formatter `0x21995` | Instrumented only for the formatter-route negative. No participant retention or full formatter semantics are claimed. |
| Allocator, registry lookup, temporary-key creation and queue | Not executed. The transfer wrappers supply private frames/objects and check copied fields. |
| Exception handlers | Replaced; any fault terminates the probe as a failure. Only normal execution and stack balance are qualified, not native SEH recovery. |
| Post-health handler tail, action/message destruction and consumer dispatcher | Not executed. The fixture cannot establish full action consumption, retirement, supported dispatch admission or live response authority. |

Compact execution receipts and source/executable hashes remain private under
`artifacts/hostile-consumer-20261007`; no image bytes are committed. This closes
the selected field-transfer/conditional-write question only. The connection,
message, queue and retained participant lifetime work below remains necessary.

The bounded next qualification work is an exact-image fixture for the selected
consumer branch and its complete connection/message/action lifetime path:

1. The bounded constructor/health-prefix fixture above is complete. Extend it to
   real participant resolution and the supported dispatcher branch before
   treating the observed write as full hostile consumption. Its missing-attacker
   and formatter negatives must remain unavailable for attacker attribution.
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
