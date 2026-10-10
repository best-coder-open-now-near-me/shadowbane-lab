# Native current-group commands

PR #157 merged the .98/.63 receiver and Track presentation changes into main.
The qualified runtime is installed and its launch is verified. A fresh Pro
`/come` reached the native GroupChannelMessage observer with current-group
attribution, but host admission expired; no operation or movement followed.
Track publication startup separately failed its close-pointer guard and blocked
automatic upkeep. The reviewed thunk correction and companion admission repair
are merged through PR #158, qualified and installed as .99/.64. Replacement
activation and fresh launch are verified; live command/Track acceptance is pending. See the [current qualification record](group-admission-delivery-20261010.md)
and [preceding installation evidence](group-track-delivery-20261010.md).

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
| GroupChannelMessage | `0x115dbc4` | `0x4142c0` / `0x4145e0` plus group decode `0x428510` | key +0x60, status +0x68, body ArcString +0x6c, channel +0x84, sender ArcString +0x90 |
| ArcUpdateGroupMessage | `0x115130c` | `0x3280b0` / `0x328c10` | subtype +0x68, count +0x70, has-rows +0x74, XYZ array +0x8c, exact-key array +0x90, error +0xa8 |

Channel 14 is incoming group chat. The GroupChannelMessage decoder supplies the
sender's native object key, body and first name. Its successful Process branch
requires status zero. The observer copies these before UI processing and requires
both the decoded key and unique first name to match the current native roster.
It checks the same roster again after native Process returns. Unicode names
retain their original text; comparison uses Windows ordinal case folding.

The previous .97/.62 observer incorrectly used the legacy ArcChannelMessage
class. Pro's `/come` appeared on Umbra's group channel but produced no receive
records, while group-position updates continued. The corrected class and fields
are verified against identical .16/.17 client code spans. The .98/.63 replacement
received a fresh live command, but admission/travel remain unverified. See
[the receive correction](group-chat-receive.md).

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

## Host command behavior

`client-pve-settings --group-commands enabled` enables this character's listener;
`disabled` stops accepting commands. This preference is independent of Hunt Foe,
tracking callouts, and buff selection. Existing settings migrate with group
commands disabled. Ordinary Pause and dispatch revocation also prevent commands.
The dashboard reports listener availability and the last request's sender,
command, queued/running/terminal or withheld state and reason.

A passive observer reads the exact process mappings and current native roster;
it never takes a movement producer. Startup, enable, read gaps and unavailable
streams seed history rather than replay it. Only a new, complete, recent group
receive with the same scene/local actor and unique current member key can create
an intent. The highest processing generation wins across nested returns.
Consumption is recorded before admission. A compact admission record links the
native event, sender key, group context and exact worker to the immutable
operation; operation receipts remain the completion authority.

The worker requests cancellation through the current operation's existing stop
signal. It waits for the actual execution result's native cleanup proof and the
preparation service's confirmed handoff, then submits one operation to its own
ledger. A terminal status alone is insufficient. Queued and active commands are
revalidated against current character, group membership and enabled state.
Ambiguous submission or an unresolved target is not replayed against later data.

For `/come`, the sender's current position comes from an exact-key native player
observation or a recent qualified per-member group update. Unavailable rows and
updates for other members do not refresh it. The destination is captured at
admission and handed to normal obstacle-aware TRAVEL. This is one-time regroup,
not continuous following: arrival ends the operation and ordinary maintenance
resumes, without returning to the previous camp.

For `/attack first_name`, the current native population must resolve one player
with that first name. Registry membership brackets the native name, server and
object-key reads. The operation-scoped executor revalidates that exact identity, protects
the local player/current group, and uses the existing `MANUAL_PLAYER` actor
context and native attack/pursuit path. It sends no UI selection or hotkeys and
does not save a persistent attack-list entry. Death, cancellation, target loss or
a native failure enters the same confirmed owner cleanup path.
A missing player remains unresolved; neither a selected object nor a Track name
can replace it. There is no blanket invisible-target rule: native availability
and existing attack eligibility determine whether that exact player can be used.

Detect Hidden (429513051, SCT-001) and Reveal (429414747, SCT-002) were observed
as learned abilities. This establishes availability only, not a current detection
effect or a successful reveal. Reveal Thyself (429429978) is a different power.
Any future explicit scout utility belongs in the same actor owner's learned-power
path; these commands do not auto-cast, infer perception from registry presence,
or authorize attacks from passive detection alone.

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
