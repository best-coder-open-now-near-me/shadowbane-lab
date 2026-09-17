# Guard upgrades

Source branch: `codex/guard-upgrades`, isolated worktree `.worktrees/guard-upgrades`.
Base: vendor branch `61e6fd8`, after fetching origin and verifying the documented
integration branch is an ancestor. Guard changes should be reviewed into
`codex/vendor-rolling`, then `codex/native-lifecycle-hardening`, followed by `main`.
The shared navigation source now supports separately typed guard selection; no
new native build has been deployed. No guard upgrade has been sent by the agent. Town automation remains unfinished.

## User policy

Upgrade all guards toward maximum rank, as far as available gold permits. Read
current costs and funds for each request; avoid already-upgrading or maximum-rank
guards. Do not infer a shared town balance from one building's funds or assume
all guard types use the same cost. The user identified warehouse gold as the funding source after confirming the
structure has no upgrade funds. Warehouse withdrawal and structure deposits
are required parts of the feature. The user-operated bounded transfer is
qualified; automatic transfer commands and funding receipts remain unfinished. Guard
upgrade receipts are now durable in host source. Do not claim that a button's availability establishes enough money.

## Completed observation slice

`client observe-native-guard-upgrade --process-id PID --json` reads the selected
type-37 guard's active Hireling Management window and the owning building roster.
The read-only implementation passed live validation without installing code or
changing the game. It enumerated all six occupied rows despite the UI viewport
showing two. Guard rows use key type 37; crafting vendors use type 42. Existing
crafting readers retain their type-42 restrictions. Other hireling types remain
visible as unqualified rows and cannot become eligible guards by display name.

The observer validates the executable, rooted manager, in-world/online mode,
both initialized HUDs, distinct HUD identities and ownership, live stack
membership, exact selected/displayed building keys, complete occupied/vacant
counts, selected row membership, unique keys and named control ownership. It
rechecks all captured bytes before returning. Cost, flags, rank and control
changes invalidate an observation. Results never authorize commands or claim
city completeness, permissions or server acceptance.

Static evidence, RVAs in reviewed source executable ac9ca464:

- ArcHirelingListEntry constructor 0x5b5c00 copies rank from response +0x40 to
  row +0x28 at 0x5b5dfb. Management refresh 0x6d3cb0 reads that rank at
  0x6d3d10 and passes it to the rank control at 0x6d3eca.
- Selected entry is rooted at manager +0x384. The known row type is 0x1169518.
- HUD name lookup 0x5df970 traverses its owned +0x54 vector. Its name getter
  0x576ed0 reads the ArcString at widget +0x164.
- Hireling refresh reads cost manager +0x274 and flags +0x2ac/+0x2ad at
  0x6d3e7e..0x6d3e98. Formatter 0x6e0af0 distinguishes an upgrade in progress,
  a numerical next cost, and the unavailable-upgrade label. The selected menu
  exposes BTNUPGRADE, BTNUPGRADECOST and SLIDEUPGRADE.
- Displayed building funds come from manager +0x1cc at 0x6d3e1d. This is not
  evidence about the player's purse, a guild bank, or funds in other structures.
- The ordinary confirmation text is CityAssetMessage:UpgradeHireling at
  string RVA 0x1348c80. The ordinary handler is now traced and implemented in the native command
  boundary below; automatic submission still needs live qualification. No raw
  packet construction or force-upgrade path is used.

## Validation and current todos

- [x] Read the exact live executable and open guard menu without game writes.
- [x] Implement a reusable, read-only guard observer and CLI command.
- [x] Verify live guard identity, complete building rows, rank, cost and flags.
- [x] Pass 68 focused guard/vendor roster/queue tests; preserve vendor rejection
  of guard types and CLI handle cleanup on success/failure.
- [x] Qualify a bounded warehouse withdrawal, exact structure deposit and one
  guard upgrade start through user-operated ordinary controls. Structure funds
  matched the intended deposit, then were deducted for the selected guard;
  the selected guard's upgrading flag and visible progress control were confirmed.
- [x] Implement typed-input structure deposit observation; 100 focused guard,
  deposit, vendor roster and production-queue tests pass, and targeted Ruff passes.
- [x] Add native and host guard navigation with distinct type-37 admission,
  exact-key response correlation and immutable duplicate-request receipts.
- [x] Implement native/host funded guard-upgrade commands, ordinary confirmation
  callback, exact before-state admission and correlated observed progress/debit.
- [x] Qualify warehouse quote source, balance, configured reserve, and typed amount.
- [x] Require durable host intent/submission/completion records for guard upgrades;
  retain unresolved outcomes across restarts and block duplicate/new spending.
- [x] Implement native/host withdrawal and deposit from exact owned quotes, with
  current purse checks, two-sided receipts, and one durable spending gate.
- [x] Open withdrawal/deposit amount windows through their owned warehouse or
  building controls, with single-Gold selection and durable preparation receipts.
- [ ] Active: connect exact warehouse/building traversal to the town funding and
  upgrade loop; verify city coverage instead of assuming nearby rows are complete.
- [ ] Qualify automatic navigation across guard structures and other guard types.
- [ ] Connect the durable guard journal to the maximum-rank scheduler
  with finite work per pass; retain every uncertain action without replay.
- [ ] Present progress and unresolved/blocked guards in the manager; validate the
  full flow and integrate through the branches above.

No automatic guard action is installed. Existing crafting jobs and historical
unresolved navigation requests must not be resumed or rewritten. The vendor
1.8.9 discovery qualification remains pending when that work resumes.

