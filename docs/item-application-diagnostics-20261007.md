# Optional item application diagnostics - October 7, 2026

The native recorder distinguishes a returned local item operation from incoming
item and power messages. These observations cannot settle the application journal,
authorize an action, identify a server request, or prove potion effects. It adds
no waiting period or combat admission requirement. Disabled, unsupported, dropped,
stopped and unreadable diagnostics leave the gameplay result unknown.

The original .14 executable is SHA256
`e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e`;
production hooks accept only prepared .14
`78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903`.
The October 7 official update changes CObjects data, not this executable. No
client binary or captured diagnostic data belongs in this repository.

## Native boundary

ArcObjectActionMessage uses vtable RVA `1155680`; destructor/process/decoder slots
+4/+14/+1C point through `6CF3/293C0/7CA2` to
`374DA0/374FA0/375180`. ArcPowerMessage uses vtable `1155FD8`; corresponding
slots `A5BF/1CC97/1C5D0` resolve to `382A60/382DF0/386380`.
The generic decoder return is `3625BC`. Decode lineage requires the actual linked
socket class (`116019C`), its nonretired flag, and a current native scene observed
across decoding. Destruction and every new decode invalidate the old object
lineage. A process callback consumes that ticket once, only for an equal copied
body and current scene. This does not establish authenticated server generation.

Item payload words contain subtype, operation, item key and conditional recipient
key; the recipient is zeroed when subtype is not 2. Power words copy native fields
+80 through +A8: power ID, rank, actor key, target key, position, flags and raw status.
Native process return values are raw telemetry; these handlers return zero even
on paths that do not apply anything. Process-return records retain the copied
pre-call body and never reread a potentially destroyed message.

The owned item event records the immutable command digest/request and local
entry/settlement/queue history after NativeActor returns, outside the queue lock.
It is not the append timestamp and carries no receive-message ticket. Item-key
or time proximity must not be presented as proven request/response correlation.

The follow-on owned-power event uses the same immutable command boundary and
existing 176-byte record (`kind=2`, `stage=4`). It copies the actual Scope receipt:
entry, send, append, followup, result, initiation epoch and resource availability.
It separately records whether ordinary Use was called, returned normally, and
returned true or false. A native exception leaves normal return unknown. Neither
false return nor empty initiation establishes local settlement after entry.

Before Scope entry and any stance preparation, bounded fault-contained reads copy
definition `+1F0`, bytes `+274/+275`, and actor state `+10/+18/+1C`. Definition
and coherent state have independent known bits; failed reads leave unknown fields
zero and do not block gameplay. These are raw pre-entry observations, not proof
that a later native branch ran. In particular, mode 3 does not exclude other
PreparePower refusals. The metadata fields do not invent names for state `+1C`.

For owned-power records, payload words are power ID; receipt/Use flags; Scope
result; initiation epoch low/high; availability; required mode; actor mode;
state `+1C`; state `+10`; and definition flags in low 16 bits with definition/state
known bits 16/17. The reader rejects inconsistent flags and unknown fields carrying
values. Incoming power records retain their different copied-message geometry.
Older diagnostic readers may reject this added owned-power record combination;
that means unavailable diagnostics, never a gameplay compatibility decision.

The fixed 256-record mapping has a read-only same-user ACL. Sequence commits,
overwrite/rejection/ticket-drop counters and stopped state expose gaps. Hooks
retain immutable originals for callbacks in flight, preserve native return values,
LastError and exceptions, and hold no recorder lock across a native original.
Startup failure remains optional and does not disable combat.

## Qualification and delivery

The native fixture covers exact copied body geometry, exception propagation,
reentry, scene changes, destructor/redecode invalidation, bounded eviction,
partial hook installation, read-only mapping access and immutable owned requests.
The exact-image probe verifies 13 code spans and six slots, then executes eight
real decoder cases per original/prepared image with a synthetic stream and an
instrumented power-ID dictionary lookup. It fingerprints full process/destructor
bodies; it does not execute their gameplay or networking paths.

The original recorder is installed in host .75/native .52, exact source `733b5fe`.
The owned-power addition is a separate candidate on
`codex/power-entry-diagnostics-20261007`, based on main `ae7f72d`.
Full exact-source package qualification, review and a later native installation
remain separate work. No live failure is retroactively explained by these fields.

## Read-only export

After installing a separately qualified DLL containing the observer, export an
existing exact-process mapping with:

```powershell
python -m shadowbane_lab.client_extension.item_application_trace `
  --process-id <PID> --creation-filetime <FILETIME> --seconds 30 --output <new-jsonl-path>
```

The reader opens no producer, lease, owner or action channel. It requires two
identical bounded mapping copies, validates the exact process lifetime, and never
replays an accepted sequence. Initial retained records are explicitly history;
scene stamps describe their capture time. Missing mappings, stopped writers,
read failures, overwritten records and lost decode tickets cannot mean that a
potion failed or succeeded. Export errors write an `unknown` diagnostic result.
The caller must obtain the current PID and creation time independently.

Package qualification now requires the seven native observer CTests, real native
record-layout parsing for each profile, and the decoder probe on both original
and prepared .14 images for both profiles. The receipt field
`item_application_trace_decoder_verified` certifies only that scoped probe;
`native_buff_observation_verified` retains its separate existing meaning.
