# Runtime hardening and combined integration

Active branch: `codex/native-lifecycle-hardening`; separate worktree `.worktrees/native-lifecycle-hardening`.
Exact starting source: `14d117e8c5194c6dff55dac608b2d3f683187d31`.
Integration destination is this branch for the batch, then reviewed integration toward `main`; no main merge or VM deployment is authorized here.

Shared ownership: initial repairs touch performance_telemetry.cpp, graphics_status.cpp and production lifecycle tests. Extension startup/rollback and cel_shading scene connections follow. Feature owners were notified in their existing tasks on September 5.

Lifecycle contract: admitted callbacks retain their resources and original call-through through return; restored hooks must still support already dispatched callbacks. Publisher timeout retains thread/events/backing state and prevents replacement generation until confirmed exit. Start/stop ownership is serialized. No hot unload, loader-lock waits, or GL deletion from a non-owning context.

Reuse particles scene_draw state guard and effects_attachment observations; selected cue retains its separate verified rendered-object ownership. Proposed ordering: scene composite, selected cue, particles, navigation, UI. Feature owners retain complete feature delivery and can continue independently.

Todos:
- [ ] Active: native teardown and manager dispatch/renewal isolation with regression tests.
- [ ] Worker/process ownership and transactional durable stores.
- [ ] Simulator correlation transaction and public planner correctness/performance.
- [ ] Reconcile both feature heads and shared integration.
- [ ] Combined gates, exact clean source package and installed controls verification.
- [ ] Consolidated acceptance handoff with exact identities and remaining live checks.

Each validated coherent repair is a commit checkpoint; publish source normally under AGENTS.md. Preserve private artifacts under ignored artifacts/. Existing feature package receipts do not certify this candidate.

## Native checkpoint 1

Implemented telemetry callback leases (including recursive CRT/Win32 entry), serialized storage mutation/start/stop, retained original API call-through after restore, and old-present rejection against the mapping start timestamp. Graphics publisher now serializes lifecycle ownership, retains timed-out thread/events/state, rejects replacement until confirmed exit, and protects event signaling against closure.

Verified production full Win32 Release DLL build and existing graphics_status/performance_telemetry CTest targets (2/2). Added held-original-callback and publisher startup-rollback/stop timeout barriers to those production tests. No loader-lock shutdown or hot unload added. Remaining native work: renderer/cue call-through, shared startup rollback and scene/context reconciliation; broader profile gates run against combined source.

Feature confirmations: particles `21e884b1c220ff072e15e83c0bd87166d1d9a012` (tested code `e1add65b4368a3eb1c5a10c1ccd70f23521c4130`); cue `7cc91b30ea4b9de57a43fd7d9f51db3c8d227519`, still developing material coverage. Both confirmed proposed scene ordering. Their package receipts are evidence for those exact feature sources only.