The UI helper failed before app enumeration (sandbox deny-read ACL error), then
failed again after reset. VM screenshots and bounded native reads supplied the
inspection. Automatic review rejected a proposed shared-folder export of live
roster details; that export was omitted. No new live roster file was written.
Task-local screenshot scratch is under `artifacts/guard-upgrades` in the normal
project root and remains private. Public source contains no client binaries,
credentials, private captures or live roster identities.

## Warehouse funding investigation

The live warehouse exposes Withdraw, Deposit and Deposit All. No direct
warehouse-to-structure or warehouse-funded guard-upgrade control has been found.
The client resource-lock tooltip explicitly describes warehouse payment for
upkeep; that is not evidence of direct guard-upgrade funding. Its ordinary
withdrawal prompt includes total, minimum balance and available amount. A total
warehouse balance must not be treated as the spendable upgrade budget.

Warehouse HUD vtable RVA 0x1170308 was observed in the owned live HUD stack.
Its resource list is named WAREHOUSE_INV and has list vtable 0x116acf0. Ordinary
controls are WITHDRAW, DEPOSIT and DEPOSITALL. The static withdrawal prompt at
RVA 0x134710c is referenced by the handler at 0x69e4f1. Structure management has
separate CityAssetMessage:WithdrawGold and CityAssetMessage:GoldToDeposit labels.
No withdrawal or deposit was sent by the agent, and no warehouse row reader or
transfer command is qualified yet. Private balances and roster identities are
not included in this source handoff.

The durable flow should discover guard structures, quote each eligible next-rank
upgrade, determine spendable warehouse gold after its reserve, withdraw only the
required shortfall, verify receipt in the character inventory, deposit into each
exact structure and verify its new balance before upgrading. Keep receipts for
both transfers and upgrades so an uncertain response cannot cause a duplicate.
Recompute each pass as ranks and costs change; do not pre-fund an entire town
using a single guard's cost or guess the maximum rank.

## Withdrawal quote and character-switch qualification

The user's new character was re-observed through NativeCharacterConfigReader;
old character inventory, window pointers and quote amounts were discarded even
though the game PID and creation time had not changed. Server and City of Temple
were verified again. This establishes why funding jobs must bind a character and
scene lifetime, not just a process lifetime. Character identity was compared
before and after the bounded memory reads.

The live amount HUD has vtable RVA 0x1168044. Its +0x108 points to the current
warehouse HUD, whose +0x10c points back to that exact amount HUD. Both are members
of the live root's HUD stack. Vtable slot +0x120 resolves through thunk 0x2254d to
RVA 0x5952e0, which installs those reciprocal links. The quote's resource context
at +0x388 matches the selected warehouse row's resource ID at +0x20. The owned
warehouse resource entry has vtable RVA 0x116f258 and its amount at +0x48 agreed
with the displayed total. Its CHAR_INV list was empty in the fresh character.

Withdrawal quote creation at 0x69e380 looks up a minimum by resource in warehouse
+0x3e8, subtracts it from the total argument and clamps a negative result to zero
at 0x69e3df..0x69e3e9. It initializes both maximum and current amount to that
available amount through thunks 0x13cf5 and 0x1d8f9. Their implementations at
0x5956f0 and 0x595720 store +0x3c0 and +0x3c4 respectively. The live displayed
available amount and both fields agreed. The screenshot omitted a minimum line;
only the observed equality of total and available establishes no withheld amount
for that particular quote, not a permanent warehouse policy.

No confirmation or transfer was issued by the agent. The user has been asked for
a bounded single-upgrade withdrawal followed by opening the target structure's
deposit amount prompt, without confirming that deposit. Revalidate inventory,
character, selected structure key, current balance and ordinary deposit callback
before qualifying the deposit. Do not treat the generic amount HUD type alone as
proof of withdrawal versus deposit direction. The current checks are research
evidence; a reusable warehouse/funding command is still unfinished.

## First complete funding-to-upgrade qualification

The user opened a deposit prompt in a second structure with the same visible
name as the first. Its unique key and six guard keys differed. Inspection switched
to the actual, explicitly user-selected destination rather than treating the
repeated label as identity. Its selected/displayed building keys matched, the
online asset manager was in gold-deposit mode 13, and its balance was zero.

Deposit prompt construction at RVA 0x6cf1d0 differs from warehouse quotes:
manager +0x74 owns the amount HUD, and amount HUD +0x104 points back to the
manager. Mode 13 reads the character purse through the local-player interface
at global RVA 0x16a2d98 plus 0x688 and uses the result for the maximum amount.
Modes 12/44 instead use structure funds and are not deposits. Construction sets
the normal ACCEPT/CANCEL event modes at control +0x1d4/+0x1f8/+0x21c. The
warehouse's +0x108/+0x10c reciprocal ownership is not used for this prompt.

The live typed amount was positive and exactly matched the deposit limit, but
amount HUD +0x3c4 still held zero. GetAmount at RVA 0x595390 looks up SLIDEHELPER,
uses its vtable +0x6c getter (RVA 0x56c5f0) to read its ArcString at +0xa4,
parses it, then clamps it to the maximum. Automation must inspect that actual
text, not the initialization cache. The reusable read_native_structure_deposit
reader now checks exact root/building/menu/action ownership, decimal input and
bounds, and rechecks all fields. The recorded limit is explicitly the purse
limit at prompt creation, not proof of a later live purse balance. It never
sends a transfer or grants command authority.

After the user confirmed the bounded deposit, the exact target's displayed gold
increased by the entered amount, its prompt closed and manager mode returned to
0. The user then opened one guard in that structure and confirmed its quoted
upgrade at the same cost. The observer verified that exact guard selected in
mode 6, the structure balance reduced to zero, upgrade_in_progress true and
SLIDEUPGRADE visible. can_upgrade and the Upgrade button remained enabled, so
neither alone is sufficient to decide whether to submit another upgrade. The
rank remained 1 during the timer; upgrade completion/max-rank behavior has not
been qualified. The complete guard observer passed against this live state.

