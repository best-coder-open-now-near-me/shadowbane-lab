# Runtime hardening and combined integration

Active branch: `codex/native-lifecycle-hardening`; separate worktree `.worktrees/native-lifecycle-hardening`.
Exact starting source: `14d117e8c5194c6dff55dac608b2d3f683187d31`.
Integration destination is this branch for the batch, then reviewed integration toward `main`; no main merge or VM deployment is authorized here.

Shared ownership: initial repairs touch performance_telemetry.cpp, graphics_status.cpp and production lifecycle tests. Extension startup/rollback and cel_shading scene connections follow. Feature owners were notified in their existing tasks on September 5.

Lifecycle contract: admitted callbacks retain their resources and original call-through through return; restored hooks must still support already dispatched callbacks. Publisher timeout retains thread/events/backing state and prevents replacement generation until confirmed exit. Start/stop ownership is serialized. No hot unload, loader-lock waits, or GL deletion from a non-owning context.

Reuse particles scene_draw state guard and effects_attachment observations; selected cue retains its separate verified rendered-object ownership. Proposed ordering: scene composite, selected cue, particles, navigation, UI. Feature owners retain complete feature delivery and can continue independently.

Todos:
- [x] Native telemetry/publisher teardown, shared scene/context and initializer rollback.
- [x] Manager dispatch isolation, per-slot transitions, retained launch recovery and stop routing.
- [x] Durable navigation merges, operation claim/retry semantics and terminal history retention.
- [x] Simulator transaction admission and public planner correctness/indexing.
- [x] Inspector launch/cleanup exact runtime and process-lifetime ownership.
- [ ] Active: cue/effects native transparency with existing owners; observed MultiDraw coverage repaired.
- [ ] Rolling movement native actuation/adapters; passive trace and policy are integrated only.
- [ ] Combined required gates, independent review of a complete pinned candidate, exact package and installed controls.
- [ ] Consolidated acceptance handoff with identities and specific remaining live checks.

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

## Remaining lifecycle isolation and recovery

`5fafce3` preserves exact launcher ownership through failed verification and attachment: explicit attach recovers the retained Popen lifetime and launch provenance without creating another process. Verification failure reports and retains PID; exited retained handles cannot authorize a reused PID. A real task-owned child regression verifies recovery and exit rejection. Prelaunch registry observation also runs outside the supervisor-wide lock.

Bound lifecycle operations now serialize by immutable instance and manifest slot. Blocking registry/window work does not hold supervisor/session global locks; observations and slot transitions publish atomically after ownership revalidation. Close disables dispatch before its blocking window request. Tests hold a real composed session/supervisor controller at tile and graceful-close boundaries while another client pauses, refreshes and reads status. Repeated start is rejected while the same slot's action is in flight. Manager suite: 240 passed plus 155 subtests; Ruff passed.

One earlier broad run observed an intermittent PermissionError in a subprocess worker-launch contender without its traceback. Full traceback capture was added; 30 controlled repetitions and the repeated broad suite passed. Root cause is not established; retain this transient as an open validation observation and inspect any recurrence rather than claim a fix.

Full combined source at sky controls merge `1e73cad1d41e7d62d4b0429b607e96a8e0258d8c`: 1736 Python tests plus 223 subtests passed, 8 skipped (7 symlink-permission checks, 1 Tk display unavailable). Results are archived in `artifacts/hardening-evidence/combined-python.xml`. These are source gates, not a final installed candidate receipt.

## Combined rendering and startup evidence

`608f1fa` makes unavailable optional performance telemetry nonfatal to a working renderer. Production initializer test verifies disabled/unavailable instrumentation and actual rollback after later heartbeat failure. Existing held telemetry/publisher tests still pass. No wire version changed.

Combined `c2f9c997870760bb1a347bd3a6006199038265b8` contains sky `4368f13` and cue frame accumulation `8967438ee794e97408ec268ba285b1e71737fffd`. Full native build passed; CTest 27 passed, two private-binding argument skips and one required transparency failure. Sky owner independently verified both profiles and exact asset/source ownership at this source. These development DLL identities are not final package receipts.

The existing navigation WGL harness now checks all 16 combinations of navigation, particles, cue and sky using their production render functions, a shared real context and the packaged sky asset. It checks state restoration between passes, native-depth preservation, 46 selected raw mesh submissions, bounded cue memory, and complete cue release between combinations. Native attachment and scene-callsite identity remain covered by their dedicated tests; this fixture does not establish connected-client ordering or solve native transparency.

Timing excludes per-node state/pixel assertions, which execute separately in normal CTest. Eight-frame host test samples include initialization and finish at GPU completion. All-enabled: 2.730ms at640x480, 2.780ms at1920x1080. Normal cue allocation: 2,457,600 and16,588,800 bytes respectively (8 bytes/pixel); zero after release. These synthetic meshes are not a full game workload. Per-combination results: `artifacts/hardening-evidence/combined-render-cost.txt` and `combined-render-cost-1080.txt`. Required native transparency still fails; do not accept these passing composition checks as a substitute.


