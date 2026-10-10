# Group chat receive correction — October 10, 2026

Pro sent `/come` while grouped with Umbra. The user confirmed it appeared in
Umbra's group channel. The installed .97/.62 observer recorded zero messages
and zero rejected messages, while the group-update stream reached sequence 54.
No movement or combat command was admitted.

The listener watched the legacy ArcChannelMessage. Ordinary group messages use
GroupChannelMessage, also used by the existing outgoing native callout path.
The fix hooks that class's destructor, Process and decoder slots, preserving
native call-through, exceptions and LastError. It does not retain a second
legacy compatibility observer.

## Exact native layout

The table is RVA `0x115dbc4`; slot 4 is thunk `0xfcbd` to destructor `0x427d40`,
slot 0x14 is thunk `0x10523` to Process `0x4142c0`, and slot 0x1c is thunk
`0xac5e` to common decoder `0x4145e0`. Group decode `0x428510` supplies the
additional name and world fields. The successful recipient is `0x428220`.

The decoded native object is key `{id,type}` at +0x60, status +0x68, body
ArcString +0x6c, channel 14 at +0x84, sender ArcString +0x90, and world ID +0xa8.
The socket's key reader `0x13f220` reads wire type into key+4 and ID into key+0.
The outgoing group constructor places message text in the same +0x6c string.
Local server source corroborates these fields, but is not evidence of the
current Wonderbane server's implementation or session guarantees.

The exact .16 official, .17 official and prepared .17 images have identical
reviewed table/decoder/Process/key-reader/dispatch spans. Local evidence is in
`artifacts/group-receive-20261010/native-image-review.json`, SHA-256
`8e1bef42832656b8a29747a90a20bbfcfac61135a88aef91ac160e079e909252`.
Private images and captured message data are not source artifacts.

## Command authority

Only a successful native group receive can qualify. The exact decoded key is
kept in the private decode ticket and must survive unchanged until Process.
It must also match the unique roster name and key before and after Process.
The public 760-byte record and host parser remain unchanged; unqualified records
never expose a roster-qualified sender key. Scene, active socket, decode caller,
copy bounds, consumed generation and execution-time group checks remain intact.
The copied body and name are preserved even if native display processing mutates
the object. This is current client evidence, not a server session nonce.

## Validation and delivery

Both native group publication fixtures and all eight actual-frame Python reader
tests passed. Added regressions cover same-name/different-key attribution,
a changed key between Decode and Process, and the native error branch.
Independent review passed; final combined .98/.63 package qualification follows.
The installed .97/.62 runtime remains unchanged; live `/come` is still pending.
