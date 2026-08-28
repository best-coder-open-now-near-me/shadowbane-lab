# WonderBane vendor dialog protocol incompatibility

## Finding

WonderBane's vendor dialog failure is a server/client protocol incompatibility,
not a text-rendering or character-encoding failure.

The emulator replies to an initial `VENDORDIALOG` request with message type `3`.
The exact WonderBane client examined here does not deserialize or handle message
type `3`; both code paths deliberately fall through to their default return.
Consequently, the client never constructs the NPC-service window and never sends
the expected follow-up `VENDORBUYWINDOW` request.

An overlay can expose the otherwise lost server payload, but it is only a
diagnostic or compatibility fallback. The durable fix is to make the emulator
emit the message variant implemented by the client.

## Affected clients

- Executable: `sb.exe`
- Original/local SHA-256:
  `ef43784ba6ffa0de6c0c16c76569f864393ad1530e7149395bb560e5cca30f13`
- Text Fix SHA-256:
  `2b186aef864ea1ce16d8ec959c450f1f2e301d1ba25d9daa3b14ab6c65d68c3d`
- Clean WonderBane copy SHA-256:
  `0889b39a6f065f2ddf696bad01455e0b691892077105fe27e35de94bfdf59ebc`
- Preferred image base: `0x00400000`
- `ArcMerchantMessage` vtable: RVA `0x0115463C`
- Message handler: VA `0x007607E0`
- Deserializer: VA `0x007614D0`
- Serializer: VA `0x00761860`

The checked-in native observation profile records the executable-bound
signatures and offsets:
[`wonderbane-2b186aef.native-vendor-dialog.json`](../src/shadowbane_lab/client_observation/data/wonderbane-2b186aef.native-vendor-dialog.json).

The complete merchant code range from handler entry through serializer tables,
file offsets `0x003607E0..0x00361A6F`, is byte-for-byte identical in all three
executables. Its SHA-256 is
`2e9b7047cfd6bd0423d447139ae6c6f38a981cbd202c0a48acd7ded8773d9119`.
The handler, deserializer, and serializer dispatch maps are also identical.
Therefore, the Text Fix did not introduce the vendor failure.

## Live reproduction

The sanitized fixture at
[`pelt-vendor-dialog.json`](../tests/fixtures/vendor_wire/pelt-vendor-dialog.json)
contains the plaintext application messages from one interaction with Pelt. It
contains no packet framing, addresses, ports, cipher state, session identifiers,
or account metadata.

Observed sequence:

1. Client sends opcode `0x98ACD594` (`VENDORDIALOG`), message type `1`, for NPC
   object type `42`, object ID `42047`.
2. Server replies with the same opcode and message type `3`.
3. The reply contains a well-formed emulator-defined menu with
   `VendorDialog`, `VendorArmorer`, `[ Merchant options ]`, and `Done`.
4. The client emits no `VENDORBUYWINDOW` (`0x682DAB4D`) request.
5. No actionable vendor window appears.

The strings decode correctly as UTF-16BE. The failure occurs when the client
dispatches on message type, before any vendor UI or text rendering.

## Client binary evidence

### Handler dispatch

The handler at `0x007607E0` dispatches on `message_type - 2` through a byte map
at `0x0076121C`. For message type `3`, the selected byte is `7`, whose jump-table
entry is the default return at `0x007611E7`. No UI function is called.

Relevant supported cases include:

- Type `2`: branch `0x00760CD3`, the NPC-service UI path.
- Type `4`: branch `0x00760DBD`, the close-dialog path.
- Type `3`: default return; no handler.

The type-2 branch looks up UI component ID `0x31` and builds resource identifiers
using the client literals `NPCService:` and `NPCServiceUnit:`. This is positive
evidence that type `2`, rather than type `3`, owns the service/vendor presentation
for this client.

### Deserializer dispatch

The deserializer at `0x007614D0` independently dispatches on
`message_type - 2`. Its map at `0x00761780` also sends type `3` to the default
path. There is therefore no hidden type-3 body parser that merely failed later.

For type `2`, the deserializer reads these logical fields after the common
message fields:

1. A string into object offset `+0x90`.
2. A string into object offset `+0xA8`.
3. An integer into object offset `+0xC0`.

It then reads the common option-map count and repeated key/value entries stored
under object offset `+0xE8`. The serializer at `0x00761860` writes the inverse
field sequence. This is the client-side logical contract that the corrected
server message must populate.

## Emulator source evidence

The MagicBane server source examined at commit
`3649c629b709c67625a09150a3752107f4b873cc` declares:

- `VENDORDIALOG` as opcode `0x98ACD594`.
- `VENDORBUYWINDOW` as opcode `0x682DAB4D`.
- `VENDORSELLWINDOW` as opcode `0x267DAB90`.

In `src/engine/net/client/msg/VendorDialogMsg.java`, `replyDialog` calls
`msg.updateMessage(3, vd)` for the initial and subsequent normal dialog reply.
Its serializer then emits the custom type-3 menu seen in the live capture.

The matching emulator deserializer reads only a fixed prefix and ends with the
comment `TODO more message to go here`; it does not document or validate the
custom type-3 body. The same file has old, commented menu serializers, while its
special-case close paths use message type `4`, agreeing with the client.

Upstream source:
[MagicBane `VendorDialogMsg.java`](https://repo.magicbane.com/MagicBane/Server/src/branch/master/src/engine/net/client/msg/VendorDialogMsg.java).

## Required server fix

The server should not send the current custom type-3 menu to this client build.
The production fix should:

1. Serialize ordinary NPC service/vendor replies as `VENDORDIALOG` message type
   `2`, populating the two resource strings, the integer discriminator, and the
   option map expected by `ArcMerchantMessage`.
2. Preserve type `4` for closing the dialog.
3. Preserve the existing vendor object identity and range/permission checks.
4. Add a golden-wire test for the exact client-compatible type-2 payload.
5. Add an integration assertion for this sequence:

   `type-1 VENDORDIALOG request -> type-2 reply -> VENDORBUYWINDOW request`

The type-2 logical fields are proven, but their complete raw byte representation
has not yet been claimed here. That final byte layout should be established from
the client's stream methods or a known-good type-2 capture before shipping the
server change. Simply changing the current leading `3` to `2` is not sufficient;
the bodies are different variants.

Implementing the emulator-defined type-3 body in the client would also repair
the protocol boundary, but it is a larger and less maintainable binary change.
Whichever side is changed, the corrected path must restore the ordinary dialog
and not merely skip it.

## Known bypass is not the fix

The client can request `SHOPLIST` directly for the selected vendor. The server's
`openBuyFromNPCWindow` path still resolves the NPC, enforces talking range, and
replies with `BuyFromNPCWindowMsg`; later purchases retain their inventory, gold,
range, and locking checks. This explains how an operator can open or use a vendor
for a player while the preceding dialog is broken.

That direct request bypasses the unsupported `VENDORDIALOG` menu and is useful
for diagnostics or emergency access. It does not restore the missing dialog,
its choices, or other NPC-service flows, so it is not the root fix.

## Regression oracle

The local parser and sanitized capture provide a regression oracle for detecting
the incompatible emulator reply. They do not require packet capture, cipher
state, process-memory access, or client input:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_vendor_wire -v
```

A server-fix test should additionally fail whenever the initial server reply is
type `3` for this executable identity and pass only after a client-consumable
type-2 reply causes the buy-window follow-up.
