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
introduced by this probe checkpoint. A later observer must retain independently
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
prove which pending use ended. These probes do not change runtime admission.
