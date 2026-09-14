# Player-owned vendor rolling

## Delivery and integration

Branch: `codex/vendor-rolling`, developed in
`.worktrees/vendor-rolling`. The original base was
`codex/integrate-current-development@f2a5ca1`; the September 14 dependency
merge includes `codex/native-lifecycle-hardening@542c632`.
Review this vendor overlay against `codex/native-lifecycle-hardening`, then
integrate into `main` after dependency and feature review. Neither the vendor
overlay nor this dependency merge is a deployment. The normal checkout stays
on `main`.

Implemented: typed native vendor inspect/Create/Keep commands, current-menu and
recipe ownership checks, durable capacity-aware queue filling, strict crafting
and inventory decoding, bounded passive tracing and conservative affix assessment.
The first automatic batch in 1.8.2 filled all three observed free slots; each
Create produced a separately correlated queue addition, and an independent
read confirmed all three items cooking. The completed batch was subsequently
finalized by automatic Keep; all three items were independently confirmed in
the owned inventory. No automatic Junk has run.
The complete rolling system remains unfinished: manager job controls, full
inventory/resource capacity and destructive-action qualification
are pending. Unknown affixes remain protected by the exclusion policy.

The dependency provides current native UI-thread, process/session lifetime and
typed command ownership infrastructure. Its movement authority does not grant
permission to craft or discard items. Vendor commands need their own typed
admission and receipts.

### September 14 dependency validation

Source checkpoint before merge: `6093942`. Native source is unchanged from
dependency `542c632`. Win32 Release compilation succeeded. Of 144 default
CTest cases, 139 passed, three fixture-dependent cases skipped, and two inherited
transparency diagnostics failed:
`wonderbane_extension_selected_cue_native_transparency` and
`wonderbane_extension_effects_native_transparency`. These failures remain
open; this is not a fully passing native suite. The three skipped binding/image
cases subsequently passed with the reviewed private original and prepared client
fixtures. All 72 focused vendor, crafting, inventory, debug-event, affix and
policy Python tests passed; whole-tree Ruff and staged whitespace checks passed.
Build output and fixture binaries remain private ignored artifacts.

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

1. **Complete:** selected vendor/recipe ownership, native typed inspection and
   automatic Create. The first live capacity-aware batch filled three slots;
   native correlation and an independent queue read confirmed each addition.
2. **Complete for the bounded batch:** persist ownership and each request before
   sending, prevent replay after interruption, detect rank growth, and stop when
   full or when outcomes/ownership become uncertain. This does not enable an
   unlimited sequence of replacement batches.
3. **Complete for this batch:** automatic Keep, preserving unresolved affixes.
   Each request was persisted before submission and matched native inventory
   confirmation. An independent owned-inventory read found all three items and
   all production slots empty. Qualified capture evidence is assessed when
   available; missing evidence remains unknown. Known low-tier identity coverage
   and live discard qualification are still incomplete.
4. **Complete in host source:** manager start/pause/resume/stop controls for one
   capacity batch, exact worker capability admission, cooking/inventory progress,
   stale-job rejection and durable phase recovery.
5. **Active:** package and qualify the manager integration. Then qualify native
   window opening, inventory capacity/paging, resources, full affix evidence and
   disposal before enabling recurring jobs. Never blindly retry pending actions.


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


## Bounded caller evidence and creation HUD

The native tracer now accepts `capture_callers=True` (CLI `--capture-callers`).
It pairs entry-time return-address candidates with each completed message,
including nested calls and interleaved threads. Reads stop at 16 addresses,
malformed or non-increasing frame pointers, unreadable memory, or a 1 MiB stack
window. No stack arguments are journaled. These are diagnostic candidates,
not a verified unwind or dispatch permission; optimized frames may be absent.
Callbacks still run after the client resumes. Thirty-one focused crafting and
debugger tests pass, and whole-tree Ruff passes.

Opening the actual recipe form identified one live ArcItemCreationHud with
vtable RVA 0x116BF7C. Its selected vendor, random modifier sentinels, modification
table, quantity one, and single-slot flag agree with the user's Gilded Scepter
selection. Static inspection resolves its owner forwarder to RVA 0x6D3240,
which sets PRODUCE and the building reference before queueing the message.
The next live qualification must associate the Create entry, this receiver,
outgoing request, and server reply. No native send adapter is enabled yet.


## Verified Create call path

