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

## Token and mask lifecycle follow-up

The token serialization boundary is now verified: `0x00511940` /
`0x00511ac0` read the first serialized word into token `+4`, then the second
into `+0`. `0x005119f0` writes in the same serialized order. The underlying
reader at `0x007e1700` reads a raw little-endian u32. Archive `(group, resource)`
therefore corresponds to in-memory `(resource, group)`, not the same word order.
The complete group word must be preserved; the low-52-bit accessor is not an
archive-key decoder.

The source render object distinguishes three paired vectors:

- `+0x150`: color textures.
- `+0x168`: source alpha masks, appended with the colors by `0x005ce130`.
- `+0x15c`: separate GPU-facing mask copies created/refreshed by `0x005ce640`.

The last routine copies exactly N*N alpha bytes and clears source `+0x1ad`.
The consumer at `0x008ae6b0` calls it only when that flag is set. Original and
generated mask backings are separate. Clone `0x005df2d0` calls `0x005dc670`,
which preserves the token through the verified two-word copy `0x00511ba0`.
This does **not** prove every mask has an archive identity: `0x0069ee60`
assigns archive-backed mask tokens, while `0x00608ea0` and the directional
seam routines also synthesize masks using the `0x005df460` texture factory.
Record absent/generated identity explicitly; never interpret a zero token as
an attributed archive record.

`0x005ce2b0` removes all-zero masks with their paired colors, and removes
occluded lower layers after an all-255 mask. The checks at `0x0058dbb0` and
`0x0058dc20` inspect width*height bytes. Retained layer indices therefore are
not stable CZone layer indices. Pixel access helper `0x0058d920` can lazily
decode data; invoking it is not read-only diagnostics.

## Confirmed edge-refresh control-flow gap

The client already implements four-direction edge copying and blend ramps in
`0x008aaea0`, `0x008ab560`, `0x008abc40`, and `0x008ac360`. It matches layers
by color texture token, checks texture flag `0x10`, and can resample stored
neighbor edges when their resolutions differ. Do not add global blurring or
assume there is no neighbor handling.

In all four routines, the completed matching-material edge-copy loop jumps
past the existing `mov byte ptr [ebx+0x1ad],1`. The blend-ramp paths execute
that store. Thus an edge copy can leave an already-generated GPU mask stale
when the incoming dirty flag is clear. This is a code-path defect; whether it
explains the user's entire visible seam remains a live acceptance question.

The minimal correction is to land each completed-copy jump on the existing
dirty-flag store, **not** on the preceding directional-completion-bit update.
That preserves repeatable neighbor copying and does not mark the edge finished.
The store changes no registers or arithmetic flags and then rejoins the same
layer-loop continuation. Only one displacement byte changes at each site:

| Jump VA | Original | Corrected | New target VA |
| --- | --- | --- | --- |
| `0x008ab14a` | `eb6f` | `eb68` | `0x008ab1b4` |
| `0x008ab80e` | `e981000000` | `e97a000000` | `0x008ab88d` |
| `0x008abe59` | `e916010000` | `e90f010000` | `0x008abf6d` |
| `0x008ac60c` | `e98b000000` | `e984000000` | `0x008ac695` |

Implementation must verify the exact executable plus all four complete edge
routines, the complete mask-copy routine, and the dirty-gated consumer, with
reviewed PE relocations normalized. Unknown/drifted code must stay unmodified.
This is a full-renderer correction only; no disk/client archive edits, no new
game input, and no per-frame scanning, framebuffer copying, or readback.

## Next review gate

Implement and test the scoped edge-refresh correction. Preserve the distinction
between this verified lifecycle defect and actual instance attribution.
The saved trace can be reanalyzed without recapture, but cannot retroactively
supply resource tokens it did not record. If live instance attribution remains
necessary, define that narrow reviewed data path before collecting anything
further; do not add a broad memory scan or guess offsets.

No renderer behavior, client settings, live resources, or archives changed.

## Resident mask access and token-comparison clarification

Offline follow-up on the same SHA-256 distinguishes two token operations:
thunk `0x412a3f` reaches `0x511bd0`, an unsigned lexicographic **less-than**
comparison (group first, then resource). It is not equality or inequality.
Thunk `0x42526b` reaches `0x511b20`, which tests both words for equality.
The base-token decision in the first directional edge routine therefore uses
token ordering. Do not describe its ramp decision as simply same/different base.

