# Native current-group commands

The focused branch `codex/native-group-come-20261010` targets main. Incoming
command support is under implementation; this checkpoint supplies native receive
publications, not a deployed command feature. No client controls or live group
messages were used to validate it. Version selection belongs to the release
composition after the independent UI-ownership fix.

The authorized commands are literal `/come` and `/attack first_name`, from any
current group member. `/come` is a one-time regroup: cancel the current operation
through its existing owner, confirm cleanup, travel to the verified sender
position, and remain there with ordinary automatic maintenance. It does not
resume the previous camp. `/attack` is a separate explicit manual-player command,
not attack authority derived from Track contacts. Detect Hidden and Reveal are
separate learned powers; neither is automatically activated by these commands.

## Native receive boundary

The exact supported official .17 image is
`051c55ebd0f25ff5fe9bd27b25efbe3cde0190d1dbf1c2a33eb9604996c69698`;
its reviewed prepared image is
`baa6c84e5f28aab01d516f12257354b42375d11e8e8e98930cfcf754aeec24e9`.
The corresponding qualified .16 pair remains supported. Startup checks the exact
file identity and the existing relocated loaded-code guard before replacing only
the expected destructor, Process and decoder vtable slots. Native call-through,
exceptions and LastError remain intact. This observation path never sends a
packet, takes movement ownership, or mutates a client message.

| Native type | Table RVA | Process / decoder RVA | Copied fields |
| --- | --- | --- | --- |
| ArcChannelMessage | `0x11520fc` | `0x337b30` / `0x337e80` | channel +0x70, sender ArcString +0x74, body ArcString +0x8c |
| ArcUpdateGroupMessage | `0x115130c` | `0x3280b0` / `0x328c10` | subtype +0x68, count +0x70, has-rows +0x74, XYZ array +0x8c, exact-key array +0x90, error +0xa8 |

Channel 14 is incoming group chat. Its decoder does **not** supply a sender
object key: +0x68 is decoded only for channel 16. Process can substitute the local
name for an empty sender. The observer copies the decoded sender before that
mutation and rejects empty senders. At Process entry it matches the first name
uniquely against the current native roster, copies the exact key and roster
context, then checks that context again after native Process returns. Unicode
names retain their original text; comparison uses Windows ordinal case folding.

Group-update subtypes 1, 2 and 5 carry per-key positions. The subtype 2 and 5
branches call `0x59ccc0` through thunk `0x21eef`, with the position flag enabled.
That setter copies XYZ into roster entry +0x68/+0x6c/+0x70. The recorder qualifies
a returned update only when the handler's in-world mode (window +0x64 = 2)
holds at entry and return, and every copied key and XYZ also matches the current
native roster. A skipped native update therefore cannot stamp differing cached
coordinates as fresh. Other supported subtypes (3, 4, 6, 7, 8) carry no position
freshness and invalidate a consumer's cached coordinate provenance.

Both bounded mappings follow the existing Track decode-ticket pattern. Only
calls from the qualified network decode return `0x3625bc`, on the active socket
vtable `0x116019c`, mint a decode ticket. Process consumes that exact copied
payload ticket. Destroy, another decode, scene transition, invalid payload or
lost ticket cannot masquerade as a newly received command. Names and arrays are
copied completely with bounds; truncation is never valid evidence.

## Wire contract and authority limits

Mappings are `Local\ShadowbaneLab.Extension.GroupMessages.v1.PID.CREATION` and
`Local\ShadowbaneLab.Extension.GroupUpdates.v1.PID.CREATION`. Each has the same
64-byte identity/counter header as Track and 32 records. Record sizes are 760 and
544 bytes respectively. The 64-byte record header records decode sequence,
processing generation, native tick, scene epoch and local actor key. Payloads
begin with the existing group-context words: marker, window, manager, sentinel,
member count and each node/entry/key/role, followed by sender key and reserved
zero. This is observed native group identity, not a server-issued group nonce.

Flag bits are payload=1, current scene=2, decode lineage=4, current roster=8.
Only returned stage 3 with all four bits is qualified. Consumers must use the
largest processing generation rather than return order, since native callbacks
can nest. An initial read is history, never a request to execute. Ring gaps,
unavailable data and failed reads cannot refresh a position cache. Current
character, group and exact sender key must be revalidated at execution; original
processing scene is not proof of the server's originating character session.

The host integration will persist consumption before any effect, avoid historical
replay after restart/enable, and use the existing worker operation ledger and
confirmed handoff. The native component alone grants no movement or attack.

## Validation

`wonderbane_extension_group_messages` exercises receive lineage, immutable sender
copy despite native mutation, exact member qualification, group changes, scene
changes, destructor invalidation and ordinary non-group call-through.
`wonderbane_extension_group_updates` exercises copied exact keys/XYZ, independent
identical generations, unapplied-update refusal and bounded arrays. Both export
an actual native ABI frame for required Python reader interoperability tests.
The standard CI and package builder require these native cases and both actual
frame tests in full and diagnostics profiles; missing or skipped cases reject
qualification. These tests use substituted native handlers, not a server.
The existing extension startup fixture covers optional observer failure and
cleanup without making an unavailable observer fail the ordinary client.
