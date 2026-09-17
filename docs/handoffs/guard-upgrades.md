# Guard upgrades

Source branch: `codex/guard-upgrades`, isolated worktree `.worktrees/guard-upgrades`.
Base: vendor branch `61e6fd8`, after fetching origin and verifying the documented
integration branch is an ancestor. Guard changes should be reviewed into
`codex/vendor-rolling`, then `codex/native-lifecycle-hardening`, followed by `main`.
No vendor source was changed or deployed by this detour. No guard upgrade has
been sent by the agent. Town automation remains unfinished.

## User policy

Upgrade all guards toward maximum rank, as far as available gold permits. Read
current costs and funds for each request; avoid already-upgrading or maximum-rank
guards. Do not infer a shared town balance from one building's funds or assume
all guard types use the same cost. The user identified warehouse gold as the funding source after confirming the
structure has no upgrade funds. Warehouse withdrawal and structure deposits
are now required parts of the feature; their limits and outcomes still need
qualification. Do not claim that a button's availability establishes enough money.

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
  string RVA 0x1348c80. Its handler, request/response and timer acceptance
  still need qualification; no raw native request or force-upgrade path is used.

## Validation and current todos

- [x] Read the exact live executable and open guard menu without game writes.
- [x] Implement a reusable, read-only guard observer and CLI command.
- [x] Verify live guard identity, complete building rows, rank, cost and flags.
- [x] Pass 68 focused guard/vendor roster/queue tests; preserve vendor rejection
  of guard types and CLI handle cleanup on success/failure.
- [ ] Active: qualify warehouse withdrawal limits and structure deposits, then
  observe one normal upgrade's confirmation and server outcome. The user has
  opened the warehouse and has been asked to leave the withdrawal amount prompt
  open without confirming. The earlier unfunded upgrade request is superseded.
- [ ] Qualify automatic navigation across guard structures and other guard types.
- [ ] Implement typed upgrade commands, durable per-guard receipts, no-replay
  handling, funding checks and a maximum-rank scheduler with finite work per pass.
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
