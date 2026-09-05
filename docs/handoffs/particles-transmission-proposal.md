# Shared native transmission: representation review

Status: rejected by the integration owner; do not implement the fragment ledger.
The memory/cost and original-fragment capture contracts are unproven. Retained
only as a record of the mathematical requirements and rejected design. Not
implemented or acceptance-ready.
Applies to particles/trails and whole-character cue in the existing native renderer.
No new scene authority, hooks, standalone viewer, or capture framework is installed.
Combined reviewed checkpoint: `5519a8e4026136d04231c9c66cfe71fc23fdac97`.

## Minimum retained information

A frame-local fragment record must retain window-space depth, original source
RGBA, native draw/subprimitive order and an immutable blend-state index. Its
blend state must include RGB/alpha factors and equations, constants and channel
write masks. Native depth/stencil acceptance and pass identity must be preserved;
final depth alone cannot distinguish a depth-writing translucent surface from an
opaque occluder. Multiple overlapping fragments within one draw remain separate.
A nearest-depth/color texture, one alpha scalar, or before/after scene snapshots
cannot meet this contract (see production GL counterexamples in PR #28).

For validated alpha-over foreground layers, a resolver can derive foreground
color S(z) and transmission T(z) at each requested effect depth. General blend
operators remain ordered records until classified: observed ONE/ONE and
DST_COLOR/ZERO are not alpha-over; MIN/MAX and destination-dependent factors
cannot silently use a scalar attenuation formula.

Cue lookup uses the destination pixel and the retained depth of each contributing
owned-mask sample. Equal-strength halo samples can have different depths. Querying
at a neighboring pixel or using destination background depth is incorrect.
Particles can likewise occupy several depths at one pixel; a single attachment
or nearest-particle depth is insufficient.

## Bounded candidate, with explicit cost

One possible representation is a shared per-pixel fragment ledger backed by a
fixed pool. A 32-byte record and a 256 MiB pool allow 8,388,608 records, averaging
about 4.6 records per pixel at 1920x955, before per-pixel heads/counts, baseline
color/depth and scratch storage. Those buffers add tens of MiB. A separate local
count cap bounds resolve work. Both global and per-pixel exhaustion must reject
the affected frame's correction and publish diagnostics; dropping a layer is not
an acceptable approximation. Such rejection is a failure/recovery condition,
not evidence that the normal feature is usable under the configured budget.

This cost is substantial for the requested effects and has not been justified by
combined performance evidence. A ledger implementation must not be introduced
merely to make two-quad tests pass. Smaller storage requires measured coverage
and a proven conservative capture region; whole-character halo availability and
moving particles prevent assuming one tiny static rectangle.

## Unresolved implementation contracts

1. Original native fragment RGBA/depth must be emitted without changing material
   semantics. Synchronous arrays/MultiDraw replay preserves argument lifetimes,
   but does not extract every overlapping fragment. Substituting a new fragment
   shader loses original texture/program output unless equivalence is established.
   A new GPU atomics/image/SSBO path would also require capability, program and
   state integration beyond the existing guard; it is not authorized by this
   proposal as a separate renderer.
2. The two verified immediate quad emitters provide bounded positions/UV replay
   through the existing cel capture. They do not prove all material paths or
   fragment coverage. List playback remains entry-state-only in diagnostics.
3. Native pass order is semantically significant. Sorting every native fragment
   by depth can reorder lighting/modulation passes. Preserving draw order alone
   does not place effects correctly among out-of-order foreground/background
   fragments. A verified material/pass ordering contract must define the merge;
   neither arbitrary depth sorting nor stable partitioning is presumed correct.

These are concrete blockers to a correct production split. A bounded storage
structure by itself does not resolve them. Do not assign cue/effects integration
against an assumed final interface until the shared owner accepts the capture
and ordering contracts and the budget is viable.

## Production regression required before delivery

Extend the existing native WGL harness against the actual shared capture/resolve
implementation. Keep the required gates failing until the production path passes:

- Effects in front, behind and between two native alpha surfaces, with both native
  depth-write modes; overlapping fragments within a single MultiDraw/primitive.
- Native ONE/ONE and DST_COLOR/ZERO passes, texture alpha/cutouts, color masks,
  depth EQUAL, stencil, and all supported program paths; unsupported paths must
  be explicit and must not be represented as successful capture.
- Whole-character mask and halo taps at distinct depths, multiple particle/trail
  depths at the same destination pixel, and no cue-driven self-occlusion.
- Disabled effects reproduce the original native framebuffer; enabled resolution
  preserves the documented native material/pass order and UI separation.
- Per-pixel/global overflow, unsupported submission, resize/context/scene changes,
  disable/re-enable and cleanup leave the game frame/state intact and expose the
  rejection; repeated transitions do not accumulate resources.
- Both native profiles and actual combined package, then combined steady-state
  frame time/resource measurements within the agreed shared acceptance plan.

No synthetic viewer or isolated model of the proposed ledger counts as passing
these production tests. No additional owner gameplay demonstration is requested.


Owner-directed next bounded work: validate synchronous source/depth capture for
the two verified native immediate quad producers using their actual material
state, without shader substitution, duplicate side effects, or multiplicity loss.
Any UV/BeginEnd work must extend existing cel capture under the shared owner.
This does not authorize a new ledger, renderer, or silently suppressed effects.
