# Runtime hardening and combined integration

Active branch: `codex/native-lifecycle-hardening`; separate worktree `.worktrees/native-lifecycle-hardening`.
Exact starting source: `14d117e8c5194c6dff55dac608b2d3f683187d31`.
Integration destination is this branch for the batch, then reviewed integration toward `main`; no main merge or VM deployment is authorized here.

Shared ownership: initial repairs touch performance_telemetry.cpp, graphics_status.cpp and production lifecycle tests. Extension startup/rollback and cel_shading scene connections follow. Feature owners were notified in their existing tasks on September 5.

Lifecycle contract: admitted callbacks retain their resources and original call-through through return; restored hooks must still support already dispatched callbacks. Publisher timeout retains thread/events/backing state and prevents replacement generation until confirmed exit. Start/stop ownership is serialized. No hot unload, loader-lock waits, or GL deletion from a non-owning context.

Reuse particles scene_draw state guard and effects_attachment observations; selected cue retains its separate verified rendered-object ownership. Proposed ordering: scene composite, selected cue, particles, navigation, UI. Feature owners retain complete feature delivery and can continue independently.

Todos:
- [x] Native telemetry/publisher teardown and manager dispatch/renewal isolation checkpoints.
- [ ] Remaining native scene/rollback integration with feature lifecycle repairs.
- [ ] Active: remaining worker/process recovery and transactional durable stores.
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

## Shared renderer and durable map checkpoints

Merged particles `21e884b1c220ff072e15e83c0bd87166d1d9a012` and cue `782aead36e0a010a0f57c7aa864e90c427f974c0` at combined `50ad9e1dd83a67de3bc814a098dc4230b0393299`. Cue material coverage and resource teardown remain with its owner; inclusion is not feature acceptance. Renderer checkpoint `8961fad07ff00c40b511f5b8f9562669069aad39` supplies one recursive callback admission/exclusive lifecycle boundary and retains restored original call-through. Full native CTest: 23 passed, binding test skipped without arguments; explicit private-client binding verification passed separately. Both installed feature smoke paths now suppress client discovery.

Sky and native movement owners start at published `0c807ee774859cc3f17f9ebc04d3f0a900bd0428` and target this branch. They are rolling additions: do not delay a complete particles/cue candidate indefinitely. Root retains shared scene/lifecycle and manager ownership reconciliation. Sky renders at verified early clear with current camera and native fallback; movement must use verified client-thread actuation and exact owner/generation checks, including stop. Neither may add competing hooks or authorities.

Learned navigation now uses the existing atomic record primitive, moved to `shadowbane_lab.record_store`, with an interprocess lock spanning load, merge and replace. Saves monotonically union coarse/refined evidence and update the saving map after successful publication. Process crash before replacement retains the previous complete map; crash after replacement exposes the new complete map. Orphan unique temporary files are ignored on load; they are not evidence records. This is process-crash recovery, not a guarantee against storage hardware/power failure. Two independently loaded writers and a deliberately crashing writer test the production save path with barriers. Navigation/store/ownership/operation tests: 29 passed.

## Combined interruption checkpoint

Cue lifecycle `e324db02297fa875030fb986628af8d82fc806e3` is integrated at `74d047c74175e4abb0b585edcd8c19d9dcc1b114`. Full combined native build and 23 runnable CTests passed; explicit private-client binding verifier also passed. Cue material coverage and native transparency interaction remain open with their feature owners. Prior `50ad9e1` installed package verification is useful evidence only for that earlier source, not certification of this repaired DLL.

The worker now claims execution atomically under the existing operation store transaction. Two independent processes can see pending work but only one transitions it to execution; an ACTIVE claim left by a crashed worker is never automatically replayed. Existing terminal receipt immutability was verified against a later ACTIVE overwrite. Observed cancellation, permit loss or failed ownership observation is latched for the operation and cannot be undone by permit renewal. A new operation remains independently admissible. Manager regression run: 236 passed plus 155 subtests; Ruff passed.

Latest user emphasis: cross-feature behavior on combined source, exact movement ownership/stop/chat/focus/isolation, render ordering/state/resources, interruption recovery, and measured installed-package cost. Keep remaining original targeted repairs, without a broad architecture cleanup. Once a complete rolling candidate is pinned, obtain one independent review of integration changes and route feature fixes to existing owners. No unfinished feature acceptance or repeated broad live navigation runs.

## Targeted simulator/planner findings

Simulator `feb83b0`: historical actor correlation IDs are rejected in admission before accepted actions mutate the tick. Multi-actor regression verifies resources, cooldowns, scheduled work, events, clock and exact snapshot replay. 35 targeted simulator tests passed.

Planner: physical destination blockers remain blocked; a route may terminate at a reachable point strictly inside the requested arrival region, without clearing the physical cell. A satisfied stationary arrival stays stationary, occupied-start escape remains controlled, and clearance-only destination behavior is preserved. Cost lookup is indexed; refined observations are grouped by parent once; far-away blockers are filtered before clearance expansion. 175 navigation/travel tests passed before final endpoint-tolerance tightening, followed by 14 planner tests passed; final combined gates still required.

Phase measurement is archived at `artifacts/hardening-evidence/planner-phases.json`, with reproducible script and committed-baseline source beside it (ignored local evidence). One Windows run, 1000 precise learned blockers plus 2006 weighted cells, 100-cell route: refinement 276.40 -> 9.35ms; grid preparation 3.11 -> 1.56ms; search 58.01 -> 1.24ms; smoothing 15.02 -> 0.10ms; diagnostics 0.43 -> 0.25ms. Route, cost and 101 expansions match the committed baseline. This is a local targeted comparison, not a connected-client frame-time claim.

## Shared context and material integration

Integrated sky early-stage dependencies `06b180a` and particles transparency evidence `773cf72` at `ee64adcc362465b7a0cf84cbc5fc40c2870a4347`; integrated cue material capture `9308665a6dad4cd896ebcce7f31fcde1976e1d21` afterward. Sky controls/package completion and movement actual native bindings remain feature-owner work. Cue added private raw-mesh capture for depth-write-disabled selected materials; no actor replay or independent hooks.

`scene_context` now owns the previous cue wglMakeCurrent hook independently of feature startup. Its idempotent install is required by cue and sky after their own binding checks. It remains process-pinned to release deferred cue GPU objects on the owning thread before unbind and invalidate sky authority even when cue startup fails. A failed context switch also invalidates authority. No hot unload or competing context hook is introduced. Production installer/callback test covers single installation, cue-independent A/B/A invalidation, failed switches, and a held callback excluding lifecycle mutation. Full native build and 6 context/cue/sky tests passed; two private binding argument skips are separately verified by explicit calls.

`80a0b93` makes the native-transparency probe a required CTest so the existing package builder cannot report success while that interaction fails. Actual CTest exit is 8: foreground half-red native transparency fails to attenuate background blue particles with depth writes both off and on. Ordinary native tests pass but candidate acceptance is blocked by this required test. Root and particles owner have the same observed RGB evidence; existing owner is investigating the durable fix. Package contracts count runtime translation units exactly once and explicitly invoke sky binding verification when the reviewed client is provided.