## September 5 combined ownership and validation checkpoint

`0b0efcc` serializes worker launch/stop with the existing per-slot interprocess lock,
so a pre-heartbeat stop cannot miss an in-flight launch. The production subprocess
launcher retains its Popen handle and retries failed attachment through that handle;
unowned numeric PIDs cannot be recovered. A proven failure before Popen creates a
child releases its reservation. Unknown launches remain explicit and conservative;
a manager crash before durable PID publication still requires external recovery
evidence and is not silently cleared. Invalid reservation records are retained.
Real-process tests cover concurrent stop/launch, retained-handle recovery and exit.

`52f6777` restricts stale inspector cleanup to the prepared runtime executable and
exact module invocation, then opens a process handle and revalidates creation time
before stopping it. New panels and discovery probes carry client creation FILETIME,
preventing PID reuse from selecting a replacement client. Actual task-owned Python
child tests verify external-runtime exclusion, stale-lifetime rejection and owned
cleanup. All PowerShell scripts parsed; 13 inspector/transport tests passed.

`c5f2f74` reuses the first immutable operation envelope for a semantic retry with
the same deduplication key and exact target/request. Regenerated envelope IDs and
timestamps do not extend its deadline or replay a terminal operation. Changed worker
lifetime or work remains a conflict. Two independent submitters converge on one
canonical envelope; existing interprocess execution claims still execute once.
34 targeted operation/ownership tests passed; Ruff passed.

Included feature revisions: particles `9e0cceddd64bbad31c911ebe4e5e75c4c9eb7a6a`,
cue `69caa80009279197296631c353e47574f04aee9e`, sky implementation `4368f13`,
movement `8536b20576fc11bc2ee33e49761f104753165b75` (policy tests and optional
passive trace; full actuation absent from runtime source lists). Both foreground
and background transparency samples now execute: front samples pass, behind samples
fail, and wholesale early-pass counterexamples fail as expected. Required CTests
remain failures, never expected-failure/disabled gates. Cue owner found a concrete
optimized MultiDraw path bypassing raw capture and is implementing that focused fix.

At `fc0723b`, complete Python run: 1750 passed, 8 skipped, 223 subtests passed.
At the same native source both Win32 profiles built; each executed 35 CTests:
31 passed, 2 private-argument skips, 2 required native transparency failures.
Explicit full-profile cue/sky binding and sky mapped-client render checks passed
against reviewed client SHA256 `feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff`.
XML/logs remain under `artifacts/hardening-evidence`; these source checks are not an
installed-package receipt. Product remains 1.6.13; ABI/wire versions unchanged.

No complete combined acceptance candidate, final wheel/DLL identity, main merge,
or VM deployment is certified. The next package-builder run must retain its failed
gate logs and stop; do not bypass transmission failures to issue a package receipt.
A complete candidate receives one independent integration review and consolidated
owner procedure only after developer-controlled checks and installed verification.

Exact clean package-builder attempt: source `5f0cf3ba15cf07634b290ac16190645f8fd5e804`,
artifacts `E:/Projects/shadowbane/artifacts/hardening-packages/0eb5791d`.
Its archived-source Python suite passed 1752 tests plus 223 subtests, with seven
symlink-permission skips; Ruff and Visual Studio 2022 full Win32 configure/build
passed. Required full native CTest returned 8 for the two transmission failures.
`validation-progress.json` and `logs/full-tests.log` record the actual executed
commands/results. The builder stopped before diagnostics/package/installed-wheel
stages; no acceptance archive or wheel was issued. Both profiles' source contracts
were separately verified from their generated runtime projects, and all PowerShell
scripts parsed successfully. CI run 33960127863 for the same source completed
Python 3.11/3.12/3.13, quality and PowerShell syntax successfully; native jobs were
still running at this observation. Preserve that distinction from local GPU gates.

`79ae9f8` preserves unverified worker Popen evidence across other launches, keyed
by worker token. Reaping is allowed only after the controller acknowledges durable
reservation publication/retirement. A real two-child regression verifies that a
later launch cannot erase the first child's exit proof or substitute its PID.
32 targeted worker/ownership tests passed.

CI 33960127863 finished with both native jobs failing: effects transparency failed,
but cue GPU/transparency were skipped because hosted OpenGL lacks FBOs. The ordinary
navigation draw test also failed because the combined fixture incorrectly required
cue resources there. The 16-combination fixture now has its own explicit CTest and
capability skip; ordinary navigation remains independently executable. Both tests
ran and passed locally with real FBO support. The package builder now reads native
JUnit results and requires combined rendering, cue GPU and both transparency gates
to have actually executed and passed. Capability skips cannot certify a package.