All transfer and upgrade clicks in this qualification were performed by the
user. The agent sent no gold or upgrade action. No repeat of this first upgrade
is needed. Next active work is implementing native command admission and
receipt tracking, then the town scheduler; city-wide automation is not installed.

## Guard navigation source checkpoint

Navigation opcode 16 opens a type-37 guard through its owned roster control.
Opcode 15 remains restricted to type-42 vendors. Observations admit both qualified
hireling types, including mixed rosters, without relaxing crafting action gates.
The existing scene/producer lease, foreground, exact before-state, timeout latch
and immutable request journal apply to guard selection. A same-ID type-42 window
cannot complete a type-37 request. Selection without the exact visible window
also cannot complete it.

The full Win32 extension builds with warnings treated as errors. All three native
navigation suites and 107 focused Python navigation/guard/deposit/vendor tests
pass, including native/host byte agreement; targeted Ruff passes. This is source
validation only. Keep the installed 1.8.9 extension until the complete funding and
upgrade flow is ready for a versioned deployment. No automatic guard or gold
action has been run.

## Funded guard-upgrade command source checkpoint

The dedicated native and host wire protocol uses inspect opcode 17 and upgrade
opcode 18. The 128-byte snapshot embeds the exact navigation/scene identity plus
selected rank, price, displayed structure balance, upgrade flags and named
control identities. Upgrading guards, visible progress bars, unavailable controls,
unfunded requests, stale scenes and type-42 crafting vendors are rejected.
The final invocation re-reads ownership, state, foreground and producer lease
on the owning game thread. A guard action in flight or unresolved also blocks
other navigation/crafting actions from replacing its context.

Static trace: live BTNUPGRADE's first action at control +0x1d0 is 0x58b, with
zero parameter at +0x1d4. Dispatch 0x6ca396 creates UpgradeHireling confirmation
in manager mode 20. Its ordinary Yes action 0x458 reaches 0x6c5e3a, which calls
thunk 0x92a0 -> 0x6d7c70. That void method uses manager +0x384 for the selected
hireling and +0xf8 for the displayed building, and emits the ordinary upgrade
request. The native integration calls this ordinary confirmed action after its
own exact typed/cost/funds checks. It does not call the adjacent mode-19 method.

Each native request UUID retains its original receipt for the process lifetime.
An accepted local invocation is only submitted. Subsequent observation must
match the same scene, manager, building, guard and controls, with the exact
quoted debit plus visible upgrading progress or a one-rank increase. Partial
observations remain pending; contradictory balances/identity/ranks or a 15-second
response timeout latch unresolved. A late response does not clear the latch.
Host upgrade timeouts never retry automatically. Native receipts are not durable
across a client restart; the unfinished host transaction journal must be completed
before exposing this flow through the dashboard.

Purse getter research: the observed player +0x688 interface has vtable RVA
0x11415e4; slot +4 resolves via 0x1c49f to 0x4bc10. It obtains an inventory gold
object through slot zero (0x1686f -> 0x4bc70), then reads that object's +0x690.
Do not incorrectly read player +0x690 as purse gold. This accessor has not been
invoked by the agent. Warehouse withdrawal builder 0x69e380 configures ACCEPT
action 0x1009 and CANCEL 0x100b; this is separate from structure deposit mode 13.

Validation: full Win32 extension build, all 11 native guard/navigation/vendor/city
suites, focused Python protocol/observation/action-channel regressions and Ruff.
A bounded read of the existing live menu still showed the prior guard upgrading;
no second request was sent. No new DLL or host is installed and no automatic
funding or upgrade operation has run. Keep native 1.8.9 installed until the full
funding/journal/scheduler flow has a versioned, validated deployment.

## Warehouse quote and reserve qualification

The reusable read-only warehouse observer is now qualified against the user's
open, unconfirmed gold quote. The live source reference belongs to a type-42
warehouse hireling, not a type-8 structure: warehouse +0x378 points to an object
with vtable RVA 0x114165c, whose +0x18/+0x1c reference is used by withdrawal.
The source identity, reciprocal HUD ownership, unique resource row, actual typed
amount, enabled ACCEPT/CANCEL controls, and current reserve map are rechecked.
The maximum must match the current resource balance less its configured reserve;
a stale quote or inconsistent tree is rejected. This observation does not verify
the current purse, authorize a command, or claim server acceptance. No gold moved.
All 69 focused warehouse/deposit tests pass, including source type mismatch,
stale balances, malformed reserve ownership, and changing inputs.

Ordinary withdrawal dispatch at RVA 0x69d49b handles ACCEPT action 0x1009,
reads resource ID from quote +0x388 and GetAmount through 0x18692 -> 0x595390,
then calls 0x28ec5 -> 0x69f500(warehouse, resource, amount). This method constructs
operation 0x11 using the source reference above. The UI handler subsequently
closes its quote. This path has been traced statically but not invoked by the agent.

The structure amount handler at 0x6cbb00 accepts action 0x456/0x458 and forwards
its mode to 0x1a050 -> 0x6cc3e0. Mode 13 deposits positive GetAmount into the
selected/displayed structure; mode 12 withdraws instead. The ordinary amount
setter 0x595720 updates cache +0x3c4 and refreshes the visible text through
0x5958b0; any future command must recheck actual input after setting it. Opening
a structure deposit uses normal building action 0x586, not a direct mode write.

