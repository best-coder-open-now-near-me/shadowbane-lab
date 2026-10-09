# Native movement interruption qualification

The offline `combat_power_movement_probe` executes the exact client 1.3.38.15
movement call at RVA `0x631a3`, argument setup at `0x63198`, thunk `0x258d3`,
full state setter at `0x5f8c0`, CharacterActivityEvent constructor at `0x44f840`
and synchronous listener traversal at `0x4520c0`. Both original and prepared
images are sealed by full-file hash before executable bytes are copied.
The package requires both image runs for each native profile. The probe is
excluded from default builds and is never linked into the runtime DLL.

Twenty-two cases per image cover prior states 4 through 8 with zero, one or two
equal initiation IDs, then callback changes to actor key, scene, vector geometry,
power ID or state pointer, nested execution and an injected exception. The
callback sees the prior state; the setter writes state 7 after the callback.
The protocol vector remains unchanged. A coherent single-ID transition from
state 6 to state 7 is a local activity interruption candidate, not proof that
the protocol ID was removed or a server request failed.

Reference accounting, locks, event base/destruction and animation are named
substitutes. The real dispatcher runs with one synthetic listener, not the live
listener set. The continuation after the movement call returns locally rather
than executing subsequent movement or networking. Foreign C++ SEH handlers are
replaced with an exception-search handler; `/SAFESEH:NO` applies only to this
fixture. The exception case proves rejection of abnormal return, not native
C++ unwinding or destructor behavior.

No live process is opened. No movement hook or application-journal authority is
introduced by the probe checkpoint. A later observer must retain independently
sealed actor/scene lifetime and shared mutation generation across callbacks;
identical before/after bytes alone cannot exclude same-ID replacement.

The user's later manual test corrected the earlier attack-cancellation theory:
attacking did not interrupt that potion attempt. Movement interrupted a later
attempt, whose diagnostic capture contained initiation but no terminal packet.
Missing packets do not establish failure. This evidence does not justify a
blanket attack or buff barrier, or waiting a fixed duration. Ordinary native item
eligibility and interruption reconciliation remain a separate source task.

## Ordinary item caller

The existing `combat_item_probe` now includes the full ordinary actor item caller
at `0x79040`, its concrete type-mask check and virtual ArcItem::Use call at
`0x792b7`. Twenty-five cases per image retain the ten ownership/queue cases,
add six direct Use cases and nine ordinary-caller cases. The caller rejects
movement state 7; states 5 and 6 reach the ordinary potion queue with zero, one
or two retained protocol IDs. State and vector are unchanged after the call.
The existing allocation/clock/lock/final-transport substitutes remain; no network
data is sent and native foreign C++ unwinding remains outside the proof.

An empty protocol vector is therefore not an ordinary item eligibility rule.
This does not authorize arbitrary bot submissions during a cast. Interruption
reconciliation must retain current activation generation and fresh actor/scene
state, rather than assuming the vector contains only one ID. Repeated same-ID
entries are native behavior; their count cannot establish a new activation or
prove which pending use ended. These probes do not themselves change runtime admission.

The subsequent readiness correction separates the global active-initiation fact
from per-action eligibility. A positively captured stationary state 5 can expose
an item opportunity despite retained IDs. Item submission and its final native
entry callback recheck this fact, exact operands and all existing arbiter gates.
That item-only checkpoint left power readiness, power/attack submission and
target attachment unchanged. The later self-power correction is described below. Movement and active state 6 never qualify the item
exception. The application journal still suppresses every unresolved queued
use; this readiness change does not remove that history or implement retry.

## Retained lifecycle contract (source integration in progress)

The shared activation model retains an immutable journal slot and monotonically
increasing ticket for the exact actor/key/scene. Positive owned queue evidence
precedes association with an incoming activation. Qualified direct owned power
followup can establish state 6 when its coherent capture actually observes it;
the subsequent incoming start continues that generation. Otherwise the incoming
state-setter and append must belong to one exact Process invocation, and the
start becomes active only after its normal return. Reentrant native activity
invalidates candidates even when memory bytes later match again.

