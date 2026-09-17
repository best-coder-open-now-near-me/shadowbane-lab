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
qualified; automatic transfer commands and durable receipts remain unfinished. Do not claim that a button's availability establishes enough money.

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
- [ ] Active: implement automatic warehouse withdrawal/structure deposit and
  durable host receipts with character/scene ownership.
- [ ] Qualify automatic navigation across guard structures and other guard types.
- [ ] Connect durable per-guard host receipts and the maximum-rank scheduler
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