The common button callback slot +0x2c resolves through 0x16860 to 0x5f5440.
Unlike the roster selection callback, its event index 0 selects first action
+0x1d0 (entries stride 36 bytes). Its return value is not server acceptance.
No callback has been qualified by live invocation here. Remaining work is the
durable spending journal, native funding admission/receipts, and town scheduling.

## Durable guard spending checkpoint

NativeGuardUpgradeSession now requires an instance-local GuardUpgradeJournal for
Upgrade; read-only Inspect remains available without it. The exact command,
request UUID, game process lifetime, host process lifetime/lease and scene-bearing
snapshot are atomically recorded before transport. A cross-process lock serializes
spending, so a new UUID cannot bypass an active attempt. Historical UUIDs cannot
be reused even after completion or proven non-submission. The manager must bind
the journal to its persistent client-instance directory, never a temporary job or
host-process directory. This is guard-upgrade storage, not yet a funding ledger.

A separately correlated native inspection completes the record only for the same
owner/controls, exact debit and upgrade progress or one-rank increase. Lost replies,
corrupt/missing records, failed writes and changed ownership retain uncertainty.
Native unresolved flags are persisted and cannot be cleared by later observations.
A completed record written before a failed active-pointer clear can be recovered
without another game action. A proven non-submission may release the spending gate,
but its UUID remains spent. There is no automatic reset, retry or history erasure.

Validation: 174 focused Python guard/warehouse/deposit/navigation/record-store tests
pass, including real native/host wire agreement, and targeted Ruff passes. The
8 built native vendor/guard/navigation suites pass. A broad unfiltered CTest attempt
also selected unrelated executables absent from this focused build directory;
those suites were not run and are not claimed as validated by this checkpoint.
No native source changed in this checkpoint and no runtime update was installed.

Next active work remains native funding capture/admission: read the current purse
on the owner thread, bind warehouse withdrawals and structure deposits to exact
identities and amounts, and require both balance changes before proceeding. Then
connect shared spending exclusion, town traversal, maximum-rank passes, manager
progress and a coherent versioned deployment. The warehouse quote was read only;
no agent withdrawal, deposit or guard upgrade has run.

## Native funding command checkpoint

The native funding boundary adds inspect/transfer opcodes 19/20 with a typed
warehouse-withdrawal or structure-deposit direction. Its snapshot binds the
character/scene, exact source hireling or destination structure, resource, current
balance/reserve/purse, owned quote and controls. The purse is read through the
reviewed accessor on the game owner thread after validating its interface slots;
that traversal runs on demand, not on every idle frame. Warehouse Gold is matched
to one unique named resource row and its exact ID, never an inferred missing row.

Transfer admission requires a fresh matching quote, requested amount within its
current limit, reserve protection and no signed balance overflow. The ordinary
amount setter is followed by a complete recapture before confirmation. Withdrawal
uses the owned ACCEPT callback (event zero); deposit calls the ordinary mode-13
handler. Local callback completion is only submission. Both balances must move by
the exact amount in opposite directions and the quote must close under unchanged
ownership. Partial changes remain pending; contradictory changes, identity/reserve
changes or timeout latch unresolved. Immutable UUID receipts prevent resubmission.
Funding, guard upgrades, crafting, city opening and navigation share exclusion.

Validation: full Win32 DLL build with warnings as errors and 14 focused native
funding/guard/vendor/navigation/city suites. Funding fixtures cover real owned
HUD/roster/map layouts, purse access, failed amount setters, stale input, both
ordinary callback signatures, wrong keys, reserve/overflow limits, partial receipts,
lease expiration and duplicate UUIDs. These are fixture executions, not live gold
transfers. No new native build is installed. Next is the host funding session and
one persistent spending gate shared with upgrades, then automatic quote opening,
town traversal, scheduler/dashboard integration and versioned live qualification.

## Host funding and unified spending checkpoint

NativeGuardFundingSession now exposes direction-specific Inspect and bounded
Transfer with exact host/window/request correlation and no transfer retry. Its
96-byte snapshot, 576-byte command and 384-byte receipt match native fixture bytes.
The transport admits the typed funding command alongside existing command classes.

The unreleased guard journal is now GuardSpendingJournal in
client_extension/guard_spending_journal.py. Both upgrade and funding sessions use
the same persistent client-instance root, active pointer and cross-process lock.
Schema 2 records distinguish upgrade and transfer and decode only that operation's
wire format. A pending withdrawal blocks both deposit and upgrade, and vice versa,
including after manager restart. Wrong-kind receipts cannot complete an action.
No previous guard journal was installed or used for live spending; unknown/older
record schemas stop for review rather than being silently discarded or migrated.

Keep the submitting transport/session alive through its correlated completion.
The native channel supports one producer lease: a scheduler must not open another
transport while the active one is leased, or close/reopen it to obtain a different
host lease while a spend is pending. After observed completion, sequential session
handoff is supported. Future manager ownership should keep that sequencing explicit.

Validation: 214 focused Python funding/upgrade/journal/observation/navigation/
record-store/action-channel tests pass, with no skipped native wire fixture.
Targeted Ruff passes; the full native build and 14 focused native suites passed
for the immediately preceding funding boundary. Public source contains no live
city identities or balances. No deployment or live agent transfer occurred.

Next: automatic quote opening, town traversal and finite maximum-rank passes,
manager progress/review controls, coherent packaging, and live qualification.
The user should not be asked to repeat already-qualified manual transfers.

## Automatic amount-window opening checkpoint