Movement interruption and normal completion are distinct terminal local facts.
Normal completion requires the qualified successful message path, its state
transition and both first-match remover sites, followed by normal Process return.
Neither terminal fact requires the bookkeeping vector to be empty. Positive old
terminal evidence survives later manual work without claiming ownership of it.

Publication state `interrupted` is appended as value 3; actor-action receipt
application value 4 denotes the same interpretation. Existing values and record
layouts are unchanged. The record retains exact command digest, submitted
revision, queued/entry history and independent local settlement. Its terminal
observation revision is later than submission. An old interruption cannot clear
a newer same-group command; a late local settlement cannot reinsert the old
application. Complete native effect presence remains independent positive proof.
Normal local completion alone does not assert remote application or permit a
retry. Native observer wiring and host-policy integration are required before
this model/journal checkpoint can be treated as a production renewal repair.


## Stationary self-power readiness

The self-power observation correction retains `initiation_clear` as a factual
empty-vector/non-state-6 observation. It separately publishes positively captured
stationary state 5 in the first reserved frame word, offset 92. The frame remains
its existing size and version; the remaining reserved bytes must be zero. Older
readers reject a new nonzero word rather than silently accepting authority they
do not understand. A READY self-power requires clear initiation or this explicit
stationary fact. Unknown frames cannot carry either authority, and a changed
stationary fact advances admission revision.

For stationary state 5, retained same-power or other-power IDs no longer impose
an extension-only readiness veto. Native learned/self-target/category checks,
peace-mode requirements, movement/auxiliary definition flags, recovery and reuse
remain in force. The actual native Use path remains the final legality check.
State 6 remains active initiation; this does not reinterpret the global clear
predicate or widen target attachment, attacks or target-power admission.

The private static audit seals both original and prepared client .15 images and
identical spans for Use `0x9bbf0..0x9bf30`, dispatch `0x9c710..0x9d43d`,
PreparePower `0x4def0..0x4ed1d` and followup `0x9d7b0..0x9e194`. The first three
normal control-flow traversals contain no direct protocol-vector access at actor
offsets `0x65c/0x660/0x664`. Followup appends IDs without requiring an empty vector,
including duplicates. This is a direct-flow and callee-boundary audit, not proof
that every transitive helper lacks such an access. Type, resource, targeting,
reference, position and other helper behavior remains native authority.

The dispatch calls PreparePower through actor virtual slot `+0xc4`. The ordinary
non-instant branch calls the real state setter at `0x4eabd` (through `0x258d3` to
`0x5f8c0`) with state 6 before successful dispatch. Call `0x9d353 -> 0xa3910`
constructs the message/reference wrapper; the outgoing sender is
`0x9d3d4 -> 0x5a65 -> 0x7f4da0`, followed by
`0x9d3e0 -> 0x6659 -> 0x9d7b0`. The `+0x274` special branch can skip state 6;
readiness alone therefore cannot prove local settlement. Integration must retain
an independently qualified owned-return/cleanup path for that branch, without
asserting remote application or waiting for effect presence.

The expanded exact-image mode/movement/auxiliary predicate fixture passed 272
cases on each image. Its locks are named instrumented ECX substitutes; it does
not execute complete Use, prove native synchronization or establish server
outcomes. The compact private static receipt is
`artifacts/persistent-buffs-20261008/self-power-retained-ids/static-qualification.json`,
SHA-256 `61f1da43a9e9e222b8ef8aad581a7e55bfc14bb6ddbf6a79fe31da8ae79441d1`.
Raw client bytes and disassembly remain private.

The observation/publication slice passed both affected native tests and 288 host
tests without skips, including the actual native publication mapping roundtrip.
Tests cover state 5/6/7, zero/same/other retained IDs, auxiliary changes during
capture, explicit stationary encoding and rejection of inconsistent authority.
Final combined native submission and local-cleanup review is separate; no live
runtime or application journal is changed by these qualification claims.
