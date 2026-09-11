# Character-forward door interaction

Owner-authorized main gameplay mission: approach a door, identify/select it,
interact/open, and walk through. Camera-center aiming is explicitly rejected.
Selection must use the character's facing, independent of camera orbit, with a
short forgiving forward cone and a clear intended-door indication. Existing mouse
selection remains available. No guessed screen click or synthetic F implementation.

Implementation owner: existing codex/native-movement-controls branch; integration,
shared lifecycle, review and packaging: codex/native-lifecycle-hardening. Finish
verified native selection/interaction and tests before offering Interact in the
binding editor. Do not expose an unwired action. Combat hotbar expansion follows
this door mission. Remapping's reviewed supported subset is separate.

## Established evidence

Owner observed single-click selection without opening, then F opens selected door
on installed1.7.8, source97612e6. Saved character configs map F to native action10
with parameters0/0 and an empty argument. Read-only selection root observation at
RVA0x16a2da4 found vtable0x1143f18; static RTTI on exact reviewed prepared executable
identifies ArcDoorObject. Its primary complete-object offset is0. Capture includes
a brief character selection interval; do not infer continuously unchanged target.
Private capture door-selection-20260911-055813.jsonl is pointer observation only,
not a call trace or proof of controller actuation.

Static action10 dispatcher classifies selected door as class4, constructs a native
record1552 with real client-string ownership, and redispatches through the game
window. Door-specific action1552 performs structure/state checks and ordinary native
request lifecycle. Use normal action10 behavior; do not directly toggle door state
or call the lower-level message/state routine. Submission does not prove server
acceptance/opening. Root independently ran the existing static door-chain assertions
against prepared EXE SHA256
bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87.

Door position slot+0x58 is thunkRVA0x1b3ec ->0x10c130, not the existing character
reader's0xa3d0. It reads door+0xc0 and invokes the backing object's position path;
missing backing geometry returns a zero vector. Reject absent geometry instead of
treating zero as a valid world point. Do not apply character+0x4b0 position offsets
to doors. CameraBasis is camera-relative and cannot establish character facing.
No established bounded door/structure enumeration or actor-facing helper was found
in the committed observation readers. Zone rotation is not actor orientation.

## Active implementation and validation

Native owner is verifying bounded door enumeration, actor-facing/world-frame
geometry, obstruction and eligibility/range, plus admitted native selection and
action-record lifetime. Use existing client-thread/runtime ownership, fresh scene
and object identity; never store a raw target across lifetimes or execute on a
render/polling thread. Keep native range, locks, permissions and obstruction policy.

Required behavior checks: camera orbit does not change the character-forward
candidate; turning the character does; candidates behind/outside reach/obstructed
or lacking geometry are excluded; competing doors resolve deterministically with
visible intended target; no candidate means no unrelated selection/action; held
Interact does not repeatedly toggle; focus/modal/scene destruction and stale input
cannot act on replacement objects. Preserve accepted controller/chat, parent-frame
movement and ordinary mouse selection. Use developer-controlled fixtures and native
adapter tests before a targeted connected door check. No broad new live run is
currently requested. Door interaction is not yet delivered or installed.

## Bounded live world-table observation

Receipt-lifetime/hash-verified read-only observation found current selected door
absent by pointer from the proposed top-level world table: capacity512,140 occupied
slots,zero ArcDoorObject entries. One entry matched the selected door's eight-byte
native identity; its vtableRVA0x1177c0c statically resolves ArcAssetStructureObject
with complete-object offset0. All examined entries were readable, table bytes and
roots plus selected identity/vtable were stable in that observation. It was not
the door's geometry backing pointer. This supports a structure/child-door model;
it does not make the structure pointer interchangeable with the selected door.

Owner static child lookupRVA0xfa690 reads structure+0x748 vector and retains the
matching door. A subsequent bounded child-vector probe declined because current
selection was no longer a door; no live child membership conclusion is claimed.
No extra input/selection/writes were performed. Next: native owner verifies the
structure-child enumeration and actor-forward frame mapping, then implements the
admitted resolver/selection/interaction path. Current live test remains unnecessary
until a specific missing fact prevents implementation.
