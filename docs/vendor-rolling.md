# Player-owned vendor rolling

## Delivery and integration

Branch: `codex/vendor-rolling`, based on
`codex/integrate-current-development@f2a5ca1`. The shared destination is
`main` after the integration dependency is reviewed. This source is not merged
or deployed. The main project checkout stays on `main`; development and local
evidence are in `.worktrees/vendor-rolling`.

The implementation includes the strict offline ITEMPRODUCTION decoder and a
bounded native crafting tracer with a post-resume observation callback. Live
rolling automation remains unfinished. The native capture path is still under
live qualification; there is no verified dispatch adapter, complete queue reader,
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

## Native discovery checkpoint

Read-only inspection of the local test baseline
`client-baseline-sources/wonderbane-20260831T023921516Z-55fb/sb.exe`
under the test VM diagnostics share found the following. Its SHA-256 is
`55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc`;
this does not establish which executable a future live process will use.

| Static evidence | RVA (image base 0x400000) |
| --- | --- |
| ArcItemProductionMessage RTTI type descriptor | 0x13066E8 |
| Complete object locator | 0x11A9598 |
| Class vtable | 0x115BFD8 |
| Candidate stream reader (vtable index 7, via jump thunk) | 0x3FA240 |
| Candidate stream writer (vtable index 8, via jump thunk) | 0x3FA6C0 |

The reader begins `558bec6aff68073bd70064a100000000`; the writer begins
`558bec6aff68383bd70064a100000000`. Disassembly shows the former reading from
a stream into object fields and the latter writing those fields into a stream.
Both access the leading action field at object offset 0x70, followed by compound
fields at 0x78, 0x80, and 0x88. Their meanings, object extent, completion sites,
stream representation, and command admission are **not yet verified**. These
are discovery locations, not a loadable native profile or permission to call
them. No pointer or ABI inferred here is exposed for live dispatch.

The VM subsequently completed boot and reached the Windows desktop. It remains
running headlessly. Live verification now awaits the test character, vendor,
and item selection, plus a working guest control path. No game interaction was
performed.

Validation at the decoder checkpoint: 19 focused unittest tests pass (crafting,
vendor wire, native vendor-dialog regressions), whole-tree Ruff passes, and
`git diff --check` passes. The local environment has no pytest module; the
equivalent focused unittest suite was run directly. CI's broader matrix and
live crafting acceptance are not claimed.


## Native capture API and September 14 test

`NativeCraftingTracer.trace` uses the existing hardware debugger backend, requires
an inspected executable hash plus all four instruction signatures, pairs nested
entry/completion events per thread, and reads only a bounded message object and
name. Every hit resumes in a finally block; consumers receive copied observations
after resume. Closing the trace detaches on success, timeout, or error. A quiet
trace and incomplete invocations remain explicit and do not certify live behavior.
The callback is an observation extension point; it supplies no dispatch authority.

```powershell
python -m shadowbane_lab.cli client trace-native-crafting --process-id 6016 --output .\artifacts\crafting.jsonl --timeout-seconds 120 --json
```

Use the current process ID; 6016 belongs only to this recorded session. Existing
evidence files are never overwritten. Timeout is capped at five minutes and the
default message limit is 32. No process is selected implicitly.

The user prepared Treehugger in City of Root, with Malik the Irekei Sage and
So'skath the Lizardman Sage in the Feudal Magic Shop. Two random Gilded Scepters
finished as Taripontor Gilded Scepter of Cruelty and Gilded Scepter of Potential.
The observed client was the 1.8.1 test package, PID 6016, creation FILETIME
134338323268126976, executable hash bb63469e... (full hash in the supported set).

The desktop tool still failed to start, but guest diagnostics and the existing
GuardedInputExecutor worked. One COMPLETE click on the Cruelty scepter opened a
confirmation; Yes keeps the item, No junks it, and Cancel dismisses the dialog.
A single guarded Yes click closed the dialog. The item remained listed and no
crafting stream messages were observed at the candidate breakpoints. This is an
**unconfirmed transaction**, not a successful keep. Do not blindly retry it.
Reconcile the vendor inventory and qualify the actual dispatch path first.

The input preconditions pinned PID, creation FILETIME, HWND 196744, exact
1920x955 client bounds, foreground ownership, and a fresh comparison of the
observed item/confirmation image. The existing live-input and emergency-stop
guards remained active. No junk action or new roll request was sent.

Local captures and runners are in the task worktree's
`artifacts/vendor-protocol/`. The staged diagnostic observer and reference images
are in the test diagnostics share's `vendor-rolling-20260914/`; guest journals are
under `C:/Users/tester/native-crafting-*-20260914.jsonl`. These are private
diagnostics, not installed client binaries or shared source.
