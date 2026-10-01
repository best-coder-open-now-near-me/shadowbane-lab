# Retaliation session boundary — October 1, 2026

Automatic retaliation remains disabled. The user confirmed that server source and
protocol documentation are unavailable. This bounded offline audit identifies
client connection and login paths, but does not establish that the first
PlayerData on a new connection authoritatively starts a new server character
session. No client, VM, network connection, hook or game action was executed.

## Exact image and evidence

Reviewed prepared client **1.3.38.13** SHA-256:
`0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d`.
Official original SHA-256:
`e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8`.

Private image:
`artifacts/guard-deploy/client-update-20260930-late/review-prepared-sb.exe`.
All **15** ranges in the retained
`artifacts/pve-pvp-resume-20260924/session-evidence-manifest.json` match this
prepared .13 image exactly. Those ranges cover NewWorld, PlayerData decode and
publication, ReadyToEnter, connection management, receive queues and socket
creation. This requalifies those client instructions; it supplies no server
ordering guarantee.

Retained private explanations and disassemblies are in the same directory:
`session-barrier.md`, `qualification.md`, `network-owner-full.txt`,
`network-stop.txt`, `server-link-ctors.txt`, `socket-constructor-full.txt`,
`underlying-socket-close.txt`, and the PlayerData process/decode files.
The additional paths below were inspected directly in the exact image.
All addresses below are **RVAs**, not preferred-base operand addresses.

## Concrete connection and login graph

- Network singleton `16AB888` owns receiver at `+0` and writer at `+4`.
  They share the receiver's socket at `+3C`. A writer replacement therefore
  does not imply a physical connection replacement.
- Setup `7F48D0` constructs receiver `4A1410`. Its network thread
  `4A1750` creates the linked socket at `4A1789..4A1808`; the qualified
  transport constructor reaches the Winsock TCP socket operation. Setup first
  tears down existing links. `7F4630` is another reviewed setup variant, but
  this audit did not establish a normal direct caller of its thunk `232AE`.
- Stop `7F4CE0` stops both link objects, marks receiver shutdown, closes the
  underlying socket and releases the link references. Underlying close
  `111350` reaches Winsock `closesocket`. Receive retirement also sets socket
  byte `+1C`. Addresses and Winsock handles may be reused; neither is a durable
  connection incarnation.
- **Server transfer:** RTTI identifies `ArcServerTransferMessage`, table
  `1157BC4`. Its process method `3A2220` calls stop at `3A224A`, starts a
  new receiver at `3A2278`, creates its paired writer at `3A239D`, constructs
  `ArcLoginMessage` through `35CA10`, and sends that message at `3A246C`.
  Login fields are populated from existing client state. This is a concrete
  reconnect/login path, not a first-character-session acknowledgment.
- **Login handoff:** path `787600` constructs
  `ArcLoginToGameServerMessage` through `35F1A0` and retains it in global
  `16AADA8`. At `7877B1`, it copies an opaque buffer and length from the
  existing `ArcSecureSocketImp` fields `+18/+1C` into the request. It stops
  the old connection at `7877BD`, starts the next receiver at `787944`,
  and sends the retained request at `787F69`. Thus login material explicitly
  crosses physical connections. Its character-session semantics are unqualified;
  this is not evidence that targeted combat messages themselves are replayed.
- A separate setup `7F4A10` constructs a receiver with a supplied socket via
  `4A1650`. The inspected caller at `7DC25E` passes null for that socket.
  This path is not evidence that normal character switching reuses an old socket,
  but it prevents treating every receiver construction as fresh TCP creation.

## Where the proof stops

PlayerData decode `37D130` owns a newly decoded player object at message `+60`.
Process `37C080` publishes that exact object through `37C8D8 -> 70340`,
then queues ReadyToEnter at `37CC68`. No verified association between that
publication and a unique login request, authenticated connection incarnation or
server character-session generation was found. The handler is not restricted by
a qualified “first publication on this connection” guard. Unclassified message
fields must not be relabeled as session tokens.

Client replay and retry paths do exist. The reviewed ArcMessagePlayer replay
caller invokes the same decoder at `49D39D`; the network caller is `4A192D`.
Processing at `522069/522159` can requeue the same referenced message into a
separate queue. Targeted messages can also create deferred actions. Physical
socket closure does not, by itself, prove that all decoded messages, retry entries
and deferred actions have disappeared.

Consequently, a fresh transport can separate bytes received on old and new
sockets **only when original receive provenance is preserved**. It does not
establish the meaning of the cross-connection login handoff or rule out server
session resumption. Conversely, this audit found no proof that the server does
resume or replay old targeted events. Both claims remain unsupported.

## Bounded next qualification

1. Resolve the opaque secure-socket handoff and login response fields far enough
   to determine whether the client checks a unique entry identity, or merely
   transfers authentication material. Relevant boundary: `13DBBD` produces
   secure-socket `+18/+1C`; `35F2C0` copies them into LoginToGameServer;
   incoming process `35F350` copies message `+68/+6C` into client state through
   `4BA810`. No session interpretation is assigned to these fields yet.
2. Qualify all supported character-entry/transfer paths and their relation to
   first PlayerData publication. A candidate fresh-connection-only policy must
   permanently revoke on a later character transition and distinguish physical
   sockets from receiver/writer wrappers. Current evidence does not prove every
   character switch reconnects.
3. If that association can be proven, finish immutable receive/message/action
   lineage through retries, replay exclusion and disposal, and independently
   qualify hostile action semantics. A recent decoder timestamp, current victim
   key or successful process return cannot replace either proof.

Do not implement a disabled receiver scaffold or force reconnects on these
findings. The current targeted-action observer remains opt-in, diagnostic-only,
and reports `combat_authority=False`. Manual-list combat and PvE recovery remain
independent. See [the existing provenance contract](pvp-response-provenance.md).
