# Passive native input diagnostics

This trace explains admission and ownership changes; it does not change movement,
release, re-arm, UI exclusion or command ownership. It requires the existing
`WONDERBANE_MOVEMENT_TRACE=1` opt-in at client startup. The integration owner owns
combined packaging, installation and any connected observation. No Python worker
or trace collector is required for manual controls.

## Version and compatibility

The schema-2 mapping is
`Local\ShadowbaneLab.Extension.MovementBoundary.v2.<PID>.<creation FILETIME>`.
Its magic is `WBMVTR2`, with a 48-byte common header, input event sequence at byte
48, current input record at 56, retained owner-loss record at 160, 256 input event
records at 264, and the existing 256 native boundary records at 26888. Input records
are 104 bytes; boundary records remain 72 bytes; the complete mapping is 45320 bytes.
The separate mapping name prevents old readers interpreting a new layout. Movement
command Status, its flags, size and zero-reserved-byte contract are unchanged.

The packaged collector supports both versions explicitly:

```powershell
python -m shadowbane_lab.client_extension.movement_boundary --schema 2 --process-id <PID> --creation-filetime <FILETIME> --seconds 180 --output <private-new-output.jsonl>
```

Use `--schema 1` for an older installed client, including 1.7.3. The collector does
not silently fall back to an old schema. It verifies exact PID/creation and accepts
only committed records identical across two independent reads. Output is private
native diagnostic evidence, not a source artifact to publish.

## Reading input records

`kind` 1 is an owning-update sample, 2 is an ownership revocation, and 3 is a native
keyboard-callback consumption decision. `tick_ms` timestamps observation;
`sample_tick_ms` timestamps the last owning-update input sample. `interval_ms` is
the interval between those samples, not host collector time. A window callback can
occur between samples: its gate bits may be older than its event, and must not be
presented as contemporaneous. For kind 3 only, the key-down mask is freshly read
at the consumption decision. Suppressed/original-down masks are observed at event
publication. No arbitrary keyboard text or automation identity tokens are recorded.

The four key-mask bits are configured forward=1, backward=2, left=4, right=8.
`key_event` has direction index+1 in its low three bits, down=8, repeat=16, and
consumed=32. Non-consumed records describe the decision to call the original native
handler; they do not certify which in-game action it eventually executes. These
records are produced even when a second diagonal key does not change ownership.

Gate bits: capture succeeded=1, native update phase=2, exact foreground=4,
UI owns input=8, camera basis valid=16, native available=32, feature enabled=64,
scene present=128, controller connected=256, pointer in world=512, capture valid=1024,
native camera gesture=2048.

Policy bits: keyboard armed=1, controller armed=2, drag armed=4, moving=8,
pending stop=16, faulted=32, available=64, foreground admitted=128, shutdown=256.
At a revocation these describe the policy at its Revoked callback; subsequent
inhibition or fault-latching may occur afterward. The following sample records the
resulting state. `reason` follows StopReason: release=0, takeover=1, focus=2, UI=3,
disabled=4, device lost=5, capture lost=6, scene changed=7, stalled=8, shutdown=9,
binding failure=10. Sample/key-decision records use UINT32_MAX (no stop reason).

The collector labels streams `current`, `events`, and `last_owner_loss`. Each has
its own sequence interpretation. The event ring retains key decisions, revocations
and changed input/policy snapshots, not redundant steady frames. The last revocation
from a nonempty owner is retained separately until another owner loss, even after
idle samples or event-ring overwrite. Sequence gaps and producer-dropped counts
must be retained when interpreting evidence. Readiness alone does not prove input
is armed or admitted, and later clear gates cannot explain an earlier loss.

## Validation and limits

Native tests cover W-to-W+D without a revocation, UI forwarding versus suppression,
UI loss versus a clock regression, admitted manual update gaps, retained loss after event-ring
overwrite, malformed diagnostic rejection, foreign-thread rejection and retired
publication. Runtime and native boundary executables both expose `input-diagnostics`.
The Python round-trip test reads the actual native producer layout; set
`WONDERBANE_MOVEMENT_BOUNDARY_TEST` to that profile's boundary test executable so
the interoperability check runs rather than skips. Schema-1, exact identity,
torn-read, ring-overwrite and invalid-record cases remain covered.

These are production composition tests with controlled native callees. They do not
identify the connected intermittent diagonal failure or establish connected input
acceptance. Next is independent integration review, the combined package's required
gates, and an integration-owner-managed observation of the actual failure.

## Remaining lifetime latch: source investigation

The source-only follow-up found no reproducible false invalidation of an unchanged,
established watch. Production lifetime tests exercise 1,000 unrelated actor-family
finalizers sharing the hooked vtable, unrelated world frees, a held unrelated free,
and a replacement pose wrapper that retains the same parent; all preserve epoch.
Each identity word and actor/parent/world/native-window change independently
retires the old epoch. An unreadable parent chain rejects capture, and restoring
the same tuple receives a new epoch. Existing destruction-before-original,
same-address reuse, held-original replacement, and arming/publication race tests
continue to pass. These are controlled native callees, not proof about the cause
of a particular connected event.

The parent is the native coordinate frame used for destination and camera-basis
conversion. A changed parent is not by itself a defect or spurious destruction;
ordinary movement may legitimately change coordinate frames. Existing evidence
does not establish that such a transition caused this latch. Any future continuity
policy must still retire old targets and automation grants and convert through the
new verified frame. This investigation does not change that policy.

`ObserveNativeMovementLifetime` can fail without advancing an established epoch
(for example rejected new-watch arming), while Runtime maps every failed observation
to scene zero and suspends input. Therefore an epoch-change-only diagnostic would
miss one class of input inhibition. Destruction advances before original call-through;
completion only removes the notice, and a later successful observation may advance
again. Logging only the successful replacement would lose the first cause.

Minimum diagnostic proposal before another connected observation:

- Record every failed observation and every actual invalidation/publication, with
  a monotonic sequence, observation tick, old/new observer epoch, and runtime's
  previously admitted epoch. Retain the first invalidation through subsequent
  unsuccessful observations and successful replacement.
- Use a cause enum for changed tuple, failed capture, actor/parent finalization,
  world deallocation, binding loss, rejected arming, terminal retirement and epoch
  exhaustion. For rejected arming distinguish active unrecorded callbacks,
  overlapping callback interference and matching in-flight destruction.
- Record a six-bit changed mask for actor, parent, world, native window and the two
  identity words. Emit no raw pointers or identity values. For failed capture,
  record the failed read/validation stage (window, receiver, mode, actor, world,
  identity, position wrapper, pose, parent) and which fields were valid; a partial
  capture must never produce a misleading changed mask.
- For an admitted destruction notice, record actor/parent/world role, captured watch
  generation, and finalizer flags. Match-role bits may include both actor and
  parent. Do not log unrelated allocation traffic or stack/memory contents.

Capture metadata at the existing observer lock/boundary, without adding gameplay
calls, changing return values, or holding an observer lock across trace publication
or native call-through. Export through the existing optional diagnostics path on
the owning update, preserving callback-safe bounded storage and first-cause
retention. Keep movement command/status schema and its reserved fields unchanged;
any diagnostic layout extension needs explicit versioning plus producer/reader
and retirement tests. No diagnostic implementation or new live run is part of this
source-only checkpoint; the integration owner retains review/package authority.