The user opened Tower Junction management. Bounded read-only inspection verified
its enabled, visible BTNDEPOSIT control with action 0x586 and zero parameter.
The warehouse WITHDRAW control is action 0x1008; its ordinary handler copies the
selected resource set before opening the first quote. Selection is not inferred
from the currently displayed resource or amount. No agent UI action or transfer
was sent during this identification.

Funding opcode 21 now opens an amount window from its already-owned parent panel.
It requires an exact closed-quote snapshot, available funds, foreground/top-panel
ownership and the current producer/scene lease. Warehouse opening selects the exact
owned Gold row through the ordinary list handler, rechecks the entire snapshot,
requires the selection set to contain only that same entry, then activates the
owned WITHDRAW button. A nonempty pending withdrawal set blocks capture/actions.
Structure opening uses only BTNDEPOSIT/action 0x586; Withdraw, Upgrade, Abandon and
Destroy are not admitted. Opening itself carries amount zero and cannot transfer.

The native controller requires the exact resulting quote under unchanged ownership,
balances, reserve and purse. Opening has immutable request receipts and shares
exclusion with spending/navigation. The host open_quote method records preparation
in the same persistent journal (operation open_quote) and requires its correlated
observation before transfer. A lost response or unresolved opening is retained;
it is not silently replayed after restart. A transfer remains a separate positive
amount command and performs its existing setter/recapture/balance checks.

Validation: full Win32 extension build, all 14 focused native suites and 224 focused
Python tests pass, plus targeted Ruff. Native/host bytes match for both transfer
and open-quote commands. Fixtures test the ordinary row/button callback signatures,
wrong resource selection, deposit-vs-withdraw action identity, changed balances,
reused requests, lost replies, and opening followed by transfer. This does not
qualify live automated opening or full town navigation. No runtime update was
installed and no live gold moved. Next is the persistent town traversal/scheduler,
including warehouse access and demonstrable coverage, followed by manager controls
and a coherent versioned live qualification.


## Building roster observation checkpoint

The shared native_building_hirelings observer reads the entire owned building
slot list without a selected hireling or individual guard window. Selected-guard
upgrade observation now uses that same read set and adds its selection, menu,
price and control checks before a single consistency recheck. Type 37 eligibility
remains explicit; other populated types are retained without upgrade authority.
The crafting observer remains strict type 42. A fully observed positive slot
list can prove all slots vacant; zero capacity or an absent/partial list cannot.

Validation: 77 focused building/guard/vendor observation tests and targeted Ruff
pass. A bounded read-only in-memory execution against the user's already-open
Tower Junction verified its complete six-slot roster without selecting a guard.
No agent action, gold movement, runtime install or private roster export occurred.
This is current-building observation, not proof of town membership or coverage.
Next: durable guard building traversal and guard-window verification, warehouse
access, finite maximum-rank scheduling, manager integration and versioned live
qualification. Previously qualified manual transfers need not be repeated.


## Typed nearby guard discovery checkpoint

The guard_discovery runner now owns a complete navigation-only sequence: read
City Command's nearby candidate buildings, release the completed city session,
then use one navigation session to open each exact building and each type-37
hireling from its verified local slot list. City cache entries may contain type
37, type 42 or unknown nonzero types; they are candidates only. The vendor reader
and crafting path remain strict type 42. Guards are discovered from the building
list even when the city cache contains no hireling rows for that building.

The existing durable discovery/navigation engines are shared, with separate
guard-discovery and guard-navigation records and guard-nearby-summary.json under
the same instance execution lock. Intents precede every open. The candidate
record retains scene/root provenance across the city-to-building session handoff.
Scene changes, detached selection, changed rosters, missing responses, cancellation
and unresolved requests stop progression; a repeated operation never reopens.
Guard observations retain rank, current price, funds and progress for later fresh
admission. Discovery never sends spending or upgrade commands. Unavailable
buildings/guards produce partial candidate coverage; completion of the candidate
pass does not establish town membership or full-town coverage.

Validation: 361 focused Python tests pass, including the native wire fixtures,
existing vendor manager/navigation regressions, complete mixed/vacant rosters,
exact guard selection, sequential producer ownership, failure cleanup, scene
provenance and durable no-replay tests. Targeted Ruff and diff checks pass. No
native source changed in this checkpoint. Only the single already-open building
reader was live-qualified; automated traversal is source/fixture qualified only.
No runtime deployment, agent game action or gold movement occurred.

Current todos:
- Complete: owned building rosters and typed nearby guard discovery source.
- Active: warehouse parent-panel access and a durable funding/upgrade scheduler
  under exact worker ownership; preserve one producer through each completion.
- Pending: manager controls/progress, maximum-rank completion qualification,
  demonstrable town coverage, versioned deployment and live end-to-end validation.

Integration remains guard-upgrades -> vendor-rolling -> native-lifecycle-hardening
-> reviewed main. This feature lane remains outside main; review/integration and
live qualification are still required before claiming delivery of bulk upgrades.


## Hireling activation correction after warehouse navigation

The user opened warehouse building management. Read-only ownership checks found
one Seneschal row and a ready native navigation channel. One exact hireling-open
request was durably recorded in the guest's guard-qualification directory before
submission. The installed extension reported SUBMITTED but the selected row and
building snapshot remained unchanged; its correlated transition timed out and
latched IN_FLIGHT|UNRESOLVED. The host record is retained as review. No request
was repeated, reset or cleared, and no gold or upgrade action was sent.

Static inspection explains the failure: row handler RVA 0x61c6e0 with event 1
sets the selected control, then dispatches that event's action mapping. The live
row has empty mappings for both event 1 and event 0. Event 1 therefore only
selects; the activation handler at RVA 0x61c7f0 supplies the default 0x4ce action
only for event 0. The action getter at RVA 0x5ce080 indexes 36-byte descriptors
from control+0x1d0. Context label strings are at +0x144, whereas +0x164 names the
control; the game's persistent main context menu is not warehouse access.