A single user-triggered Create hit the ArcItemCreationHud builder at RVA
0x63CE40. The captured receiver carried the selected vendor, building, recipe,
random modifier sentinels, quantity one, and single-slot mode. Serialization
produced the matching PRODUCE request and the server returned CONFIRM_PRODUCE
with a new cooking item. UI creation and outbound serialization ran on different
threads; a command adapter must execute through the owning UI-thread boundary.

Explicit detach again returned Windows error 5. The subsequent debugger check
succeeded and reported no attached debugger; the same process lifetime remained
alive. No automatic crafting command was issued.

## Reference import and exclusion policy

The user supplied WonderBane_Field_Reference_v3_7_Zone_Resources.html and selected
an exclusion policy: exclude confirmed Tier 1 and Tier 2 results; retain everything
else, including unknown results. Unknown affixes override exclusion, even when
paired with a known low-tier affix. Unfinished items receive WAIT.

The affix table is packaged in equipment/data/wonderbane_affix_reference_v3_7.json,
with the original file hash, edition, source links, equipment categories, vendor
restrictions, formula costs, and evidence notes. Executable HTML and other
reference sections are not imported. equipment.affix_reference provides the
reproducible importer, bundled loader, tier queries, and exact name lookup.

The table contains 112 Tier 3, 50 Tier 4, and nine Tier 2 rows. It contains no
Tier 1 rows. Generic source categories such as "Weapons (source category)" remain
unexpanded. Names are not unique across tiers: "of Thorns" has different Tier 3
and Tier 4 effects and equipment restrictions. Lookup returns both records.

equipment.rolling_policy.evaluate_roll_tiers implements the selected policy.
Inputs must be confirmed tiers; None is unknown and zero means confirmed absent.
It returns WAIT, KEEP, or EXCLUDE without sending input or discarding items.
Missing reference entries remain unknown; this list is not a complete tier map.
Live effect tokens must be mapped before any result can be excluded automatically.

Next: verified modifier-token mapping, complete inventory/queue reconciliation,
typed UI-thread dispatch, and a bounded rolling job with an explicit run limit.
No automated crafting or disposal has been enabled.


## Kept-item identity and effect records

The observer now decodes bounded InstanceInfo content from CONFIRM_DEPOSIT:
template/item references, name, optional durability, raw item count, values,
and at most 64 effect records. Effects retain their token, train count, and source
type; no prefix/suffix role or tier is inferred from the list. Missing optional
item data is distinct from an empty effects list. Unknown/invalid pointers,
identity types, strings, and collection bounds fail before the callback.

In live testing, an earlier user discard consumed one of the trace's three
message slots. The observer captured COMPLETE and CONFIRM_SETPRICE for the new
scepter but ended before CONFIRM_DEPOSIT. Do not claim deposit-reply qualification
from this capture. A subsequent read-only scan found the same item identity in
InstanceInfo, with the user-visible Gilded Scepter of Genius, and also the older
Taripontor Gilded Scepter of Cruelty shown in the vendor inventory. The game
process lifetime was unchanged despite the reported logout/relogin.

The live non-stackable items reported zero in the count field, so it is exposed
as quantity_raw rather than being treated as an inventory count of zero.
Matching a heap instance alone is not ownership proof; a production reconciler
must bind it to the active vendor inventory and current game session.

The token reader at RVA 0x14C720 directly reads a 32-bit stream token.
The upstream hash of human-facing catalog names did not match the live effect
records; this does not establish a native token conversion. Mapping must use the
actual effect-definition keys, not guessed capitalization or display names.
Unknown effect identities continue to produce KEEP under the user's policy.


## Verified parent-affix identities and automatic assessment

