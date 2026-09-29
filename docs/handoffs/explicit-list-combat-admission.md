# Explicit-list combat source delivery

Branch: `codex/explicit-list-combat`, based on freshly fetched `origin/main@a91dfd5`.
Manual-runtime source checkpoint: `87d0251`, pushed.
The completed manual-list source transaction and validation are recorded in the
latest September 28 status below. Integration destination is `main` through
[draft PR #39](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/39),
first combined and reviewed on `codex/bot-integration-20260928` with PRs #40, #41,
and #42. Source now includes native attacks gated by verified image, service
readiness, current ownership, and saved intent. This is source delivery, not an
installation or live gameplay acceptance receipt; the running VM is unchanged.
Automatic response insertion still lacks authoritative response-event provenance.

Earlier checkpoint sections below preserve their original validation and pending
work at that time. Their disabled-service and next-work statements are historical;
the latest status supersedes them.

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

## Shared schema 2

The mapping is 320 bytes, fixed-width little-endian. Both implementations and the shared
hex fixture enforce its geometry. Mapping name is `Local\WonderBane.CombatFence.v2.` plus
32 lowercase UUID hex digits; mutex name adds `.lock`. Producers create once and reject
existing objects; consumers/mutators only open. Explicit protected DACL grants the current
Windows user access and disables inheritance. This coordinates trusted same-user processes;
it does not defend against that user's malicious code or privileged administrator override.

| Offset | Data |
| --- | --- |
| 0 | Eight-byte magic `WBCFNC2` plus NUL |
| 8 | uint32 schema=2, size=320 |
| 16 | uint32 state, reserved zero |
| 24 | uint32 native client PID, producer PID |
| 32 | uint64 client creation FILETIME, producer creation FILETIME |
| 48 | uint64 producer generation, movement Grant generation, scene epoch, list revision |
| 80 | 16-byte request UUID |
| 96 | 32-byte store-path digest, owner digest, saved entry digest, operation digest |
| 224 | Local object key and target object key (two uint32 each) |
| 240 | SHA-256 of the complete exact saved target name in UTF-16LE |
| 272 | 48 reserved zero bytes |

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

## Initial admission checkpoint validation and next work — historical

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


## Owner-service cleanup integration — historical checkpoint

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
token using EqualSid. Hosted CI is fully green for checkpoint 05386d0 across
Python 3.11..3.13 and both native profiles; the newer typed-binding checkpoint
will run the same gates when pushed.

The fixed-size typed command design retains the existing 576-byte payload: Host16,
window8, Grant216, UUID16, immutable ticket digest32, exact UTF-16 local-name/server/
target-name digests96, local/target keys16, revision8, store/owner/entry/operation
digests128, reserved40. All 320 mapped bytes are reconstructible from command plus
current channel process identity and must match; digest checks add a reference pin,
never replace current native identity or admission. UTF-16 digests cover complete
strictly decoded native strings without case folding or truncation. The typed binding and saved-store registration are implemented and validated;
channel routing and actual native combat remain disabled until the complete transaction is ready.


## Typed immutable command binding — historical checkpoint

`register_combat_admission` now derives command metadata from the current saved
entry and registers only that exact durable revision. A concurrent edit between
metadata capture and registration rejects instead of mixing identities. The native
576-byte command reconstructs all 320 fence bytes with its own process lifetime;
canonical SHA-256 ignores only the mutable state by encoding REGISTERING. Native
admission still compares every immutable mapping field under the no-wait mutex.

Fence ABI 2 uses 32 formerly reserved bytes to pin the exact saved target-name
digest. This is required because the durable entry ID intentionally identifies
server plus player key. A forged self-consistent command cannot replace the saved
name. ABI 1 was never activated or merged; v2 uses a distinct kernel name and rejects
old bindings without a compatibility fallback. Mapping geometry remains 320 bytes.

Native identity checking accepts complete strict UTF-16LE sequences of at most
64 code units, preserves case/whitespace and combining characters, and rejects NUL,
unpaired surrogates or overlong strings. It independently rebuilds the existing
ASCII JSON owner and server/key entry hashes from current native identities, and
requires both players' full server strings to match. Hashes never authorize a
borrowed pointer, bypass current party/pet checks, or substitute for the ticket.

The shared C++/Python command fixture and real spawned native consumer verify exact
lifetime/generation binding, wrong owner/name rejection, and both remove/entry
orders. All 80 focused host tests pass, including the existing record/list suites;
both native wire/fence fixtures pass in both VS2022 profiles. Command kinds 34=start,
35=status and 36=cancel are reserved after vendor kinds 25..33; preserved furnishing
branches contain no collision. No channel capability, hooks or attacks are enabled.
The active next item remains the owner-thread selection/attack/cancellation service
and its factory/outbound-queue receipts, followed by host combat recovery wiring.

## September 28 command receipt presentation — historical checkpoint

The normal text listener now displays the saved list revision and every entered
request that still requires native cancellation. It states that cancellation is
not confirmed before displaying the remaining entries or an empty list. A successful
saved-list edit therefore does not conceal an outstanding combat cleanup obligation.
JSON continues to retain the original structured mutation receipt unchanged. An
empty cancellation receipt makes no claim that native cancellation completed.

Validation: 78 attack-list, combat-wire and combat-fence tests passed with the
existing VS2022 full-profile Win32 consumer enabled, with no skipped tests. The
native entry -> clear mutation -> listener formatter regression checks the actual
entered-ticket receipt; formatter cases cover add, remove, clear, multiple request
IDs and unchanged JSON output. Ruff passed for the touched Python files. No native
source, installed runtime, wire format or saved provenance changed.

Next remains the complete native owner-thread combat transaction. Current
`command_channel.h` has no combat queue routing, and only runtime tests install
`combat_owner_service`/`combat_owner_stop`; the production service is absent.
Implement its start/status/cancel queue and retained stop/retirement callbacks on
the existing owner service boundary. Before enabling the capability, require fresh
exact player/party/native legality checks, revalidate after selection callbacks,
enter the saved-intent fence immediately before attack, correlate the specific
outbound request, and complete exact-Grant cancellation before PvE recovery. The
receipt presentation does not supply any of those missing action guarantees.

## September 28 transaction work — early checkpoints

The shared-session host protocol is published at `4d9f007`: typed 384-byte receipts
correlate the complete immutable request, and START/STATUS/CANCEL use the existing
movement session and producer lease. Focused validation passed 51 tests with seven
existing native-consumer skips. The capability remains unavailable until the
production native service is installed and fully qualified.

Native party protection is published at `297ff12`. Two bounded complete roster
captures must agree on scene, roots, links, entries, exact keys, and roles. Unknown,
unreadable, partial, duplicate, or changed rosters reject admission. The local
actor and every roster member remain protected. The Win32 native test passes,
including unreadable memory and replacement during capture. `de17010` centralizes
the same attack-list storage root for command editing and bot execution; all 51
existing attack-list tests pass.

The [native entry contract](../native-combat-entry-contract.md) records the
completed offline callback qualification and its limits. Native factory/append
correlation, owner-service integration, and host recovery remain in progress;
these checkpoints do not claim completed gameplay activation or live acceptance.

## September 28 latest transaction status

Manual-list host composition is complete: the canonical PvE runner uses its
existing movement session, producer lease, and exact Grant. A candidate comes from
coherent loaded-player and party observations plus durable manual intent; native
entry independently verifies the full saved name/server and exact key. Host
preflight requires combat readiness, pauses existing PvE under that Grant, then
registers the immutable ticket and sends one START. Uncertainty retains that
ticket and routes STATUS/CANCEL; a readiness drop blocks new START while preserving
cleanup for the existing exact owner. A never-entered cancellation tombstone
prevents a delayed START from attacking.

The production native service routes START/STATUS/CANCEL on the existing owner
update. It retains actor and target references, rechecks party and selection,
admits the single-use fence at D0, and correlates that exact request with outbound
queue insertion. The receipt proves local queue ownership only. Cancellation uses
the native stop path and verifies mode 1, action state 1, and no combat target
before releasing the old owner's obligation. Actual scene retirement ends the
run. Confirmed local cancellation enters a distinct recovery state; health, mana,
stamina, and camp return must recover on fresh observations before another listed
START or ordinary PvE acquisition. No fake kill or name-only retaliation is added.

Host checkpoints include `3d98f07` (resolver/coordinator/recovery), `913b3b8`
(readiness and exact-Grant baseline pause), and `9ef272a` (cleanup after readiness
loss). Native target qualification is `c7ff3a8`; typed queue routing is `9469bd8`;
the complete production owner-service/runtime integration is `87d0251`.
The [native entry contract](../native-combat-entry-contract.md) records the
supported callback and caller-ownership boundaries. Private client images,
disassembly, captures, and build outputs remain outside the source commits.

Validation before the final native integration passed 3,480 Python tests with
33 skips and 756 subtests; Ruff passed. The latest host readiness/cleanup slice
passed 59 focused tests with three existing native-consumer skips. At `87d0251`,
both full and diagnostics-only native profiles build successfully. Each required
CTest run passed 179 checks and skipped three private-image fixtures; explicit
private-path runs then passed those three fixtures in both profiles, exercising
all 182 required checks per profile. Two optional renderer-transparency stretch
diagnostics still fail their known expectations; they are separate from the
required combat gates. Full combined candidate validation and supervised
package/gameplay acceptance remain next.
Keep PR #39 draft until those review and acceptance steps are resolved. Automatic
response insertion remains blocked on the separate
[server-session fence](../pvp-response-provenance.md).