Source navigation now uses the ordinary list selection setter RVA 0x613520
(list, exact_control), which only assigns list+0x404, then rechecks full owned
roster membership, selection and action mapping before ordinary event-zero
activation at RVA 0x61c7f0(control, 0). Only default or explicit 0x4ce activation
with zero numeric arguments is admitted; other mapped actions and hidden rows
are rejected. Funding's Gold-row selection remains selection-only, as intended.
This correction applies to both vendor and guard navigation.

Validation: full Win32 extension build, all 14 focused native suites and 361
focused Python tests pass. New native callback fixtures prove activation of an
already-selected row, selection followed by activation, type-37/type-42 dispatch,
and rejection of different actions, hidden controls, failed selection, detached
ownership and action changes before activation. The correction is not installed;
the current game's unresolved attempt must remain retained. No live retry is
appropriate in that process. A normal client restart during a coherent versioned
update will supply a new lifetime, without rewriting historical receipts.

Private evidence remains in the guest's guard-qualification/
warehouse-open-seneschal-20260917.json and host artifacts/guard-upgrades/
warehouse-context-20260917.png and warehouse-seneschal-result-20260917.png.
Those artifacts are not source deliverables and were not added to Git.
Next: inspect the Seneschal's own menu to identify resource-inventory access,
then finish warehouse traversal and funding/upgrade scheduling before deployment.


## Warehouse resource entry point and native access checkpoint

The user opened the Seneschal conversation's warehouse resources. A bounded
read-only observation verified exactly one rooted ArcWarehouseHud, its retained
NPC source key, owned Gold row and reserve map with no amount quote open. This
qualifies the parent panel independently of the previously qualified withdrawal.
No live action, gold movement or runtime installation occurred in this checkpoint.

Static inspection distinguishes the two paths: asset-management Inventory action
0x58c opens ItemManaging (or reports a non-goods hireling), not warehouse storage.
NPC dialogue leaf action 22 dispatches ordinary cdecl RVA 0x877770(actor, NPC).
That function borrows its NPC argument, checks the ordinary 20-unit predicate,
creates Warehouse, retains the source through 0x69c9f0/0x5d91a0, and requests its
resource inventory. No fabricated packet or management inventory click is used.

Native navigation now has a distinct warehouse verb 22. Admission requires the
exact type-42 row in the complete, currently owned building roster, online scene,
foreground window and producer lease. The retained world query matches the NPC
vtable and full world key at +0x18 (never the building key at +0x780). It releases
other results, calls the ordinary range predicate, repeats ownership/admission,
and invokes the ordinary opener while holding its own borrowed reference. Native
exceptions quarantine uncertain ownership. The controller confirms only an active
Warehouse HUD with the exact retained NPC source and expected building context;
a hireling-management window or unrelated warehouse cannot complete the request.
Gold inventory loading is separately required by the funding observer before use.

Navigation receipts are version 2 (magic WBN2); the embedded guard-navigation
snapshot requires guard receipts version 2 (WBG2) as well. Both host/native sides
must ship together. The fixed snapshot size remains 96 bytes, with its former
16 reserved bytes now carrying warehouse HUD, source object and full source key.
Legacy receipt formats are rejected. Existing request histories are not rewritten.
The host exposes open_warehouse, with no retry after a lost action response.

Validation: full Win32 DLL build, all 15 focused native suites (including retained
target ownership), 371 Python regressions, then 34 affected host/wire tests after
adding a nonzero warehouse cross-language fixture; targeted Ruff and diff checks
pass. Tests cover ordinary call arguments, borrowed reference release, range and
scene rejection, duplicate/wrong-type candidates, fault quarantine, exact HUD
source correlation, legacy receipt rejection, immutable responses and no replay.
Automatic warehouse opening remains source/fixture qualified, not live-qualified.
The installed client's earlier unresolved navigation remains retained unchanged.

Current todos:
- Complete: identify/live-observe warehouse parent resources; native/host access.
- Active: durable warehouse visits and the persistent funding/upgrade worker.
- Pending: maximum-rank completion, manager controls/progress, demonstrable town
  coverage, coherent versioned deployment and live end-to-end qualification.
Integration remains guard-upgrades -> vendor-rolling -> native-lifecycle-hardening
-> reviewed main. No build from this checkpoint is installed or merged into main.


## Unified guard navigation and spending journal

Guard navigation can now use the same GuardSpendingJournal as quote opening,
withdrawals, deposits and upgrades. Distinct navigate_building, navigate_guard
and navigate_warehouse operations retain exact command bytes, native host lease,
process lifetime and correlated receipts before advancing. Navigation commands
and receipts now have strict encode/decode round trips; the recorded operation
supplies the verb and validates both typed keys. Already-open, exactly correlated
navigation is a terminal no-op; an OBSERVED upgrade is never treated that way.
Lost replies, mismatched sources, scene/lease changes, pending flags and unresolved
responses keep the gate closed across worker/client restarts. No new request is
allowed to bypass the gate by choosing a different operation. UUIDs never replay.

The production guard-discovery factory now supplies this journal to navigation
and checks it before opening City Command. Vendor discovery keeps its existing
own durable records; the vendor job path is not migrated or resumed. The persistent
funding worker must use this same journal for every navigation session and retain
each producer until correlated completion before opening the next session.

