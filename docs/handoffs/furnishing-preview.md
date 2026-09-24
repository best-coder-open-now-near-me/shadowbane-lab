# Furnishing preview: renderer discovery and handoff

## Status and delivery

Source branch `codex/furnishing-preview` starts at freshly fetched
`origin/main@a91dfd58322f6489bd49eccbb69e6db32c3a1bc5`. Integration destination:
[draft PR #35](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/35) into `main`. This lane owns graphics discovery and the read-only
furnishing observer; the coordinating carpenter task owns the live VM and
ordinary selection/drop diagnosis. No preview renderer is enabled or deployed.

The client already loads the actual furnishing model for its inventory row.
Its existing Furniture Placement display is a floor image plus oriented bounds,
not a full 3D view. Reusing those native assets is feasible in principle. A safe
render-only model submission and lifetime contract is still required before
showing the model at a proposed placement. Do not call placement to manufacture
preview state, or treat a successful model load as server placement.

## Inspected inputs

Read-only static image: official client 1.3.38.11, SHA-256
`6347b420c6c151995f168f16fd1624408dd8911698d11a4a74b26d211fb49f19`.
Its prepared counterpart is
`7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f`;
see [the client identity review](../client-update-20260924.md). The observer
admits only these two hashes, not the broader historical vendor family.
All addresses below are RVAs relative to the loaded image base; private
analysis uses preferred VA base `0x400000` and subtracts it for this table.

The reviewed local original and changed caches reside under
`E:/Projects/shadowbane/artifacts/guard-deploy/client-update-20260924/official/`.
Task-generated string/xref/disassembly scripts reside in this worktree's ignored
`artifacts/furnishing-preview/`. These private inputs and analysis outputs are
not distributed with source. No VM process, settings, assets or contract was
changed by this lane.

## Native contracts found

| Boundary | RVA / field | Observed behavior |
| --- | --- | --- |
| Furniture HUD | vtable `0x1167c68`; constructor `0x592350` | Inherits prop-layout HUD; initializes selection to null |
| Row class | vtable `0x1169908`; constructor `0x5c27b0` | ArcFurnitureEntry, kind `0x25` |
| Row selection | `0x592b80` -> `0x592bc0` | Reads list selection, stores HUD `+0x660`, updates TXTDETAILS; no ghost placement |
| Selected deed row | HUD `+0x660` | Borrowed row pointer, distinct from scene selection at `+0x508` |
| Deed/model references | entry `+0x20` / `+0x24` | Reference-managed source and loaded furnishing object |
| Row model loader | `0x5c2a80` | Obtains actual furnishing key, loads object, retains it in row `+0x24` |
| Furnishing key getter | `0x5c2c50`, wrapper `0x5c2c90` | Copies key from source object `+0x7b8`; requires typed source ownership before use |
| Generic object factory | `0x51c510` | Resource lookup/creation and state initialization; not established as a pure render API |
| Native destination | HUD `+0x64c` | Retained structure reference (setter `0x68b540`) |
| Floor | HUD `+0x628` | Zero-based internal selection; displayed floor adds one at `0x593270` |
| Layout area | `+0x648`, `+0x630/+0x634`, `+0x638/+0x63c` | BTNPROPLAYOUT, width/height and offsets; zoom `+0x37c` |
| Layout drawing | `0x68b050` | Scissored floor image followed by existing scene-entry bounds |
| Furniture bounds drawing | `0x68c830` | Uses native object bounds/orientation and immediate-mode lines, not textured meshes |
| Screen to floor | `0x5936d0` | Uses HUD mapping `0x68acb0`, selected structure level, floor lookup `0xf7e30`, height `0xeb0e0` |
| Scene object creation | `0x68bf60` | Native factory, object registration/attachment, optional selection and native references; unsafe as an assumed detached preview API |
| Drag/drop | `0x592970` | Checks LIST00/parent/layout/selected row then calls placement handler |
| Placement handler | `0x6e7560` | Resolves floor point, builds FurnitureMsg operation 3 and dispatches; this is a server mutation |
| Existing move/rotate state | `0x5937b0`, `0x5937e0` | Marks scene entry dirty before inherited operation; must not repurpose committed-object edits as preview |

The floorplan and ordinary placement transforms are building-local; no world
translation/yaw composition has been qualified for a new renderer. Do not copy
floor coordinates into a world draw or assume the native rotation unit/sign.

## Asset findings

The current CObjects cache contains separate bench props and bench deeds. For
example prop `0:622657` is named Bench and points to Render `0:622657`, while
deed `0:960047` is also named Bench but points to Render `0:626` (the deed
appearance). Stone Bench, Long Bench, Pine Bench and other variants coexist.
Names cannot identify the user's intended model. Use the owned row's source
furnishing key and actual model reference; preserve the two-word key order.

The coordinator subsequently confirmed the owned ArcDeed key as `622657:0`.
The client key is `(id,type)`; archive notation below is `(group,resource)`, so
this resolves to CObjects `0:622657` -> Render `0:622657` -> Mesh `0:622894`.
The current render metadata has unit scale, translation approximately
`(0.001,0.001,-0.001)`, no children, and collision/bounds enabled. Mesh bounds
are approximately `(-1.575,0,-0.688689)` to `(1.575,1.147893,0.715165)`.
These are asset coordinates, not world placement or a server validity verdict.
The material prefix identifies one mesh, no specular texture, no decal or
backface doubling, and one type-1 texture `0:622505` with transparency 0,
wrapping and mipmapping enabled. This resource has a 26-byte header followed
by exactly 256x256x3 bytes. Native channel order, UV orientation and material
application still need qualification; no appearance has been visually accepted.

The mesh prefix contains 106 vertices, 106 normals, 106 UV pairs and 62 triangles.
All checked floating-point values are finite, every index is within the vertex
array, and computed vertex extrema match the stored bounds. These private
parsers leave five Render bytes and 530 Mesh bytes uninterpreted. This is a
qualified identity and partial geometry/material audit, not a complete loader.

All four inputs match the retained September 24 official manifest. A fresh
anonymous fetch of the official manifest during this investigation returned
identical entries for these four archives:

| Input | SHA-256 | Retained original location |
| --- | --- | --- |
| CObjects | `f168b71c63b0f4affb8f53f8f970f9b555309ba6ead095e6e365b9be56b3843f` | September 24 official cache directory above |
| Render | `5dd78baa0c5ae867e720ec05ba184624ad6dff363a576f48f941100d2e7d3667` | `E:/Projects/shadowbane/artifacts/guard-deploy/client-update-20260919/official/cache/Render.cache` |
| Mesh | `136f6625faa98a13378274d044d2d5f6920babbb1cb84f2547ecdacbc24e4993` | `E:/Projects/shadowbane/artifacts/Mesh.cache` |
| Textures | `1a142d73f8e1ef9bed8b56ef3a238203bc16a1da6df9c69b5ca625652d0d968a` | `E:/Projects/shadowbane/artifacts/guard-deploy/client-update-20260919/official/cache/Textures.cache` |

The old top-level artifact Render.cache and Downloads Render.cache failed this
identity check and were excluded. Private `bench-asset-chain.json` in the task's
artifact directory retains the exact decoded values and source paths.
`bench-material.json`, `bench-mesh.json` and `bench-texture.json` preserve the
prefix audit; `current-official-manifest.json` preserves the fresh identity
reference. Reproduction helpers are `bench_chain.py`, `qualify_material.py`,
`bench_texture.py`, `audit_assets.py` and the thunk-resolving `method.py` there;
they use the existing private parsers under `E:/Projects/shadowbane/artifacts/tools/`.
The extracted texture payload remains private in that same task directory.
No cache
bytes or client geometry are published in the PR.

Five Feudal Mercantile entries (`0:596000`, `0:596400`, `0:596800`, `0:882000`,
`0:884400`) have a null primary render in the shared CObject prefix. A building
is not a single mesh obtainable from that prefix. Reuse the native destination
structure and level geometry after reviewing its lifetime and draw contract.
The existing Python object-navigation decoder provides collision metadata,
not a textured 3D asset loader or an authoritative placement validator.

## Native draw side effects

Static review found concrete reasons not to replay the row model's native draw
as an assumed detached preview:

- ArcStaticObject's secondary interface at object `+0x44` has vtable `0x114350c`.
  Its `+0x0c` slot reaches `0xe9910` and the general render walk `0x3b300`.
  It is not established as a pure, independently positioned submission.
- Producer `0x1cb100` allocates a global render wrapper, stores a raw render
  pointer at wrapper `+0x1c`, and traverses child render objects. No scoped
  retained preview handle has been established on this path.
- Wrapper `0x1c8a90` calls native preparation `0x1cd970`, changes native render
  state, and writes render `+0xec` from wrapper `+0x18` before draw `0x1cb700`.
  Replaying it therefore mutates the shared render object.
- Draw `0x1cb700` loads matrices using native camera state and changes the
  native `GL_NORMALIZE` tracking global (preferred VA `0x1788c20`) according to
  scale. Restoring driver GL state alone would not restore native caches.

The existing `RenderSceneGeometry` callback contract requires a reviewed caller
boundary and balanced matrices/framebuffer handling; it does not grant native
model ownership or make these methods pure. The existing world composition
safety check also states that no supported late path establishes complete native
foreground coverage. A late ghost overlay cannot assume correct occlusion merely
because a camera snapshot is available.

Orientation getter `0xccee0` follows the object pose reference at `+0x4b0` to
float `+0x110`. Transform helper `0xd5f30` copies a native transform, invokes an
imported inverse, then transforms a point. These are leads for proving coordinate
composition; native rotation units/sign and complete world/local conversion
remain unresolved. No guessed transform is delivered as rendering behavior.

## Delivered observation boundary

`read_native_furnishing_preview` is a bounded, read-only diagnostic. It follows
the reviewed game root -> active HUD list -> city manager -> Furniture HUD ->
owned list controls -> typed entries. It reports null/unselected/loading states,
raw row identity, source/model references, layout/floor and scene selection.
Copied bytes are rechecked in reverse order. It refuses unknown executables,
ambiguous HUDs, detached/duplicate entries and malformed pointers/geometry.
It never dereferences unknown model/source layouts beyond their class word.
For the verified ArcDeed class (`0x1142468`) only, it also copies the furnishing
key at `+0x7b8`. The live model class is ArcStaticObject (`0x1143540`); model
geometry pointers are not exported or retained. List selection (`list+0x404`)
and HUD selection (`HUD+0x660`) remain distinct observations.

The continuous recorder has an explicit `--furnishings` option. Use it only
with the existing exact process-ID/creation-time arguments and private output
location, serialized by the VM owner. The recorder does not install a hook,
invoke the factory, retain objects, move/rotate, or issue messages. Samples are
not atomic native leases and cannot prove that an address was not reused.
`preview_pose_verified`, `render_lifetime_owned`, `placement_confirmed` and
`command_admitted` remain false. A native scene entry is not a server receipt.

## Durable implementation boundary

1. The owner-update phase owns selected row, exact building/zone/floor and the
   candidate pose. Reuse the verified ordinary coordinate conversion, then
   establish the local-to-world transform and native orientation convention.
   A pose update must never invoke the commit handler or dirty an existing prop.
2. Prefer the row's loaded model after proving its render-only submission and
   retaining it under the native owner lifetime. Review whether a detached render
   instance is necessary; never change the shared object's transform/material.
   Cache per selection/model/context, not per frame. Loading stays outside draw.
3. Publish one immutable, generation-tagged preview snapshot. The renderer owns
   GPU resources only in its current context. No borrowed external-reader pointer
   may become a renderer handle. Cancel on row/deed/structure/floor replacement,
   HUD close, logout, scene/context loss, extension stop or explicit Cancel.
4. For an in-world ghost, use the existing reviewed world/pre-UI boundary in
   `cel_shading.cpp`, `SceneFrameState`, the same-context camera, and shared
   `RenderCallbackLease`/`RenderLifecycleMutation`. A full building cutaway pane
   needs its own reviewed viewport/camera/depth target; it cannot masquerade as
   the main world camera. Choose this presentation with the owner after actual
   geometry can be rendered safely.
5. Preserve depth testing/occlusion and all GL state (including framebuffer,
   viewport/scissor, matrix stacks, texture/client arrays and fixed-function
   caches). Distinguish the candidate with a clear Preview label and orientation
   cue. Existing transparency diagnostics do not qualify a translucent ghost;
   do not depend on the suppressed selection-mask path. Reuse actual materials
   or a separately validated preview treatment.
6. Confirmation remains the ordinary exact-building server transaction owned by
   the carpenter lane. Local validity is advisory; only an attributed server
   response plus refreshed structure state can confirm placement. Clear the
   preview when committing and preserve uncertainty without replaying placement.

## Evidence and validation still needed

The coordinator observed a rendered floorplan, internal floor 0/display floor 1,
400x400 layout at offsets (64,54), one kind-0x25 row with key5017277:30, and a null
HUD selection despite reported dragging. The row already has non-null source
and model references (ArcDeed and ArcStaticObject respectively). Both list and
HUD selection were null in the coordinator's stable sample. This is separate
from adding a 3D preview. The unnamed
outer ArcListControl is expected; the nested LIST00 drag control must be checked
by the ordinary-workflow lane. No correction to naming or input is inferred here.

The coordinator additionally qualified the current structure class as
`0x1177c0c`, with one available floor. Getter `0xf2990` computes count as
`(model[+0x738] - model[+0x734]) / 4`; raw floor 0/display floor 1 is in range.
Commands 373/374 in `0x6cb130` use bounds `0x68d680`, update `+0x628`, recalculate
via `0x68b9e0` and refresh the label via `0x593270`, without writing row selection
`+0x660`. Both arrows are unavailable for this one-floor building. This rules out
an out-of-range selected floor for that sample, not placement invalidity generally.

Next serialized evidence: select a row without dropping; compare `+0x660`, model
and source class/key, then close/reopen. Floor-change acceptance requires a
separately qualified multi-floor destination. Verify exact destination
structure identity/template/zone; do not identify it by its display name. Static
review must then finish render-only submission, retained model/structure lifetime,
local/world transforms and cancellation before a native preview hook is authored.

Runtime acceptance must demonstrate the correct furnishing in the correct
building/floor, orientation and position following the candidate, clear Preview
status, cancellation, row changes, context loss and reopen; no placement messages
may occur before explicit confirmation. Compare GL state and performance with
preview disabled and exercise both native profiles. A successful observer or
unit test does not satisfy these visual/server gates.

Source validation: 51 focused observer/recorder tests passed, plus Ruff. These
include both admitted hashes, changed selection/reference/geometry rejection,
detached ownership, duplicate HUDs/rows, loading states and short reads. No native
DLL was changed, built, deployed or visually qualified at this checkpoint.

Full host validation passed **3,427 tests**, **20 skipped**, and **756 subtests**;
repository-wide Ruff passed. Recorder help exposes `--furnishings`. The new reader
itself has not yet been run against the live process; the coordinator's independent
samples qualify the listed field observations, not this implementation end to end.
PR #35 remains draft; hosted checks are tracked on its exact head. No merge is implied.

Remaining todos: coordinator-owned single-row selection and observer qualification;
reviewed detached render submission/lifetime and transform proof; then implement
and visually qualify the actual real-time preview. Ordinary placement repair is
owned separately. No branch or worktree is retired while these tasks are active.
