# Furnishing preview: renderer discovery and handoff

## Status and delivery

Source branch `codex/furnishing-preview` starts at freshly fetched
`origin/main@a91dfd58322f6489bd49eccbb69e6db32c3a1bc5`. Integration destination:
reviewed PR into `main`. This lane owns graphics discovery and the read-only
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

Five Feudal Mercantile entries (`0:596000`, `0:596400`, `0:596800`, `0:882000`,
`0:884400`) have a null primary render in the shared CObject prefix. A building
is not a single mesh obtainable from that prefix. Reuse the native destination
structure and level geometry after reviewing its lifetime and draw contract.
The existing Python object-navigation decoder provides collision metadata,
not a textured 3D asset loader or an authoritative placement validator.

## Delivered observation boundary

`read_native_furnishing_preview` is a bounded, read-only diagnostic. It follows
the reviewed game root -> active HUD list -> city manager -> Furniture HUD ->
owned list controls -> typed entries. It reports null/unselected/loading states,
raw row identity, source/model references, layout/floor and scene selection.
Copied bytes are rechecked in reverse order. It refuses unknown executables,
ambiguous HUDs, detached/duplicate entries and malformed pointers/geometry.
It never dereferences unknown model/source layouts beyond their class word.

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
and model references. This is separate from adding a 3D preview. The unnamed
outer ArcListControl is expected; the nested LIST00 drag control must be checked
by the ordinary-workflow lane. No correction to naming or input is inferred here.

Next serialized evidence: select a row without dropping; compare `+0x660`, model
and source class/key, then floor changes and close/reopen. Verify exact destination
structure identity/template/zone; do not identify it by its display name. Static
review must then finish render-only submission, retained model/structure lifetime,
local/world transforms and cancellation before a native preview hook is authored.

Runtime acceptance must demonstrate the correct furnishing in the correct
building/floor, orientation and position following the candidate, clear Preview
status, cancellation, row changes, context loss and reopen; no placement messages
may occur before explicit confirmation. Compare GL state and performance with
preview disabled and exercise both native profiles. A successful observer or
unit test does not satisfy these visual/server gates.

Source validation: 44 focused observer/recorder tests passed, plus Ruff. These
include both admitted hashes, changed selection/reference/geometry rejection,
detached ownership, duplicate HUDs/rows, loading states and short reads. No native
DLL was changed, built, deployed or visually qualified at this checkpoint.
