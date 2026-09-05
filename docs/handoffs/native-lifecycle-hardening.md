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

## Manager checkpoint 2

Launch polling no longer owns the dashboard, live-configuration, session or lifecycle-supervisor global lock. Session reservations exclude duplicate start/attach; supervisor retains launch receipts on failed attachment. Periodic supervise() is separate from dashboard response construction; dashboard health inspection does not renew permits. Renewal and shutdown serialize, actions use per-slot ownership, and capacity replacement excludes in-flight lifecycle actions. Manager CLI dependencies now resolve in their owning module without facade namespace mutation.

Worker controller reserves a launch in a durable node-local file under the existing interprocess record lock, before process creation. It retains PID plus verified creation time and a reserved worker token (passed through the existing worker command), allowing exact stop routing before heartbeat. Unknown attachment remains an explicit .launch-reservation record and blocks duplicate launch; do not delete an unresolved reservation based on heartbeat expiry. The controller waits for actual old-process exit before replacing it. Heartbeat closure is one serialized terminal transition. Terminal history remains available and does not consume the active-record limit.

Validation: 234 manager/ownership/CLI tests plus 155 subtests passed. Includes two independent controller processes racing to launch one real child with no heartbeat, pre-heartbeat exact stop request, unverified attachment retention, blocked launch across application/session/supervisor/live configuration, stale-running worker, close/publish race, and terminal-history reload. Remaining: review reservation crash/recovery surface, exact launcher/panel cleanup, operation store transitions and broader combined gates. No package identity is issued for this intermediate checkpoint.

Next active todo: integrate available shared feature dependencies, then transactional navigation persistence and simulator/planner findings while cue material coverage continues with its owner.
