# Selected-character cue — active implementation

Base: `14d117e8c5194c6dff55dac608b2d3f683187d31` (owner-pinned).
Branch: `codex/selected-character-cue`; initial PR destination:
`codex/navigation-inspector`, dependent on PR #27. The native lifecycle/runtime
hardening developer owns combined integration. This branch must not deploy the
shared client/VM or merge main. Navigation acceptance is retained, not reopened.

## Current work

- [x] Isolate the pinned source in a separate worktree.
- [ ] Implement verified selection/render ownership, silhouette and direction cue.
- [ ] Integrate settings, lifecycle, regression tests and actual package wiring.
- [ ] Verify both native profiles and the committed package.
- [ ] Reconcile with the integration owner's candidate and verify combined source.
- [ ] Provide one consolidated live acceptance procedure and exact source/package IDs.

This is an implementation record, not a feature-completion claim.

## Ownership evidence

Inspected the existing private updated official client in place. SHA-256:
`feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff`.
No binary is committed. Addresses below are RVAs, preferred base `0x400000`.

- ArcCharacter's render interface is its `+0x44` subobject. Routine
  `0x78AE0` subtracts `0x44` to compare with the local ArcCharacter. It loads
  `[interface+0x7C]`, hence `[character+0xC0]`, into EDI and passes it as ECX
  to thunk `0x269E0` at `0x78C66`.
- That thunk enters `0x1CB100`. It assigns this render object to the pooled
  ArcCharacterRenderWrapper's `+0x1C` at `0x1CB16A`. It recursively queues
  render-object children from the pointer vector `[render+0x3C, render+0x40)`.
- RTTI identifies wrapper vtable `0x1149ED0`; virtual render slot `+4`
  is thunk `0x26D91`, entering `0x1C8A90`. This reads wrapper `+0x1C`
  and calls the existing renderer through thunk `0xFFB0`.
- Main scene queue drain `0x79C730` calls each queued wrapper's virtual `+4`.

This establishes a structural ownership path, unlike draw-class, texture,
distance or transformed-position matching. Runtime guards still need to verify
the exact executable, code and stable pointers. Same-address reuse must also
check the existing object type/UUID fields and selection lifetime.

## Intended presentation

Highlight visible character coverage only; obstacles hide it. Occlusion does not
make an in-view character off-screen. A separately projected direction indicator
chooses the shortest horizontal camera turn, retaining its side near the exactly
behind-camera tie. Appearance and enable settings belong in Graphics Lab.

Investigating a depth-change silhouette captured around an owned render wrapper:
it would observe the original draw once rather than invoke character rendering
twice. Final scene depth must reject later occluders. Coverage of materials that
do not write depth must be evaluated explicitly, not silently claimed complete.

Shared changes will be limited to renderer connections, startup/cleanup, Graphics
Lab tab connection and CMake. The particles developer is extracting the existing
navigation GL guard; coordinate reuse rather than introducing a second guard.