Validation: 396 focused Python tests and targeted Ruff pass. New cases cover all
three navigation verbs, intent-before-dispatch, already-open completion, lost
replies across restarts, source/scene/lease/type mismatch, operation crossing,
command corruption and pending action rejection before city discovery. Native
source is unchanged from 54f2b57. No runtime was installed and no live game action
was sent. Next active todo: persistent warehouse-to-building funding and upgrade
sequencing, then manager controls, town coverage and versioned live qualification.


## Front-window readiness before funding

Sequence review found that navigation treated any owned visible HUD as already
open even when another panel was in front. Funding and guard actions correctly
require their HUD on top, so that no-op could strand a warehouse/building handoff.
Navigation now records the first owned HUD-stack member as front_hud, replacing
the unused last-dispatched-manager field. OwnsBuilding remains a separate parent
roster admission check, while successful building/hireling/warehouse navigation
requires the exact target HUD in front. An existing background window therefore
uses its ordinary opening path and waits for the actual front-window response.
No arbitrary focus message or OS-input helper was introduced.

This changes word 24 of the snapshot: navigation receipts are now WBN3 and guard
receipts WBG3. Host/native ship together; prior receipt meanings are rejected.
The fixed command/snapshot sizes are unchanged. Historical checkpoints above
record their then-current formats; version 3 is the current source contract.

Validation: full Win32 DLL build, all 15 focused native suites and 397 affected
Python tests pass. Cases include all four navigation verbs already present behind
another window, foreground correlation, parent-roster admission behind a hireling,
wrong-source warehouse responses and a journal that stays pending for a background
panel. No runtime update or live action occurred. Next remains the persistent
funding/upgrade sequence, manager integration and coherent live qualification.


## Durable warehouse-to-guard funding cycle

The manager now has a reusable run_guard_funding_cycle transaction for one
freshly quoted guard upgrade. Its immutable target includes the exact game
process lifetime, native scene/root, warehouse building/NPC and guard building/
hireling identities. It holds the existing instance execution lock and uses the
shared GuardSpendingJournal for every action. One producer stays alive through
its correlated completion; each closed session must leave the journal idle before
the next family claims the transport. Each factory handoff also checks PID lifetime
and HWND. Cycle IDs and native request IDs are retained and never replayed.

The cycle opens the exact guard, reads current rank/price/funds, and skips guards
already upgrading or without an eligible offer. Existing building funds avoid all
funding actions. Otherwise it visits the warehouse, honors the current resource
reserve, uses existing purse gold and withdraws only the shortfall. After the
withdrawal's two-sided receipt it opens the exact building, refreshes its balance,
deposits only its remaining shortfall, returns to the guard and rechecks rank,
price and eligibility before the upgrade. The final result requires the exact
upgrade debit and progress/rank receipt. Pre-existing amount windows are not
adopted. Confirmed withdrawals/deposits remain recorded if later phases stop.

A missing response, changed source/scene/character/price, lost worker or cancellation
stops later actions. A new cycle ID cannot bypass an unresolved shared action.
Insufficient gold is a clean result without partial funding; already-upgrading
and no-offer states are explicit, and no-offer is not a maximum-rank proof.
An already-front exact window needs only observation, avoiding unnecessary opens.
This permanent transaction boundary is intended for the town scheduler; it is not
yet wired to dashboard admission or an automatic maximum-rank loop.

Validation: 420 focused host tests passed before adding the final cross-cycle
no-bypass case; the complete funding-cycle suite and source checks are run again
for this checkpoint. Its integration fixture uses the real persistent journal and
wire codecs, simulates intermediate in-flight observations, and asserts only one
producer exists at a time. It covers existing gold, reserve exhaustion, every lost
phase response, cancellation after withdrawal, stale target lifetime, scene/HWND/
character changes, changed prices and exact balances. Native source is unchanged
from 51f41cd; no runtime update, live withdrawal/deposit or guard action occurred.

Current todos:
- Complete: native warehouse access, front-window navigation, unified action
  journal and the durable funding/upgrade transaction source.
- Active: town guard planning and scheduling using these transactions.
- Pending: manager controls/progress, maximum-rank completion qualification,
  demonstrable town coverage, coherent deployment and live end-to-end validation.
Integration remains guard-upgrades -> vendor-rolling -> native-lifecycle-hardening
-> reviewed main. Source/fixture validation does not imply installed acceptance.


## Persistent guard plans and rank scheduling

Funding cycle source checkpoint 087be51 is pushed. The next source slice adds
GuardUpgradePlan and GuardJobStore/run_guard_upgrade_job as the permanent queue
boundary. Plans derive type-37 guard keys from retained guard-discovery and
guard-navigation records, pin both file digests and the exact observed warehouse
snapshot, and require the same instance, PID creation, scene/root and complete
owned rosters. Duplicate display names never select a target. Inaccessible
buildings and unverified guard windows remain excluded coverage; loaded nearby
candidates still do not establish city membership or full-town coverage.

The queue records a fresh funding-cycle ID before calling its transaction, rotates
through admitted guards, and waits five minutes by default between rank checks
(one-minute minimum, configurable up to one hour). It holds a runner lock while
active, with native sessions opened only by individual cycles. Existing progress
waits; an unaffordable guard does not prevent checking another cheaper or already
funded guard. All confirmed withdrawals, deposits and upgrade debits are accounted
from the retained cycle file. After an accepted upgrade, its prior rank plus one
becomes the minimum required before any later funding/spending for that guard.
A disappearing progress bar without that rank increase stops for review.

A worker restart can reconcile a fully confirmed outstanding cycle exactly once;
accounting and clearing its active marker are one atomic record replacement.
Missing, partial, mismatched or unresolved cycles require review and cannot be
bypassed with a new job ID. Confirmed partial movements remain in the cycle and
shared journal even when the queue stops. Pause takes effect between transactions;
Stop/worker cancellation interrupts work, retaining uncertain actions for review.
No-offer and insufficient-gold results remain explicit; no state falsely claims
maximum rank or completion of all guards in town.

