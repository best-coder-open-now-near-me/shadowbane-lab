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

## WOW64 debugger correction and verification

The timing-call positive control ended with client PID 6016 exiting. Windows
Application Error recorded exception 0x4000001E in kernel32.dll. This is the
WOW64 single-step status; the backend handled only the native 0x80000004 status
and passed the WOW64 event to the application as unhandled. This establishes a
debugger defect consistent with that exit, but does not establish the cause of
the earlier unconfirmed keep transaction.

The backend now routes both native and WOW64 single-step events through owned
hardware-breakpoint detection, and recognizes both attach breakpoint statuses.
Unowned steps and unrelated application exceptions remain unhandled. Reference:
[Microsoft DbgShell exception constants](https://github.com/microsoft/DbgShell/blob/master/DbgProvider/public/Debugger/DbgExceptionEventFilter.cs).

A disposable x86 C# process on shadowbane-testing verified the corrected backend:
PID 9984, eight events across four kernel32 functions, successful continuation and
detach, then normal exit code 0 with PROBE_COMPLETED. No game interaction was
used for this verification. The source, executable, and runner are private in
artifacts/vendor-protocol/; executable and runner plus the corrected backend were
staged in diagnostics/vendor-rolling-20260914/. The shared test checkout was
not changed. All 31 focused tests and whole-tree Ruff pass.

Remaining acceptance: recover/inspect the current game session, reconcile the
unconfirmed keep against vendor inventory, capture a complete crafting message
exchange, then implement and qualify bounded rolling admission and results.
Automated production and stop-on-match remain unfinished and are not enabled.

The same reviewed test client was reopened as PID 988, creation FILETIME
134338345902905271. The corrected observer completed its 300-second window
without a crafting message or incomplete invocation and detached cleanly. No
additional game input was issued. Treehugger was visible near the city tree;
returning to the sages and reconciling inventory remain the active live step.
The private journal is C:/Users/tester/native-crafting-fixed-20260914.jsonl.
Automatic approval review rejected a proposed guest-to-host journal copy,
citing credential use and potentially sensitive log contents. No copy was
performed, and the workflow continued with the observer's live output.

Further source inspection of
[ManageNPCMsg](https://repo.magicbane.com/MagicBane/Server/src/commit/7c3a3fb84c55c1efaa615f4ef2711173629a27c8/src/engine/net/client/msg/ManageNPCMsg.java)
confirms distinct recipe, cooking-item, modifier-table, and inventory lists.
Inventory entries delegate to Item.serializeForClientMsgWithoutSlot, so a
complete inventory decoder must own that nested grammar. Native management
class mapping is unresolved: ArcOrderNPCMessage belongs to the separate
ORDERNPC family and must not be relabeled MANAGENPC based on its name.

## First live crafting breakpoint hit

With Malik's menu open, the user was asked to create one random Gilded Scepter
(quantity one, Create Item). A new Gilded Scepter appeared in production with a
20-minute timer. The native trace reached a paired crafting entry/completion,
then rejected a zero-length read while decoding the message name. The object's
string buffer was allocated but empty (begin equals end), a valid client state
not covered by the original null-buffer case. The hit resumed and the debugger
detached; no decoded payload or server acceptance record was emitted.

The decoder now validates that buffer's bounds and returns an empty string
without issuing a zero-byte process-memory read. A regression runs the full
capture/callback/resume path with both retained capacity and zero capacity.
Seventeen crafting tests pass; whole-tree Ruff passes. The corrected observer
was reattached to PID 988 using a fresh guest journal
C:/Users/tester/native-crafting-completion-20260914.jsonl. No second production
request was made. Next: reconcile the old scepter in inventory and decode the
new roll's result. The initial produce payload remains unverified.

## Native observation schema 2

Live qualification exposed a native/wire layout difference: ArcCacheID stores
ID before type in memory, while the wire pair is type then ID. Schema 2 corrects
the native object-reference labels. Schema-1 captures must not be used for command
admission. The roll's template ID and remaining count are now separate fields
instead of a misleading template object reference.

The common scalar fields are named quantity_raw and production_marker_raw.
A zero raw count can represent a single-slot request; ForgeManager normalizes it
to one. Consumers must not treat the raw value as the accepted job count.

The observer has now exercised JUNK, PRODUCE, and cooking CONFIRM_PRODUCE.
Eighteen crafting tests and whole-tree Ruff pass. Completion observation,
inventory reconciliation, and an admitted production dispatcher remain open.
Automatic approval review initially blocked reattachment using the test VM's
provisioned credentials. The user subsequently approved that access and the
source push; both operations succeeded.
Raw captures remain private. This checkpoint changes only source, synthetic
regression coverage, and these implementation notes.

## Completion and keep acceptance

After approval, the schema-2 observer reattached successfully and the source
checkpoint was pushed. It observed completed CONFIRM_PRODUCE messages for the
same virtual items previously seen cooking, with final modifier tokens, zero
remaining time, and complete flags. A separate nearby vendor also generated a
completion, confirming that subscribers must filter building and vendor identity.

A user-triggered COMPLETE request was followed by CONFIRM_SETPRICE and
CONFIRM_DEPOSIT. Visual inspection then confirmed the kept scepter in the
selected vendor's inventory and an empty production slot. This verifies the
manual keep workflow; the current decoder does not yet decode the nested
inventory item in CONFIRM_DEPOSIT, so that reply alone is insufficient for
automated inventory reconciliation.

Observed lifecycle coverage now includes produce, cooking, completion, junk,
and keep/deposit replies. No automatic command dispatcher is enabled. The
user's testing included actions at both sages; the kept item was distinct from
the two newest production IDs, so those captures must not be presented as one
continuous single-item produce-through-keep sequence.

Read-only native inspection identified these additional candidate RVAs:
message constructor 0x3F9080, UI produce builder 0x6D7590, UI keep builder
0x6D7080, and UI junk builder 0x6D6EB0. The produce builder takes two stack
arguments and reads recipe/count/vendor state from its receiver. These are
static candidates, not an approved callable profile. Next is qualifying that
receiver and call contract, completing queue/inventory observations, and adding
typed command admission before a bounded rolling job may invoke production.

## Send-path qualification follow-up

A final manual Create was captured at the crafting serializer with the expected
random-recipe request. The candidate UI produce entry at RVA 0x6D7590 was not
hit. Its receiver and call contract therefore remain unqualified for this
Create-button workflow. Further static inspection found another recipe builder
at RVA 0x63CE40 that reads the creation HUD's selected item, modifiers, count,
and slot mode, then forwards to its owner. Neither candidate is enabled for
dispatch; the next call-path capture should include bounded caller-stack context
at the serializer to avoid inferring the active builder from static xrefs alone.

At the end of this exploratory trace, DebugActiveProcessStop returned Windows
error 5 (Access is denied). A subsequent read-only CheckRemoteDebuggerPresent
succeeded and reported false; the same process lifetime remained visible and
foreground. No debugger remained attached and no automated game action was
issued. Keep this diagnostic outcome explicit rather than claiming every trace
detached without an error.

The source branch is an observation-hook checkpoint. Remaining work is the
qualified native send adapter, complete inventory/queue decoding, and bounded
rolling jobs with keep rules and resource limits. Raw diagnostic artifacts remain
in their private local/VM locations and are excluded from the source push.