Backing pixel accessor `0x58d920` returns backing `+0x5c`. If that pointer is
null and backing `+0x104` is nonzero, it calls a decoder through `0x416e46`.
It also writes backing `+0xf4` on every call. The zero-mask test `0x58dbb0`
independently reads backing `+0x5c` and checks width `+0x38` times height `+0x3c`
bytes. An external read-only diagnostic must never invoke either method.
Reading resident bytes directly requires exact backing-class/layout validation,
bounded alpha-only dimensions, and repeated pointer/header/data checks; missing
resident data must be reported without triggering a load or decode.

The generated-mask backing factory at `0x58d340` (thunk `0x424b36`) installs
vtable `0x015490f0`; its complete-object locator `0x01592f18` resolves to RTTI
`ArcImage`. The edge routine sets width/height, channels 1, GL_ALPHA, and
GL_TEXTURE_2D, then calls setter `0x58db10` through `0x4174ef`. That setter writes
the supplied resident buffer pointer to backing `+0x5c`.

The opt-in alpha poll maps only this exact backing class and reviewed dimensions.
It additionally checks all 40 bytes of `0x58d920` before and after capture:
`568bf18b465c85c0750f8b860401000085c07405e80d95e8ff8b465cc786f4000000ffffffff5ec3`.
This is a read-only layout gate, not authority to invoke the accessor or mutate
the backing. Existing complete-graph consistency checks are unchanged.

## Terrain geometry and coordinate ownership

The retained masked terrain stack is `0x5a0765 -> 0x8e9738 -> 0x5aab67 ->
0x5b67b9 -> 0x8f1864`. Offline RTTI and virtual slots establish:

- Shader `+4` is an ArcSinglePolyMesh wrapper, vtable `0x015498a0`.
- Its draw slot `+0x2c` reaches `0x5b6790`. Wrapper `+0x10` selects a cached path;
  only zero takes wrapper `+0x14` through the mesh's draw slot `+0x30`.
- ArcMesh vtable is `0x0154965c`; its draw method is `0x5aab20`.
- Mesh vector `+0x64` holds tightly packed float3 positions; `+0x70` holds float2
  UVs. CacheCompiledVertexArrays vtable `0x015496b4` slots `+0x10/+0x14` lead to
  `0x8e90e0/0x8e9180`, which pass those exact pointers to GL with zero stride.
- Mesh vector `+0x94` holds uint16 indices. Mesh `+0xf8` chooses a draw action;
  only RenderNormal vtable `0x015495a8` is attributed here. Its method `0x5a0740`
  sends the entire index vector as triangles. Optimized/multidraw actions are not
  interchangeable and are not cast to this topology by the poller.
- `0x8e9430` with terrain flags `0x1b` configures units 0 and 1 using the same
  float2 UV vector. The float3 alternate unit-1 path requires flag `0x800`, absent
  from this terrain call. Array-cache state can still differ at runtime; reading
  source arrays does not verify the actual GL bindings.
- `0x8f1660` scales unit-0 texture coordinates by 14. Unit 1 rotates around
  `(0.5,0.5)` using source float `+0x1a8`, with a negative Z rotation axis.

The extension's BeginBandedLightingDraw rejects blend-enabled draws. The saved
masked terrain draws have blending enabled, so the single-texture cel shader
does not replace these mask-composition passes. This does not rule out differing
lighting of the base pass or establish a full scene visual comparison.

The geometry option preserves exact executable/lifetime and existing graph
checks, additionally gates four non-relocated instruction spans, and bounds
resident geometry reads. It never invokes a method, obtains GPU data, or treats
source-array coordinates as already projected screen coordinates.

ArcTerrainRenderObject's primary vtable is `0x01549f88`: complete-object locator
`0x015946a8` has subobject offset zero and type descriptor `0x016d77d0`.
Other vtables for this class have nonzero subobject offsets and are not accepted
as the source layout. Staged polling gates this primary class and brackets root
association separately from the longer, independently checked source/mesh read.
