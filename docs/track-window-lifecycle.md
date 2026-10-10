# Automatic Track window lifecycle

## Problem and intended behavior

Automatic Hunt Foe already copies native response contacts for awareness and
callouts. The ordinary client response handler also closes the preceding Track
panel, creates a replacement and opens it, so repeated automatic scans leave a
panel on screen indefinitely.

Automatic scans should maintain contacts without leaving their panel open.
Explicit manual Track should retain its normal panel until the user dismisses it.
The native result handler and copied contact publication remain unchanged; this
is a presentation policy, not query-response attribution or combat authority.

## Native ownership boundary

The existing admitted automatic Track action acquires scene-bound presentation
ownership. Once per scene, it can close an already-stuck Hunt Foe panel through
the native close operation. An ordinary unscoped Track send reserves manual presentation. That
reservation survives the response handler's internal close/recreate sequence;
an actual dismissal outside processing releases it. Owner retirement releases
automatic ownership, and scene changes invalidate the old scene's state.

After normal response processing, automatic ownership may close the exact current
Hunt Foe HUD. The native close operation performs parent and focus cleanup. The
extension must not set raw visibility flags, unlink controls, destroy the HUD
itself, skip native processing, or infer gameplay permission from presentation.
Manual activity or ownership changes during native callbacks prevent an old
presentation decision from closing the user's replacement panel.

## Reviewed native paths

The Track table is RVA `116fb58`; its close slot `10c` contains thunk `17440`
(`E9 2B DA 5D 00`), which jumps to body `5f4e70`. The slot is not a direct
pointer to that body.
`ArcTrackingListMsg::Process` is `3b2b30`. Existing Track send observation at
`9bea0` distinguishes an admitted automatic native frame from ordinary manual
entry. These spans match the reviewed official .16 and .17 images. Runtime
installation continues to require the exact supported executable identity and
loaded-code guards. Contact mappings and callout semantics do not change.

## Delivery status

Native implementation `090eb95a` is published on
`codex/track-window-lifecycle-20261010`, based on shared main. Both native
profiles built; all 12 focused tests and 31 actual-frame host tests passed.
Independent review passed, including the regression preserving a manually
reopened panel across owner reentry. Combined .98/.63 qualification, installation
and launch passed; PR #157 is merged. Live inspection then exposed a binding
regression: the direct-body slot check rejected the real native thunk, preventing
Track publication startup and leaving upkeep in `needs_attention`.

Reviewed correction `e8e3c042` on `codex/track-close-binding-20261010` validates
the actual slot, exact jump and body prologue, and still calls through the native
slot. The original synthetic fixture had invented a direct slot; it now follows
the real thunk. Exact-image binding cases run against original/prepared images
in both package profiles and reject changed slots, thunks and bodies. No lifecycle
or publication ABI changes accompany the repair. This source is planned for
.99/.64; live automatic closure and manual preservation remain unverified.
See the [delivery record](group-track-delivery-20261010.md).
