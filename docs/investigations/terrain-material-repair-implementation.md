# Terrain material coverage repair implementation

This branch implements the evidence-selected correction for terrain tiles whose
centers fall on a strict region boundary while an exact registered material-map
tile exists for the same world terrain key.

## Scope

The implementation does not alter region containment, terrain height samples,
terrain geometry, collision, zone ownership, or cache/archive bytes. It changes
only the material-region argument supplied to the stock material append routine,
and only after the following gates pass:

- the complete executable SHA-256 and PE image identity match the reviewed client;
- fixed code signatures match the reviewed builder, registration, append,
  finalizer, image, and lookup routines;
- the untouched builder and finalizer vtable slots match their reviewed thunks;
- the current material owner has no exact registered stack for the requested key;
- exactly one captured registered region has a complete exact stack for that key;
- the existing unpruned stack has no partial, reordered, duplicate-mask, or
  conflicting-color overlap;
- all candidate registrations use ordinary paired color/mask vectors within the
  reviewed bounds.

On any ambiguity or validation failure, the stock arguments are left unchanged.
The inserting lookup at `0x69f5a0` is never used for probing; the adapter walks the
bounded map read-only and requires one exact key match.

## Ownership and lifecycle

The replacement occurs before the stock append call. The stock builder therefore
publishes the selected stack using its normal construction path, and the stock
finalizer receives the restored layers before pruning and before it creates its
separate GPU-facing alpha images. The extension never sets the mutable flag on an
archive-backed image, never uses the shallow texture clone as a pixel copy, and
never writes shared archive pixels.

Registration and append entry hooks use generated x86 ABI bridges derived from
the exact reviewed executable. Inline patches verify complete instruction
boundaries and exact prologue bytes. The builder vtable change uses
compare-and-swap ownership. Hook removal restores only the extension's own patch;
a conflict is reported and never clobbered.

The full-renderer DLL queues initialization outside loader lock and pins itself
before installing client hooks. Diagnostics-only targets do not receive the
sources or enabling definition.

## Tests

The native policy tests cover complete, absent, partial, reordered, duplicate,
wrong-color, nested, sibling-ambiguous, unsupported-mode, rotation, malformed
region-tree, and capacity cases. Transaction tests cover complete preparation,
invalid ownership proofs, preparation failure, reserve failure, paired append
rollback, and quarantine on rollback failure. Hook and exact-client verification
have platform-specific fail-closed tests.

Live visual acceptance remains separate from source validation. The rejected
material snapshot 6 is not used by this implementation or its acceptance model.