Validation uses persistent files plus the actual spending journal and wire codecs.
The queue suite covers source/lifetime/scene/roster changes, partial candidate
coverage, identical building/guard names, fair rank checks, unaffordable offers,
pause/resume/stop, recovery exactly once, unrecoverable interrupted cycles and lost
withdrawal replies. End-to-end fixture cases execute two real funding cycles over
rank increases and stop a second debit when the rank does not advance. Broader
host regression: all 452 affected tests pass; Ruff and the source diff check pass. Native source is
unchanged; no runtime install or live gold/upgrade action was performed.

Current todos (supersedes the previous active list):
- Complete: warehouse/navigation primitives, shared journal, funding transaction,
  exact discovered guard plans and persistent rank scheduling source.
- Active: manager worker admission, controls and progress for guard jobs.
- Pending: maximum-rank completion qualification, demonstrable town coverage,
  coherent host/native packaging/deployment and live end-to-end validation.

Integration remains codex/guard-upgrades -> codex/vendor-rolling ->
codex/native-lifecycle-hardening -> reviewed main. This lane is not merged or
installed. The normal main checkout and old vendor jobs remain untouched.


## Manager guard controls and worker integration

Queue checkpoint 2988ba3 is pushed. Guard work now has its own strict worker
operation family and worker capability, admitted through the existing exact
instance/permit/operation ledger. The manager dashboard exposes Find guards,
Upgrade verified guards, Pause, Resume and Stop with confirmed upgrade/gold
progress. Find guards first retains the exact open warehouse observation, closes
that producer, runs City Command and typed guard discovery, and publishes a
prepared selection without moving gold. Start requires the exact prepared
selection ID displayed in the dashboard, so a stale page cannot silently start a
newer plan. The worker rechecks PID creation, window and discovery provenance.

Pause/Stop remain instance/job-specific. An idle Stop is acknowledged under the
runner lock; an interrupted cycle is retained for review. Public cancellation
recognizes guard work and the exact worker routes guard commands directly to its
guard executor. Existing crafting jobs retain their own controls and records.
The dashboard explicitly labels nearby coverage and unverified maximum rank;
there is still no claim of full-city census or maximum-rank qualification.

Validation: 565 combined host tests passed with one existing platform-dependent
skip. This includes guard funding/queue tests, authenticated HTTP controls,
manager binding/status, strict operation serialization, stale selection and worker
rejection, idle stop, existing vendor behavior, movement, cancellation and worker
runtime suites. Ruff and diff checks passed. The dashboard asset is UTF-8; its
existing security-header and read-only polling tests pass.

A read-only VM process check confirmed the same sb.exe PID 9428 under the existing
vendor test client. It still carries the earlier unresolved navigation history;
no command, gold movement or upgrade was sent. Host/native remain installed at
0.3.18/1.8.9. Next active todo is a coherent versioned package, followed by restart
and live qualification. Town coverage and positive maximum-rank detection remain
unfinished. Do not reset or reuse old native requests or crafting journals.


## Versioned source for coherent packaging

Manager checkpoint 85a2215 is pushed. The packaging source is now host 0.3.19 and
full extension 1.8.10. It contains WBN3/WBG3 navigation/guard receipts and WBF1
funding receipts, and must replace host/native together after game closure.
The package builder now requires all six guard native/controller/channel suites
to execute exactly once and pass for both profiles, and checks that guard native
sources each have one runtime owner. The existing packaging workflow retains its
full Python/Ruff, Win32, real IPC, installed-wheel and image-binding gates.
Versioning is not a deployment or live acceptance claim. The existing 0.3.18/1.8.9
runtime and its unresolved PID 9428 navigation remain untouched.


## Verified 1.8.10 package staged

Exact source 25f607e is packaged and staged as full extension 1.8.10 / host 0.3.19.
The isolated source suite passed 2,671 tests with 19 skips; required native/IPC/
binding, installed-wheel and all six installed guard-wire comparisons passed.
Guest dry-run verification passed. The game remains on 1.8.9/0.3.18 and no game
commands or gold movement were sent. The user has been asked to close Shadowbane
for activation. See [package validation and next steps](guard-upgrades-1.8.10.md).

Current active todo: activate the verified package after confirmed game closure,
then qualify the live funding/guard sequence. Full-town coverage and positive
maximum-rank qualification remain pending. Do not rebuild a documentation-only tip.

## Activated 1.8.10 guard manager

The staged full extension 1.8.10 / host 0.3.19 update is now activated through the
existing shortcuts. Read-only loaded-artifact and process-lifetime checks passed;
the manager has a healthy worker and exposes the guard controls. Historical
journals were preserved. No game actions or gold movement were sent by activation.

Active todo: live funding/guard qualification after login. Positive maximum-rank
evidence, full-town coverage and review/integration remain pending. See the
[current handoff](guard-upgrades-1.8.10.md). Private activation/rollback evidence
remains in local task artifacts.

## Menu timing correction activated

Packaged source c1472a6 increases only the bounded navigation response window,
without resubmitting requests or weakening gold/upgrade confirmation. Full source,
required native and installed-package validation passed. The corrected full
extension 1.8.11 / host 0.3.20 is activated and verified through the existing
shortcuts. See the [current handoff](guard-upgrades-1.8.11.md).

Active todo: resume live funding qualification after login beside the Seneschal.
The retained unresolved menu request was not reset. No gold was moved. Full-town
coverage, positive maximum-rank evidence and review/integration remain pending.