Read-only inspection located live parent action definitions with canonical IDs
SUF-123, SUF-143, and PRE-028. Combined with the kept items' inventory labels,
these map respectively to of Genius, of Cruelty, and Taripontor on the tested
Gilded Scepter recipe and exact patched executable. Child effects such as
SUF-123A/B and PRE-028A/B are separate components, not extra rolled affixes.
The narrow compact-ID hash is covered by native parent/component test vectors
and pinned to [Hasher.SBStringHash](https://repo.magicbane.com/MagicBane/Server/src/commit/7c3a3fb84c55c1efaa615f4ef2711173629a27c8/src/engine/util/Hasher.java).

The native tracer now adds roll_assessment after resuming the game and before
journaling/delivering the callback. A completed SUF-123 result resolves to
Tier 3 through the imported reference. Cruelty and Taripontor remain unknown
because the reference does not assign them tiers. Unknown builds, recipes,
tokens, component IDs in parent positions, and ambiguous names do not inherit
qualification. Cooking, failed, or conflicting completion states return WAIT;
hidden zero tokens are not classified as absent affixes until completion.

The assessment is observational: command_admitted is always false. It does not
prove current inventory ownership, current login/session identity, remaining
slots, affordability, or permission to send a subsequent request. The tested
game retains its PID and process-creation identity across logout/relogin, so
process lifetime alone cannot guard a rolling job.

Validation: 55 focused equipment, policy, inventory, crafting, and debugger
tests pass. Next remains the active task: a vendor/session-bound queue reader
and UI-thread command adapter, followed by bounded rolling jobs. No crafting or
item-disposal command has been enabled by this checkpoint.


## Current-menu production queue reader

The active ArcWindowGame owns its city manager at +0xA4 (constructor assignment
RVA 0x7949F3). The manager owns the open management HUD at +0x78, and that HUD
refers back through +0x104. The reader also requires the HUD to be present in the
current native window's bounded HUD list. It then traverses the HUD child vector,
the production list box's owned controls, and their ArcProductionEntry payloads,
checking both the menu and list back-pointers.

This replaces heap discovery for production slot observations. During the live
check, two city-manager instances existed with the same building identity; the
older detached manager retained an earlier item identity. The reader followed
only the current native window and returned the two empty production slots shown
in the user's open management menu. The repair-service row was excluded from
the slot list. The nonempty slot layout is statically inspected and covered by
synthetic tests; cooking/completed slot reads still need live qualification.

Use the normal client command on the target machine:

    shadowbane-lab client observe-native-vendor-queue --process-id PID --json

read_native_vendor_queue accepts the existing WindowsReadOnlyProcessMemory
interface, does not attach a debugger, and does not scan the heap. All pointer
collections are bounded. Duplicate, broken, missing, changed or ambiguous
ownership fails instead of returning an empty queue. A reverse verification
pass rechecks every copied block, including the root and collection contents.
The command closes its process handle on both success and failure.

This external observation is not an atomic command lease, a login epoch, or a
guarantee against same-address object reuse. It does not identify the sage from
the building ID or infer that an empty displayed slot grants permission to
produce. Vendor/recipe binding, native UI-thread admission, inventory ownership
and bounded rolling jobs remain unfinished. No automatic crafting/disposal is
enabled. Validation: 66 focused tests, CLI help and whole-tree Ruff.

Delivery remains on codex/vendor-rolling, outside main. The next integration
step is review with the current native lifecycle source before enabling a native
command adapter; the normal main checkout and the other task's native worktree
are unchanged. Private scratch stays in artifacts/vendor-protocol and the
existing test-VM diagnostics directory.


## Recipe bound to the current queue

Queue schema 2 includes creation_recipe, read from the current native window's
active HUD list in the same read/verification pass as the production slots.
The creation HUD must refer to that window's current city manager. The selected
ArcItem must have the verified native type and a nonzero template reference.
The snapshot copies vendor, template, modifier selections, quantity and slot
mode. A qualified random Gilded Scepter selection requires template 26990,
modification table 12, mode 1, quantity one, single-slot mode, and the exact
3362971591 random sentinel in both modifier selections. This qualifies the
selection, not command authority or the availability of a production slot.

The live check found Malik (2517204/type42), the selected random scepter, and
two empty slots under the current window/manager/menu. A subsequent user Create
changed one owned slot to cooking item 4294925624/type40 while the other stayed
empty. The selected creation HUD remained present. The native duration/elapsed
fields were 1050/526, with the elapsed double advancing; a new cooking job does
not necessarily begin at elapsed zero. No crafting command was sent by the
observer. This qualifies the cooking slot layout; completion and inventory
ownership still need reconciliation.

The PID and process creation value stayed unchanged while the native window,
city manager and management HUD differed from the previous session. Neither a
process lifetime nor a previously observed recipe grants permission in a later
window/manager lifetime. Missing selection returns no qualified recipe; changed,
foreign-owner, malformed or multiple active recipe windows fail closed.
Validation now includes recipe/vendor changes during reads and active-list
membership. Next: the native UI-thread command path and bounded job controller;
the existing in-progress item can support completion verification.

## Selected vendor ownership — September 14

Queue snapshot schema 3 now follows the current ArcCityAssetManager's selected
ArcHirelingEntry at +0x384, checks vtable RVA 0x1169518, and reads its identity
at +0x10. The Keep builder's code at RVA 0x6D7127 passes this record to getter
RVA 0x567F90. The current test menu independently resolved Malik (2517204/type42)
through that link. An open recipe must name the same vendor. Management mode
must be zero, and the building fields consumed separately by Create (+0xF0)
and Keep (+0xF8) must agree. All links join the existing read consistency checks.

The manual roll 4294925624/type40 was observed cooking and then complete in
the same owned queue, with one other empty slot. Completion had zero timers,
complete/active/modified flags set, and stable item identity. This is a live
menu observation, not authoritative server inventory reconciliation or native
command admission. An external consistency check cannot prevent object reuse
or prove that asynchronous menu contents have finished updating.

The bounded Keep callpath observer expired twice without a matching call,
send, or deposit and detached normally. The item remained complete at the
last read. Computer Use initialization and its single retry failed before any
input (Node kernel exited; Windows sandbox deny-read ACL setup failed).
No Keep or discard action was issued by the agent. The next live step is an
armed Keep followed by current-vendor inventory confirmation.

Validation: 75 focused Python tests pass, including 20 queue/recipe/vendor
ownership tests. Missing or foreign hirelings, recipe/vendor mismatch, changed
selection, mismatched building fields and mode changes reject the observation.
The live schema-3 reader returned Malik and the completed roll successfully.
The existing native transparency failures recorded above remain unchanged.

## Keep and owned inventory qualification - September 14

The final armed observer captured all three required events for the manually
kept Gilded Scepter: native Keep entry, outbound COMPLETE (4), and successful
CONFIRM_DEPOSIT (10), following action 9. It detached normally. Keep is VA
0xAD7080 (RVA 0x6D7080), signature 558bec6aff68bba9db00, a thiscall on the
current ArcCityAssetManager with the 8-byte item ID/type by value and ret 8.
The observed owning UI thread was 5760; serialization/receive happened on other
threads. The receiver, selected hireling, building and item matched the rooted
menu. This qualifies the manual call, not an admitted automatic invocation.

The current inventory was then read through manager +0x7C -> active
ArcItemManagingHud (vtable RVA 0x116C64C). HUD +0x104 and +0x3F4 point back to
the current manager; +0x3F0 is the child-owned list. HUD setup at RVA 0x646500
assigns the list and RVA 0x646544 assigns the manager interface. Each list
control owns an ArcItemManagingEntry (vtable RVA 0x11696C8), whose item ID/type
at +0x10 must agree with InstanceInfo +0x20 and ArcItem +0x24. Template IDs
must also agree. These are ownership links, not heap-scan candidates.

Queue snapshot schema 4 includes this optional inventory view and decoded item
effects, using the same read-consistency set as vendor and queue ownership.
The received scepter was found with matching template, item, durability, value,
and effects; both production slots were empty. Previously kept Genius and
Cruelty scepters were also present. The view explicitly reports displayed entries,
unknown capacity, and incomplete inventory coverage. Closing the inventory
returns unavailable, not an empty list. A shared item between production and
inventory, inconsistent IDs, duplicates, changed backing data, or broken owners
reject the snapshot. No game input, disposal, or new roll was issued.

Validation: the live schema-4 reader matched the kept item. All 83 focused
Python tests and whole-tree Ruff pass. Native code is unchanged from the prior
checkpoint; the two recorded native transparency diagnostics remain open.
Next: native observation publication and typed game-thread command admission,
then durable bounded jobs and an automatic end-to-end run.

The owner specified the first automatic batch should use every available
production slot. Determine capacity from the current vendor queue, fill each
free slot once, and recheck acceptance before filling another. The latest
verified Malik queue has two free slots. This does not authorize blind retries
or an unbounded number of future batches. Tier 1/2 exclusion with unknowns
preserved remains the desired policy. No automatic batch has started.

## Native command implementation checkpoint - September 14

The extension now has separate typed vendor inspect/Create/Keep requests (kinds
8/9/10) within the existing schema-3 transport envelope. A vendor receipt has its
own signature and layout; movement grants are neither decoded nor consumed.
The producer process/creation/generation/heartbeat lease is reused only as
transport ownership. Payloads and deadlines are validated before queuing.

The existing native update invokes the vendor service on the exact HWND owner
thread. Startup verifies the full reviewed executable; each operation rechecks
the live scene, rooted manager/menu/hireling, building, recipe, current slots,
foreground window and topmost relevant menu. Default empty ArcString construction
and destruction use the native functions at RVAs 0x145000/0x145310; Create and
Keep use their manually qualified native builders. The game retains allocation,
message construction and sending. No synthetic network packets or remote-thread
game calls are used.

Requests receive immutable local submission receipts. They are not server
acceptance. The controller blocks another mutation until an unambiguous queue
addition, or queue removal plus owned inventory presence, is observed. Gaps,
session changes, multiple additions and uncertain native calls stop mutation.
A process-local ledger never evicts action UUIDs; an identical repeat returns
its old receipt and a changed repeat is rejected. At 4096 actions it stops new
mutations rather than permitting old requests to replay. Queued requests that
expire before the UI thread consumes them are retired without invoking the game.

Validation: Win32 Release build passes, and all 82 selected native startup,
event-channel, movement channel/runtime/lifetime, vendor controller and vendor
reader cases pass. This is a source/build checkpoint, not a live automatic
crafting qualification or deployable release identity. Private build artifacts
still carry the prior version until the complete package is prepared; do not
install them as a replacement 1.8.1. The previously recorded rendering failures
remain outside this selected test set.

Remaining in this slice: host wire/session implementation, a durable controller
that fills every initially available slot once, cross-language/channel tests,
then a versioned package and live automatic qualification. No automatic commands
have been issued to the test VM. Junk/disposal remains unavailable.

## Durable capacity-aware batch checkpoint - September 14

The host now exposes typed vendor sessions and `client fill-vendor-slots`.
It binds the exact process lifetime, window and vendor, persists each request
before submission, and waits for a correlated native queue transition before
sending the next Create. Existing journals are never replayed. Lost receipts,
timeouts, logout, disappearing capacity and unrelated item changes stop the batch.

The owner ranked up both vendors and expects further capacity increases.
Capacity is read from the current queue, never fixed at two. New slots appearing
between requests or while a Create is pending extend this batch's recorded plan.
The batch finishes when the observed queue is full. It does not automatically
clear completed items or start indefinite replacement batches. The wire/reader
bound is 16 slots; exceeding this bound rejects the observation rather than
silently truncating capacity. There is no evidence yet of a vendor exceeding it.

Validation: 120 focused Python tests pass, including repeated 2-to-4-to-6 slot
growth during and between requests, a 16-slot vendor, no replay after interruption,
and C++/Python wire compatibility. All 83 selected native tests pass, including
the actual channel, controller growth and bounded reader cases. No new package
is installed and no automatic game commands have been issued. Next: versioned
package validation and live queue-fill qualification, followed by completed-item
assessment/Keep integration. Junk remains unqualified and unavailable.

## Versioned package prepared for live qualification - September 14

The exact source `8aad37f` produced product 1.8.2 / wheel 0.3.2. Full Python,
both required native profiles, explicit private image bindings, IPC, installed
wheel checks and all seven CI jobs passed. The two known rendering diagnostics
remain recorded. See [exact package handoff](handoffs/vendor-rolling-1.8.2.md)
for hashes, counts, private artifact locations and remaining live work.

A fresh read of the existing 1.8.1 test client confirmed Malik now has three
empty slots. The random recipe window was not open. No automatic command was
sent. The separate guest runtime is prepared and verified; current game/shortcuts
remain unchanged. Next: close the current game, launch 1.8.2, login and perform
the first native capacity-aware batch, then finish completed-item integration.

The owner closed the prior client and the prepared 1.8.2 game is now running.
The matching 32-bit verifier confirmed its exact DLL. Runtime identifiers and
launch evidence remain guest-local. Initial native inspection timed out before
world entry; no mutation was issued. Next: login as Treehugger, select Malik's
random Gilded Scepter recipe, verify inspection and run the current-capacity batch.

## First automatic capacity batch - September 14

The live 1.8.2 service returned an OBSERVED/READY receipt for Malik with the
random Gilded Scepter recipe selected and three empty production slots.
The authorized batch persisted one request per slot, submitted each once and
waited for its distinct native queue transition. Its journal completed with
three observed requests, three new items and capacity history [3]. A separate
rooted read matched all three batch items and reported each as cooking.
No Keep, Junk or replacement batch was issued. Detailed evidence is retained in the VM and excluded from Git.
The bounded passive observer detached normally after its five-minute window
without completed results. A fresh independent read still found all three batch
items cooking. No observer remains active and no keep/discard action was issued.

The live queue-filling hook is qualified for this exact package and recipe;
this does not certify completed-item handling or the entire rolling loop.
Next: completion/affix assessment and automatic Keep qualification, followed by
safe disposal and manager-owned recurring jobs.

## Durable completed-batch Keep implementation

Host wheel 0.3.3 adds `client keep-vendor-batch`, using the unchanged 1.8.2 native
Keep contract. The controller binds the successful Create journal to the live
client/scene/vendor, requires completed items and an open owned inventory view,
records each request before sending, and waits for correlated native inventory
presence before moving to the next item. Lost replies and uncertain transitions
stop without replay. Confirmed exclusions remain in production; no disposal or
replacement crafting occurs. Valid same-batch native completion evidence uses
the existing affix assessment. Missing evidence stays unknown and is preserved.

Focused validation: 54 Python tests pass, including durable writes, uncertain
outcomes, queue removal without inventory, wrong client/evidence, conflicting
captures, hidden inventory, cancellation and exclusion/unknown handling. This
is a host-only update; the loaded native client is unchanged. The full host suite passed 2120 tests with 12 expected skips; Ruff also passed.
Exact-source host packaging and live automatic Keep qualification are next.

## First automatic Keep batch verified

Host-only wheel 0.3.3 from `25dd627` was built from an exact-commit archive with
embedded source identity, installed into a separate host environment and checked
through its installed command entry point. Native 1.8.2 remained unchanged and
running. All three finished items matched the original Create batch; the current
owned inventory was visible before submission. The captured completion evidence
contained no resolved affixes, so all three were kept as unknown under the user's
policy. No guessed affix names or tiers were used.

The durable Keep journal finished with three inventory-confirmed requests. A
separate rooted reader matched every batch item in Malik's inventory and found
all three production slots empty. No discard or replacement batch was issued.
The automatic Create -> completion -> Keep path is live-qualified for this
selected recipe/vendor and visible inventory. It is not certification of full
inventory capacity, all low-tier mappings, Junk, or indefinite recurring jobs.

Host wheel SHA-256: d0aeee50351fd7890d3152045b2c8b88518ead124536e5af05c8114c2084a3b9.
Host source: `25dd627e6dbf56bf804f73a803fe6690fd4c83ec`; native source remains
`8aad37fcf691e05ae49960f939cab8ceba43a299`. Detailed host installation and batch
receipts remain local and excluded from Git. An initial working-tree package
was not installed; it was archived separately from the verified exact-source
wheel, with its original locations recorded in the private artifact directory.
Next: manager job integration, complete exclusion identity coverage and qualified
disposal, inventory/resource capacity and recovery validation.


## Manager job runner checkpoint

The instance-scoped durable job runner now composes the verified Create and Keep
operations into one capacity batch. Local pause waits before new actions while
a submitted request is still reconciled. Stop or lost dispatch authority prevents
further submissions. Explicit recovery resumes only at a fully persisted phase
boundary; partial or uncertain child journals require review and are never replayed.
The runner waits visibly for cooking and the vendor Inventory, with a one-hour
job deadline. Unknown affixes remain preserved; no discard or recurring refill is
enabled. Native window-opening hooks, resource capacity and full exclusion identity
coverage remain unqualified. This is source validation, not a new deployment.

Active: dashboard controls and exact-worker composition. Next: manager regression
tests and packaging; then the remaining live window/resource/disposal qualification.


## Host 0.3.4 manager integration

The dashboard now exposes one bounded vendor job through the existing exact
worker operation ledger. New command shapes are strictly validated. Start requires
a current permit and a capability receipt from that same worker lifetime; an
older host is rejected before an unsupported operation reaches its ledger.
Pause/resume/stop name the current job as well as the exact game instance.

The worker verifies the qualified game executable and process lifetime, composes
the durable Create/wait/Keep runner, and always closes its native session. It
rechecks dispatch immediately before native submission, including after the
request journal was flushed. Local pause never abandons a pending receipt;
lost permits, uncertain outcomes, changed vendors and stale evidence stop safely.
No native files changed. This checkpoint does not enable disposal or unattended
recurring replacements. Full manager/live installation qualification is separate
from the previously verified command-line three-item batch.


Validation for the manager source: 2150 host tests passed with 14 explicit
environment skips (unavailable symlink privilege or unbound native movement
fixtures); 571 subtests passed. Repository Ruff, dashboard JavaScript syntax and
diff whitespace checks passed. New coverage includes full worker Create/Keep,
rank growth, duplicate starts, stale jobs/permits, older-worker rejection,
HTTP authentication, last-moment dispatch revocation and crash reconciliation.
Exact-source host packaging and installed-manager read-only qualification are next.
