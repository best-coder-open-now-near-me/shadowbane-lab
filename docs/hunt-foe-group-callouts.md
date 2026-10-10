# Hunt Foe group callouts: native evidence and delivery boundary

The callout feature is not enabled. `pve/tracking_callouts.py` supplies the reviewed
appearance/message policy only; it does not send messages, expose a setting or
grant attack authority. Native send and group-lifetime qualification remain the
next implementation slice.

## Appearance policy

Consume complete, fresh Hunt Foe response generations. A successful empty list
can establish departure; failed/unavailable reads cannot. Deduplicate server-unique
first names, omit the local actor and consume each generation once. A new actor
or qualified group lifetime seeds its first response without retrospective chat.
One response produces at most one 120-byte ASCII message with grouped arrivals;
excess names become a count, not a delayed backlog. The limit is a conservative
policy bound, not a claimed native protocol maximum. Invalid name data preserves
the previous presence set. Missed ring history does not invalidate a subsequently
complete response.

The caller must supply freshly aged `TrackingStatus` and an actual native group
lifetime generation. A roster hash is not that generation. Reset only on explicit
disable or ownership release. A returned decision is consumed; a native sender
must separately retain an uncertain submission rather than replay it on later
tracking reads. The sender must revalidate the same actor/group immediately before
entry. No sender or group-generation source is currently wired.

## Exact .16 static evidence

Evidence image: official `sb.exe` SHA-256
`a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a`,
image base `0x400000`. All addresses below are RVAs.
Private reproducible disassembly is retained under
`artifacts/group-chat-20261010/static`; the existing
`artifacts/track-20261009/static/disassemble_track.py` accepts `--span BEGIN END`
and `--xref RVA`, and verifies the exact image digest before reading it.
No private image or copied client bytes belong in the repository.

| Boundary | Observed client behavior |
| --- | --- |
| Registration `0x46579a..0x46580e` | `/GSAY` and `/GROUP` both register `0x477e90`. |
| Ordinary command `0x477e90..0x477f58` | Copies command body, allocates `0xb0`, invokes GroupChannelMessage constructor `0x427e00` through thunk `0x1fd48`, sends via thunk `0x18c91`, releases its own reference. |
| Group constructor `0x427e00..0x427e85` | Passes channel `14` to base constructor `0x414100`, copies body to `+0x6c`, sets vtable RVA `0x115dbc4`. |
| Base constructor `0x414100..0x41417a` | Initializes key `+0x60`, status `+0x68=0`, body ArcString `+0x6c`, channel `+0x84`. |
| Shared sender `0x414520..0x414571` | Retains native reference, obtains queue singleton through `0x7dab`, calls ordinary queue through `0x5a65` (`0x7f4da0`). |
| Base response `0x4142c0..0x4142d8` | Nonzero status `+0x68` invokes error virtual `+0x24`; zero invokes response presentation virtual `+0x28`. |

The constructor reads its message token from RVA `0x138bdbc`; this is runtime data,
not a hardcoded guessed network opcode. The body is an ArcString (24 bytes), whose
first 16 bytes are `core::String`; its wrappers call named `Core.dll` imports.
The Group subclass also initializes key `+0x88` and string `+0x90`. Subtype codec
`0x428510/0x428560` reads/writes `+0x90` and `+0xa8`; their application semantics
have not been established, and the outbound text constructor does not explicitly
initialize `+0xa8`. Do not invent a group identifier there.

This outbound type is **not** `ArcChannelMessage` (incoming vtable RVA `0x11520fc`,
Process `0x337b30`, channel `+0x70`, text `+0x8c`). Reusing that incoming layout for
sending would be incorrect. The native channel-name table independently labels
index 14 as Group, but the stronger outgoing evidence is the ordinary `/GROUP`
handler and concrete GroupChannelMessage constructor.

Static span digests:

- `0x477e90..0x477fa0`: `0422e5943eb5c27b3e3b1d5b8d3283f93dfbd4a1b016452f0190bca71e99989d`
- `0x427e00..0x427f60`: `127506425fa21de191c316a0924afef7af0f3eb34a7c2d57fa74c1bfed0ae229`
- `0x414100..0x414280`: `41d2112a19dae15a6fedadecb0fd69c5b5f5ca7825a3d4876995b9095532c62f`
- `0x414520..0x414900`: `08e5cf4ff2aa1deaa68e8fca18c7d011501cf5239b9e0a34cae8c94db087f7da`

## Remaining native qualification

Existing `combat_party.h` provides a double-read scene-bound group roster:
`ArcWindowGame+0x98 -> ArcGroupManager+0x9c -> linked member records`, with exact
member keys and roles. It is suitable for immediate admission revalidation, but
does not alone prove a group lifetime across leave/rejoin with identical members.
The ordinary group sender has no explicit recipient key. Server selection of the
current group is plausible from this path, but not yet claimed as observed delivery.

Next: execute the actual constructor/string/reference/queue path in an exact-image
offline arena; qualify the group-update/retirement generation boundary; then use a
bounded passive capture of one explicitly requested ordinary group-chat marker to
confirm the recipient-channel/response interpretation. No guessed native calls,
keyboard fallback or live group send is authorized by these static findings.
Queued native submission and actual group delivery must remain distinct facts.
