# Player-owned vendor rolling

## Delivery and integration

Branch: `codex/vendor-rolling`, based on
`codex/integrate-current-development@f2a5ca1`. The shared destination is
`main` after the integration dependency is reviewed. This source is not merged
or deployed. The main project checkout stays on `main`; development and local
evidence are in `.worktrees/vendor-rolling`.

The implemented slice is the strict, offline ITEMPRODUCTION observation decoder
and its CLI. Live rolling automation remains unfinished. There is no verified
WonderBane crafting native profile, dispatch adapter, complete queue reader,
or resource-budget controller in this delivery. Do not treat this decoder as a
live automation capability or register it as one.

## Verified upstream boundary

The reference is MagicBane Server revision
`7c3a3fb84c55c1efaa615f4ef2711173629a27c8`, not a claim that the running
WonderBane server uses that revision:

- [ItemProductionMsg](https://repo.magicbane.com/MagicBane/Server/src/commit/7c3a3fb84c55c1efaa615f4ef2711173629a27c8/src/engine/net/client/msg/ItemProductionMsg.java)
  defines request and response bodies.
- [ItemProductionMsgHandler](https://repo.magicbane.com/MagicBane/Server/src/commit/7c3a3fb84c55c1efaa615f4ef2711173629a27c8/src/engine/net/client/handlers/ItemProductionMsgHandler.java)
  maps produce requests to work orders, completes virtual items into inventory,
  and distinguishes junking a roll from recycling inventory.
- [ForgeManager](https://repo.magicbane.com/MagicBane/Server/src/commit/7c3a3fb84c55c1efaa615f4ef2711173629a27c8/src/engine/gameManager/ForgeManager.java)
  schedules batches and assigns random modifiers.
- [Protocol](https://repo.magicbane.com/MagicBane/Server/src/commit/7c3a3fb84c55c1efaa615f4ef2711173629a27c8/src/engine/net/Protocol.java),
  [mbEnums](https://repo.magicbane.com/MagicBane/Server/src/commit/7c3a3fb84c55c1efaa615f4ef2711173629a27c8/src/engine/mbEnums.java),
  and [ByteBufferUtils](https://repo.magicbane.com/MagicBane/Server/src/commit/7c3a3fb84c55c1efaa615f4ef2711173629a27c8/src/engine/util/ByteBufferUtils.java)
  establish opcode, action ordinals, and UTF-16BE strings.

ITEMPRODUCTION is `0x3CCE8E30`. PRODUCE (1), JUNK (2), COMPLETE (4),
and server CONFIRM_PRODUCE (8) are decoded. Requests and replies use different
grammars, so direction is mandatory. Other actions fail closed rather than being
misinterpreted as a roll. MANAGENPC (`0x43A273FA`) remains a separate queue and
inventory snapshot boundary that still needs decoding.

A produce request carries a template ID, quantity, prefix and suffix tokens,
name, and slot mode. Zero modifier tokens request random generation where the
vendor's modification tables support it. Slot mode can multiply quantity;
automation must not assume the requested count equals the final work-order size.
The upstream forge already supports batches and may persist intermediate
batches automatically. A stop-on-match policy should start with one item in one
slot until those semantics are verified on WonderBane.

CONFIRM_PRODUCE also describes cooking items. Zero hidden modifier tokens do not
mean a completed item has no modifiers. The completion flags and remaining time
are independent fields. Item IDs preserve their unsigned wire bits because
virtual IDs can be negative Java ints; a template ID cannot identify a rolled
item for a keep/junk action. COMPLETE persists an item into vendor inventory,
and confirmation requires observing that inventory transition.

## Use the observation hook

`shadowbane_lab.client_observation.crafting_wire.parse_crafting_wire` accepts
one complete plaintext message including its big-endian opcode. It returns an
immutable `CraftingMessage`; `to_dict()` includes the source revision, direction,
building/vendor references, fields, and payload digest. It does not take TCP
segments, encrypted packets, native object memory, or a queue snapshot.

For a binary capture already extracted at the plaintext boundary:

```powershell
$env:PYTHONPATH = "src"
python -m shadowbane_lab.cli client decode-crafting .\artifacts\roll.bin --direction server_to_client --json
```

Input is bounded to 64 KiB. Truncation, oversized names, unsupported direction/
action combinations, contradictory completion flags, and trailing data fail
closed. Opaque fields are preserved without inventing their meaning. Synthetic
tests prove the upstream grammar only; no live capture has been promoted.

## Remaining implementation

1. **Active: verify a manual roll on shadowbane-testing.** Bind the process
   lifetime and executable hash; capture opening management, requesting one
   random roll, cooking, completion, and keeping the item. Identify the native
   crafting message and dispatch functions through signatures and call paths.
   Existing ArcMerchantMessage vendor-dialog breakpoints cannot capture this
   different message class simply by changing an opcode.
2. Add the verified native observation path and complete MANAGENPC queue/
   inventory snapshots. Keep callbacks bounded; publish immutable events through
   the extension event channel. Bind observations to process lifetime, vendor,
   item, sequence, and capture time, with explicit gaps and reconnect handling.
3. Add typed crafting commands through the existing manager admission and native
   action boundaries. Recheck vendor access, identity, fresh queue capacity,
   inventory capacity, and gold/material limits immediately before dispatch.
   Observe server acceptance separately from local send success.
4. Add durable rolling jobs with recipe, count/resource limits, desired modifier
   rules, and explicit reject handling. Start/pause/stop belong to the manager.
   Persist job ownership and pending actions before dispatch; never blindly retry
   an uncertain produce or destructive action after timeout/restart. Reconcile
   through a fresh authoritative snapshot before resuming.
5. Validate one request through completion and keep, then bounded repeated rolls,
   budget exhaustion, full slots/inventory, rejection, disconnect/restart,
   duplicate/missing events, cancellation, and wrong-client/vendor isolation.
   Default to retaining items; junk/recycle require explicit policy.

Local research files and VM screenshots are under
`artifacts/vendor-protocol/` in the task worktree and are ignored. They are not
client packages and must not be shipped. On September 13 the selected test VM was
powered off; it was started headlessly and was applying Windows updates.
The computer-use runtime failed with `apply deny-read ACLs`; VirtualBox
screenshot inspection remained available. No crafting input has been sent.
