# Carpenter discovery - September 24, 2026

## Verified scope

The current VM session uses client 1.3.38.11, native 1.8.27 and host 0.3.47,
with prepared executable SHA-256
`7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f`.
The user has a Bench contract and the Furniture Placement window open at a
Feudal Mercantile with a Carpenter hireling. Exact process lifetime, character,
HUD ownership and object references were checked before observations/input.
Session-specific identities and screenshots remain private.

- The floor plan is loaded and the native building floor count is one. Current
  Level displays 1, corresponding to native index 0. Up/down reject out-of-range
  levels, so their lack of movement is expected here. The center button's own
  click action has not been qualified.
- The deed list owns a valid furniture entry backed by an ArcDeed and
  ArcStaticObject. Its nested draggable control is named LIST00; the empty outer
  row name is expected and is not evidence of a defect.
- The user reports that dragging from the Furniture Placement deed list does
  nothing. Earlier observations found both native list and HUD selection empty;
  those observations alone do not prove which input event failed.
- One guarded ordinary left click on the visible Bench icon selected both the
  native list row and the matching HUD entry. The screenshot then displayed
  "Furniture deed for Bench". No drag/drop or Accept was performed by that test.
- Actor pose-parent and HUD destination point to the same native building.
  An exterior-looking camera view is not evidence that the actor is outside.
- A bounded, reverse-rechecked resource snapshot from the graphics task's
  published helper found the selected Bench's render root, template, mesh and
  texture-set references. Root has no children, unit scale, identity quaternion,
  and local/world translation approximately (0.001, 0.001, -0.001). An unreviewed
  texture class was reported without following assumed fields. Copied references
  are not renderer ownership, resource readiness or permission to draw.

## Placement boundary

Static inspection of this exact executable identifies selection callback RVA
`0x592b80`, setter `0x592bc0`, drag acceptance `0x592850`, drop `0x592970`, and
manager handler `0x6e7560`. Drag acceptance requires a LIST00 control and matching
native selection. The drop path also checks control ownership and floor-plan
coordinates. A valid manager result sends ArcFurnitureMsg operation 3 immediately.
**Accept is not the only potential placement boundary.** Invalid native locations
have a "Bad location, cannot place furniture there." path.

A successful single click narrows the investigation, but does not establish that
click-before-drag fixes placement or that the server accepts the request. No
placement message receipt, consumed deed, placed Bench or persistence after
reopening has been confirmed. Static input tracing indicates row selection occurs
on left press (handler `0x5fa190` through generic dispatch `0x5fb650` and row
handler `0x61c6e0`), before release. Therefore a separate completed click is not
established as a native requirement; click-then-drag is a diagnostic sequence, not
a proven root-cause fix. Drag startup conditions remain under review.

## Follow-up after the selected-deed drag

The user retried and reported "Done Loading" with no visible change. A fresh
read-only snapshot and screenshot show the same Bench deed key, source model,
building and floor; however, the owned list row and entry were reconstructed,
and list selection, HUD selection and scene selection are all zero. The same
Bench remains listed and the floor plan shows no obvious placed item. This
establishes a reset/rebuild rather than an unchanged selection, but does not prove
whether a placement request was sent, rejected or completed.

Static receive handler `0x3f68f0` handles ArcFurnitureMsg operation 2. Its nonzero
`message+0x94` branch calls `0x6e6f40`, which refreshes the building/floor view,
sets "Done Loading" through `0x593150`, then calls `0x6e7180` to rebuild deeds.
Rebuild invokes HUD virtual `+0x208`, reaching `0x592800` and clearing selection.
The setter's only identified direct/thunk caller is this refresh path, and the
refresh helper's only identified direct/thunk caller is the incoming handler.
This strongly supports a response-driven refresh, but no message payload was
captured. The status text alone is not placement success.

A subsequent bounded, reverse-checked capture found the scene list at `HUD+0x444`
empty and the furniture map (`HUD+0x664`, count at `+0x668`) empty with null root.
Manager keys at `+0xf0` and `+0xf8` both match the occupied destination building.
There is no retained placement entry in this HUD, rather than merely a hidden
entry. This does not prove that the server sent zero furniture records: handler
`0x593360` inserts the scene tracker and furniture record only after setup
`0x68bf60` succeeds; native asset-creation failure can discard an incoming record
before insertion. The next discriminator is the response payload and setup result,
or corresponding server logs. No unsupported server-fault claim is established.

The operation-2 handler iterates scene-record pointers at message `+0x98..+0x9c`
and consumed-deed keys at `+0xb0..+0xb4`. The refresh flag being zero does not skip
records; failed building initialization can skip them, but the observed Done
Loading path indicates that initialization succeeded. Both collections require
strict type, pointer, cycle/count and reverse-read checks before interpretation.

Private follow-up evidence: `after-user-drag.json` in the guest investigation
folder, followed by `after-drag-manager-keys.json` and
`after-drag-scene-state.json`; `after-user-drag.png` and
`after-user-drag-detail.jpg` remain on the host. No
additional game input or placement request was sent by the coordinator.

## Parallel ownership and delivery

The user-requested graphics task owns `codex/furnishing-preview`,
[draft PR #35](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/35).
The resource reader exercised here is source
`a98a9d39d79a7ceb0535c24183ae84ee7f56a283`; its task reports 115 focused tests and
Ruff passing. The coordinator reviewed the two helper modules and executed them
transiently using the existing read-only process-memory API. No wheel/DLL was
installed, native function invoked, or game memory written by that snapshot.
Native clone eligibility, resource lifetime, queue ownership, rendering integration
and visual acceptance remain in that task. Preview scope follows the actor's
occupied building/floor and clears when that context changes.

This documentation branch targets `main`. Main remains the normal clean checkout;
no branch or worktree is retired. Private evidence stays under the host's
`artifacts/carpenter/20260924` and the existing guest runtime's
`carpenter-investigation/20260924` directories, including selection screenshots,
selection receipt, occupancy transforms and selected-resource snapshot. These
captures, helper launch scripts and client binaries are excluded from delivery.

## Next todos

1. Active: qualify request/response evidence or obtain matching server logs after
   the selected-deed drag reproduced a reset with the Bench retained and scene
   collections empty. Distinguish missing response records from failed client
   asset creation before choosing a fix or server escalation.
   Verify persistent placement before claiming carpenter usable.
2. Continue graphics implementation and qualification in PR #35, using native
   ownership and occupied-building evidence. No speculative render hook deployment.
3. Release the serialized VM client for pending Barracks/guard/Condemn coverage and
   vendor recipe/Inventory navigation observations. Existing transaction journals
   and jobs remain preserved; no older request is replayed or automatically rebound.

See the [catch-up plan](../catch-up-plan-20260923.md) for the remaining production
vendor scheduler, affix/resource/disposal/recurrence and guard/rank acceptance scope.
