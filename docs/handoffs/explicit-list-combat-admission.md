# Explicit-list combat admission checkpoint

Branch: `codex/explicit-list-combat`, based on freshly fetched `origin/main@a91dfd5`.
Source checkpoint: `f9da2bfe9e2d699230e9473f9512f5dee0e8a790`, pushed.
Integration destination: `main` through [draft PR #39](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/39). Hosted CI is pending. This checkpoint changes saved-list
mutation admission and adds its native consumer; it does not enable native attacks,
install a package, change the running VM, or supply response-event authority.

## Delivered boundary

`AttackListStore.register_admission` reads current durable membership/revision under
its existing interprocess record lock. Only an exact manual persistent player entry
can receive a single-use ticket. Registration creates a Windows mapping and mutex,
publishes the bounded registration index durably, then arms the ticket before releasing
the list lock. A registered-but-unarmed ticket cannot enter. A crash before registration
leaves no discoverable authority; a crash after arming leaves the producer dead and native
entry rejects its exact retained process handle. No pointer, name-only target, response
entry, stale revision, or historical native observation supplies current permission.

Every actual add/remove/clear mutation revokes all registered tickets before durable
list publication under that same lock. Failed or interrupted publication leaves old
saved intent intact and old tickets revoked. Registration cannot slip between revocation
and publication. No-op edits leave the current revision/tickets alone. Registry corruption,
access denial and live mapping mismatch abort a mutation; earlier revocations stay in force.
No lock is held over a game callback. On first enrollment, the store migrates to schema 4 under the same lock, before any
ticket is armed. Membership and revision stay unchanged. Old hosts only accept schemas
1..3, so they reject before bypassing revocation. Subsequent writes preserve schema 4;
unfenced stores remain schema 3. Registry format is separate and indexes kernel objects,
never membership. A rollback to an older host must first retire all combat consumers;
do not downgrade an enrolled record while any ticket could still enter.

## Shared schema 1

The mapping is 320 bytes, fixed-width little-endian. Both implementations and the shared
hex fixture enforce its geometry. Mapping name is `Local\WonderBane.CombatFence.v1.` plus
32 lowercase UUID hex digits; mutex name adds `.lock`. Producers create once and reject
existing objects; consumers/mutators only open. Explicit protected DACL grants the current
Windows user access and disables inheritance. This coordinates trusted same-user processes;
it does not defend against that user's malicious code or privileged administrator override.

| Offset | Data |
| --- | --- |
| 0 | Eight-byte magic `WBCFNC1` plus NUL |
| 8 | uint32 schema=1, size=320 |
| 16 | uint32 state, reserved zero |
| 24 | uint32 native client PID, producer PID |
| 32 | uint64 client creation FILETIME, producer creation FILETIME |
| 48 | uint64 producer generation, movement Grant generation, scene epoch, list revision |
| 80 | 16-byte request UUID |
| 96 | 32-byte store-path digest, owner digest, saved entry digest, operation digest |
| 224 | Local object key and target object key (two uint32 each) |
| 240 | 80 reserved zero bytes |

The store digest binds the normalized absolute record path; owner and entry digests use
existing durable identity definitions. All bytes except state are immutable. The native
caller must supply the current independently validated command binding; state comparisons
ignore only the state word. The operation digest will be derived from exact worker and
operation tokens by the typed combat adapter, not treated as independent permission.

State transitions: registering(0) -> pending(1) -> entered(2). Revocation sends registering
or pending to revoked(3), and entered to entered-revoked(4). Terminal states never rearm.
The named mutex gives a linearizable admission transition; this is not hardware CAS.
Native `TryEnter` waits zero milliseconds and returns busy without admission if contended.
Abandonment revokes conservatively. A producer process death similarly revokes. An admitted
request is never admitted twice, including after an error or transport timeout.

Entered-revoked does not undo an action: it requires native owner-thread cancellation.
The list mutation receipt and blacklist command result report entered ticket UUIDs as
`entered_admissions_requiring_cancellation`. Consumers retain mappings until cancellation
completes. Closing the host ticket revokes and closes its handles; native-held mappings
remain readable. A failed close retains handles for a revocation retry and never claims
retirement. Missing mappings can be pruned because no consumer creates/recreates a
name. Names are never recycled. The index is limited to 128 live registrations per store;
exhaustion fails closed and requires consumers to retire rather than evicting live tickets.

## Validation and next work

Current validation: 72 host tests passed, including the existing attack-list suite and
19 fence tests plus the shared record-store suite. Tests use actual named mappings, a compiled Win32 native consumer, and
spawned independent producers/mutators. Schedules cover remove vs entry, registration vs
remove, producer death before/after arm, abandoned mutex, mutation death after revocation
before publish, failed atomic publication, stale generation, duplicate entry, capacity,
store isolation, current-user DACL and UUID reuse. The native shared-fixture test passed;
CI now builds and runs host/native interop in both native profiles instead of skipping it.
No client binary or game process is needed for these checks.

Next active task is the typed owner-thread combat transaction: connect this ticket to the
existing producer lease/heartbeat and movement Grant, reacquire the exact player with fresh
party/legal checks, revalidate after selection callbacks, enter immediately before the native
attack call, correlate the actual request with outbound queue insertion, and cancel before
PvE recovery. Use the existing native owner services and stop pipeline. The fence alone
never proves lease freshness, current scene/party/target, local queue submission, server
acceptance, or cancellation. The complete transition and supervised package acceptance
remain unfinished. Response-driven retaliation separately retains its server-session and
deferred-action authority blockers; no receive-only intermediate is enabled.

Private build output remains under this worktree's ignored `artifacts/combat-fence`.
No source draft, private game capture, or executable belongs in the PR.


## Owner-service cleanup integration

The existing movement controller now records owner-service native work separately
from `moving_`. `BeginNativeOwnerAction` is available only in the verified update
phase, for the exact acquisition host/lease, movement Grant and lifetime, with a
fresh UI/focus check. That query does not consume device-reset/input sample state.
The service must record responsibility before its first callback that can cause a
side effect; receipt success is never the ownership boundary.

Runtime stop composes the existing NativeStop cleanup with the combat service's
conditional exit callback before publishing any replacement Grant. Admission retains the exact service stop
and retirement callbacks until cleanup succeeds, even if service registration is
cleared meanwhile. Both callbacks must exist before admission. An installed
inactive service must return true without acting. A failed/cooldown-blocked exit
returns false, retaining the existing pending old-Grant cleanup obligation and
excluding new writers. Retry may stop only that Grant. Scene retirement notifies
the service without allowing old work to act against the replacement character.
Action admission is unavailable inside cleanup callbacks. No combat service is yet
installed, so this checkpoint changes ownership infrastructure without enabling
selection or attacks. The adapter still needs exact retained actor/player handling,
party/pet checks, conditional mode exit and local outbound request receipts.

Both VS2022 native profiles build the DLL and pass all 49 affected controls,
input, native-stop and runtime tests, including exact cleanup after unregister,
failed-stop retry, lease/UI loss and callback reentrancy. Independent review found
no additional issue in this ownership slice. Hosted CI earlier found a test-only
SDDL alias assumption; the test now compares the actual ACE SID with the current
token using EqualSid, and fresh CI is pending.

The fixed-size typed command design retains the existing 576-byte payload: Host16,
window8, Grant216, UUID16, immutable ticket digest32, exact UTF-16 local-name/server/
target-name digests96, local/target keys16, revision8, store/owner/entry/operation
digests128, reserved40. All 320 mapped bytes are reconstructible from command plus
current channel process identity and must match; digest checks add a reference pin,
never replace current native identity or admission. UTF-16 digests cover complete
strictly decoded native strings without case folding or truncation. This contract
is agreed for implementation; the typed command itself is not enabled yet.
