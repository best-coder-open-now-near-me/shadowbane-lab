# Terrain texture ownership: offline evidence

Reviewed on 2026-09-03 against the preserved vanilla executable SHA-256
`55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc`.
Addresses below are preferred-image VAs, not ASLR-adjusted process addresses.
This is an offline review record, **not an approved runtime memory mapping or hook**.
No process memory, texture pixels, or new live trace was read for this step.

## Terrain shader and source lists

RTTI identifies `ArcShaderCustomTexturedTerrain` at vtable VA `0x015625a4`.
Its constructor at `0x008f1470` installs that vtable. A static initializer at
`0x005bfe70` constructs the shader at preferred VA `0x01788228` through thunk
`0x00412c88`; this observation does not establish safe concurrent access to
that object in a running process.

The populate routine at `0x008f19e0` obtains its source through the second
argument's `+0x10` pointer. It clears the shader's paired vectors, then:

- Copies the source's `+0x1a4` reference into shader `+0x2c`.
- Iterates source vector `+0x150` / `+0x154`.
- Takes the corresponding reference from source vector `+0x15c`.
- Passes the pair to thunk `0x0042941a`, which reaches `0x008f1ac0`.
- That helper appends the first reference to shader vector `+0x14` and the
  second to shader vector `+0x20`, preserving reference ownership.

The draw routine at `0x008f1660` binds entries from shader `+0x14` on texture
unit 0 and paired entries from `+0x20` on unit 1. The unit-1 path explicitly
handles null entries by disabling that texture unit. The optional `+0x2c`
reference supplies the separate initial pass.

All three reference paths invoke virtual slot `+0x58`. The already observed
return sites `0x008f1772` and `0x008f1864` remain the link to the saved trace's
25 initial passes and 29 masked layers. This statically explains the paired
color/mask ownership; it does not reveal those instances' actual resource keys.

## Texture object to GPU binding

RTTI separately identifies `ArcColorTexture` at vtable `0x0154a39c`.
Slot `+0x58` points through `0x00410631` to `0x005df600`. In this exact
preserved client, the latter already jumps to a client trampoline at
`0x00cf7202`; do not assume an unpatched prologue there.

That trampoline reads the backing object at texture `+0x5c`. If absent, it
invokes virtual slot `+0x44` before testing the backing pointer again. For a
present backing object it reads:

- `+0x44`: the texture name passed as the second binding argument.
- `+0xfc`: the texture target passed as the first binding argument.

The call reaches `0x00945a20` through thunk `0x0040a00b`. That wrapper caches
the per-unit binding and calls the GL binding import at `0x01ab086c` when needed.
Consequently invoking the texture's binding method is not a read-only way to
query its identity: the client can lazily load a missing backing object.

The saved draw trace does **not** record the bound texture object's vtable.
Therefore this exact class path remains conditional until instance type is
established; do not cast arbitrary captured GL names to `ArcColorTexture`.

## Resource token boundary

The texture identity accessor at `0x005e15b0` copies the two words starting at
texture `+0x10` through `0x005117b0` (thunk `0x00425581`). Their construction
and serialization must be reviewed before interpreting them as the cache
directory's `group_id, resource_id` pair. The two formats are not proven identical
merely because both occupy eight bytes.

The RTTI-backed `ArcTerrainImageBuilder` vtable at `0x015634cc` confirms its
build method at `0x00954750`. Its token accessor at `0x00511f20` masks the second
word to 20 bits. The builder then applies a minus-one / 1000 quotient-and-remainder
calculation before requesting a one-by-one terrain region. This is useful tiling
evidence, but does not yet prove archive word order, map/layer encoding, mask
orientation, gutter convention, or the live trace's exact archive entries.

## Next review gate

Decode and verify token construction/serialization and the terrain-mask image
population/sampling path against the existing archive decoder. Preserve the
distinction between static ownership evidence and actual instance attribution.
The saved trace can be reanalyzed without recapture, but cannot retroactively
supply resource tokens it did not record. If live instance attribution remains
necessary, define that narrow reviewed data path before collecting anything
further; do not add a broad memory scan or guess offsets.

No renderer behavior, client settings, live resources, or archives changed.