## Latest combined checkpoint (not an acceptance package)

Verified source `83326a6ef43f39ff65fc34de2eb02aa6b0d6fb11`, based on original
`14d117e8c5194c6dff55dac608b2d3f683187d31`. Included feature tips:
- particles `11a44eea9ce21250e46a9caf2b61ed11d4ad9b13`;
- selected cue `d741f04ff0eadd9e2d94901e5d2dd366e3a72a35`;
- sky implementation `4368f13c53601684d0abb67f3d43513561b0bbf4`;
- movement investigation/policy/trace `6f26a58429deb378fcac0b53be82cdcb9bc4ab63`.

Cue MultiDraw integration preserves the one shared context lifecycle and adds
sealed dynamic slot observation/capture within shared callback admission. Its
metadata lock is not held over drawing. The production regression holds a callback
through driver refresh and stop; original call-through remains captured and the old
scene mask is invalidated. Real GPU tests capture both primitives with depth writes
on/off and one native color submission. The exact reviewed-client binding test
passes all new code seals and drift checks. The lane is separately verifying
combined `b713dbf0c5cecf743c441c38472db8568cdbeaf9` (same cue runtime source).

Full source Python result: 1753 passed, 7 symlink-permission skips, 223 subtests.
Ruff passed. Both Win32 profiles build; each CTest executes 36 entries: 32 passed,
2 private-client argument skips, 2 required transparency failures. Local combined
rendering executes and passes all 16 feature combinations. The developer-only actual
native tree-detachment probe built and passed 64,256 removals against the reviewed
binary in a separate process; it does not establish a complete native movement stop
and is excluded from runtime/package capabilities. Full controls/adapters remain
unfinished. Product version is still 1.6.13; no ABI/wire change.

The renderer evidence now proves that identical scene RGBA/depth snapshots can
require different behind-effect transmission (blue 191 vs 64). Native source
color/alpha/depth and blend semantics at every contributing fragment are missing
from the existing capture contract. Nearest-depth masks, whole-pass early ordering
and retained mutable shader pointers cannot resolve this. Existing feature owners
retain the correction and bounded material-path investigation; no competing hooks
or approximation has been installed. This blocks a complete particles/cue package,
not the mere existence of newer movement work.

No acceptance package, installed wheel, acceptance DLL, consolidated owner procedure,
or independent complete-candidate review is claimed for this checkpoint. Last
actual builder attempt and its failing gates remain recorded above. No main merge
or shared VM/client change occurred. Active worktrees and ignored evidence remain
retained; current source is published on the integration branch.

Cue owner independently verified exact combined
`b713dbf0c5cecf743c441c38472db8568cdbeaf9` in a clean lane-owned detached worktree:
full DLL/all native targets build; CTest 36 entries = 32 passed, 2 argument skips,
2 required cue/effects transparency failures. Explicit reviewed-client cue and sky
binding tests both passed. Held MultiDraw refresh/stop, actual GPU, shared context,
all 16 rendering combinations and 17 Python selection-control tests passed.
GPU/binding sources match `d741f04`; reviewed runtime reconciliation consists of
the shared scene_context extraction. Evidence:
`E:/Projects/shadowbane/artifacts/cue-combined-native/b713dbf/lane-verification.xml`.
This closes independent lane verification of MultiDraw inclusion. It is neither
transmission/package acceptance nor the independent integration review required
once a complete candidate is pinned.

Integrated movement probe `9aab84ff9e9c81272ca9a44bceb3d005f4cb8f67`:
both local profile targets build and each passes 64,256 actual native
lookup/removal/copy/destruction sequences. Exact unsigned two-word identity,
missing lookup after removal, tree invariants and payload preservation are checked.
Only the developer-only probe and its handoff changed; DLL/runtime capabilities
are unchanged. Native pool cleanup and ordered full-stop composition remain with
the movement owner. This is not a complete stop binding or feature acceptance.

Movement `2f87ee47ccdf79469ab727380d9887e14ceb94cf` is integrated. Both combined
profile policy tests pass: takeover requests a native stop even without locally
tracked movement, failed stop excludes the new writer, and camera/ordinary click
preserve ownership. Both isolated actual-code probes pass 144 continuation-helper
cases with complete actor/state preservation plus 64,256 container sequences.
These are policy/primitive checks; the later native world-update follow regression
and complete stop composition remain unfinished. No runtime controls were enabled.

Movement probe `d4f7207f7e5b923280478d750f95f1b8a96ef779` is integrated and passes
in both combined profile builds: 144 continuation cases, 64,256 complete native
lookup/removal/destruction/40-byte-pool-return sequences, plus forced pool-lock
contention. The probe verifies free-list ownership, other size-class isolation,
payload preservation and lock release using private globals and two verified
Win32 imports. Runtime code is unchanged. This closes the isolated pool cleanup
check; it does not complete native stop composition or enable controls.
