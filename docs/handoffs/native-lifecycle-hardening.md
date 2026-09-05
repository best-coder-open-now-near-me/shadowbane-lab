# Runtime hardening and combined integration

Active branch: `codex/native-lifecycle-hardening`; separate worktree `.worktrees/native-lifecycle-hardening`.
Exact starting source: `14d117e8c5194c6dff55dac608b2d3f683187d31`.
Integration destination is this branch for the batch, then reviewed integration toward `main`; no main merge or VM deployment is authorized here.

Shared ownership: initial repairs touch performance_telemetry.cpp, graphics_status.cpp and production lifecycle tests. Extension startup/rollback and cel_shading scene connections follow. Feature owners were notified in their existing tasks on September 5.

Lifecycle contract: admitted callbacks retain their resources and original call-through through return; restored hooks must still support already dispatched callbacks. Publisher timeout retains thread/events/backing state and prevents replacement generation until confirmed exit. Start/stop ownership is serialized. No hot unload, loader-lock waits, or GL deletion from a non-owning context.

Reuse particles scene_draw state guard and effects_attachment observations; selected cue retains its separate verified rendered-object ownership. Proposed ordering: scene composite, selected cue, particles, navigation, UI. Feature owners retain complete feature delivery and can continue independently.

Shared acceptance requirements: [the owner's consolidated plan](../combined-testing-acceptance.md).
Pin the exact complete build source for each pass, preserve the known-good runtime
and restoration procedure, and record automated results separately from owner
observations. Documentation-only results commits must not replace the recorded
build SHA. Required GPU skips block package certification. Use one coordinated
first gameplay session and focused retests after actual failures; no paid compute
or separate group-operation/research scope is introduced.

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


GitHub delivery metadata audit: PR31 is merged at its historical movement head
`8536b20576fc11bc2ee33e49761f104753165b75`; subsequent movement checkpoints were
merged separately into this branch. PR30 is also merged. PR28 and PR29 remain
open against `codex/navigation-inspector`, despite the intended new source
integration destination being this hardening branch. The branch map now states
the actual metadata and owners were notified to reconcile future review targeting.
No main merge, PR closure, branch deletion or runtime deployment was performed.

Shared acceptance plan adopted at source checkpoint
`758e6f8242cc25e0e749bde0d679f2fc03dd9cad` and sent to all four feature owners.
The existing combined WGL check now repeats all 16 enable/release combinations
three times, verifies bounded allocation and zero cue bytes after release, and
reports first-frame resource creation separately from three warm-up frames and
16 steady samples. Both profile targets build and the combined CTests pass.
One internal 1080p sample with all visual features enabled: first frame 5.055ms,
warm-up mean 3.350ms, steady median 3.079ms (range 2.779–3.459ms); cue allocation
16,588,800 bytes, zero after release. First-frame timing is renderer resource
creation, not complete client/process startup. Synthetic 46-node geometry and
this host's GPU are not connected-client performance acceptance. Evidence:
`artifacts/hardening-evidence/combined-render-phases-1080.txt`. This results-only
entry is not a new build source or package receipt. Remaining blockers and the
single coordinated owner acceptance gate are unchanged.


Shared acceptance follow-through (integration source `2289bd7`): archived native
TerrainTrace evidence was located under the normal checkout's
`artifacts/git-cleanup/20260904T062424Z/scratch/.tmp/`. The
`terrain-trace-evidence-960/terrain-trace-960-134329406441965396-1.json`
trace retains 537 draws (403 blend-enabled); the
`terrain-retained-trace-20260903/terrain-trace-6420-134329234815817786-1.json`
trace retains 1,505 draws (218 blend-enabled). Both report a complete reviewed
interval, one unsafe-query omission, and zero capacity/query-budget omissions.
Retained categories are immediate, display-list entry, arrays and elements;
these are not exhaustive fragment or driver-internal coverage. Neither trace
contains the proposed program, separate blend, stencil or write-mask fields.
Private captures remain local and are not package or acceptance receipts.

Particles checkpoint `ec816a594a99dff4cb6beedbfa9df42e15f2e262` is reviewed but
not yet included: the owner is strengthening exact-enum/capability and existing
Python-reader compatibility tests before integration. Cue owns native MultiDraw
categorization and the existing cel query-safety observation helper, coordinated
with particles on trace serialization. Sky is extending only missing sky pixel
and depth assertions in the existing CombinedProbe, outside the timed path;
no duplicate matrix or alternate acceptance pipeline is being added. Shared
lifecycle ownership remains here. The cue's halo requires transmission evaluated
at the destination pixel and each retained contributing owned depth; a mask or
background depth substitution is not an accepted repair. Active work remains
the shared native transparency contract, followed by complete-feature gates,
independent combined review and exact installed-package acceptance. Movement
stop composition and full runtime adapters remain with their existing owner.


Combined source `4e908b411570122a07cc15fd98dc9888ab74fc37` now includes sky
fixture `1e70f4095dc99ab95557c2ebdbb23fdf8d515713` and particles trace
`ec816a594a99dff4cb6beedbfa9df42e15f2e262` plus strengthened capability tests
`1f23943bc387b5ec7707f40eb49a8de0357a299a`. Both full and diagnostics native
builds succeeded. Each profile ran and passed four targeted CTests (navigation,
combined rendering, trace enabled and disabled), zero skips. JUnit evidence is
`artifacts/hardening-evidence/trace-sky-native-full.xml` and
`trace-sky-native-diagnostics.xml`. Existing Python trace analysis: 19 passed;
trace collector: 29 passed. Ruff and diff checks passed. An initial pytest
invocation named nonexistent `test_terrain_trace.py` and collected nothing;
the corrected actual suites above were then executed successfully.

The shared fixture now checks complete depth-buffer preservation, enabled sky
pixels, alpha holes, later native background blending and final UI pixels, outside
its timed path. Trace fields are additive, capability-gated and disabled by
default; old state positions and readers remain compatible. This adds evidence
for the transparency repair, not a repair or release claim. Required native
transparency failures remain open; no package or owner acceptance is certified.
Next is cue MultiDraw trace coverage and the shared transmission contract,
with complete movement stop/runtime composition continuing in its owner lane.


Cue trace checkpoint `98bcd21814b472942c8eea1ee1e932806ca5c0a9` is integrated
at combined source `5519a8e4026136d04231c9c66cfe71fc23fdac97`. Merge resolution
retains the shared scene-context observer and both material-state and MultiDraw
serialization assertions. The same verified dynamic slot observes one native
multi-submit before private replay; count is explicitly subdraws. Opt-in capture
works with disabled cue or missing target, while disabled/no-trace avoids adoption.
Existing immediate/list query guards suppress unsafe supplemental GL work.
Both native profiles build and each executes seven targeted tests successfully,
zero skips: startup, scene context, cue runtime, combined render, both trace modes,
and cel shading. Evidence: `artifacts/hardening-evidence/multidraw-full.xml` and
`multidraw-diagnostics.xml`. Both Python trace suites pass (48 tests). No new
hook system, wire version, package receipt or transparency completion is claimed.
Next remains shared native fragment/transmission representation, coordinated
through the existing scene owner; bounded emitter replay alone is insufficient.


Bounded material observer `dffd9bbd43fa8375ea033082c41750c0a0a741b3` was applied
without its copied prerequisite, producing combined source
`1c293a1a48280b83ab5493f7b0a92dfb94f2c4b7`. The explicit candidate predicate
observes capability-gated ARB/program, texture target/texgen and raster state;
unknown mechanisms remain unknown and replay eligibility is always false.
Both complete native profile builds succeeded. Each profile executed five
trace/lifecycle tests (startup, cue runtime, both trace modes, graphics publisher):
all passed, zero skips. Evidence: `artifacts/hardening-evidence/material-native-full.xml`,
`material-native-diagnostics.xml` and matching build logs. Existing trace Python
suites: 49 passed; touched-test Ruff and diff checks passed. This is instrumentation
for a bounded missing-facts check, not a transmission repair or package receipt.
No capture, client replacement or deployment occurred. Next is owner analysis of
whether this observation resolves the specific material unknowns and whether one
narrow enriched capture is necessary; coverage/pre-depth/ABI/source-equivalence
and complete movement runtime remain unresolved.


Pipeline observation `16dd37b58ccf27b6bb7e9a00c63d04afd4f51aac` is included as
`549036b617d57651650976f67511e878cb8194c1`. Only handoff text conflicted; native
source applied unchanged. Both full native profile builds and both trace tests
per profile passed with zero skips. Logs/JUnit are under
`artifacts/hardening-evidence/pipeline-native-{full,diagnostics}*`. Core/ARB
pipeline zero clears only its own ambiguity; nonzero/missing, EXT-only semantics
and independent vendor mechanisms remain unsupported/unknown. Replay eligibility
remains false. Next is the authorized bounded actual-GL source/coverage comparison
in the existing cue GPU test path; no runtime collector or deployment is enabled.


Actual-GL feasibility `827b7421f35bb19390eced07b261695c64561fed` is included at
combined source `a22a1bbb8b7252ba8a0d1c1e7c1f51078d75d4d3`. Both profile cue GPU
targets build. Each executes base GPU and source-feasibility tests successfully,
zero skips; each required cue native-transparency test still fails the same two
foreground cases (expected 131,16,19; actual 116,31,37 without depth writes and
127,0,0 with depth writes). Background cases still pass. JUnit and build logs:
`artifacts/hardening-evidence/source-native-full*` and
`source-native-diagnostics*`. No failure was reclassified or hidden.

The test-only explicit material packet exercises 288 controlled actual-GL cases
through the existing shared scene guard: source RGBA, independent alpha/depth
coverage, pre-depth scratch copy, native-buffer invariance, query rejection and
successive order-dependent draws. Its 64x64 scratch is 32KiB attachment storage;
that is not a complete runtime memory or frame-cost budget. No client hook,
collector, runtime replay or guessed ABI was added. Next is a bounded ordered
transmission strategy preserving distinct native submissions and cue tap depths;
this successful experiment alone does not provide that integration or certify
an owner-facing package. Full movement stop/input integration remains open.


Particles operator regression `b0010bb97a0b3d9d6c99eb6c84e58d41c22230e2` is
included as `84c1e44`; root compatibility adjustment is exact combined source
`0376ae083cc0bcf5406d8544bef1b69c1f30f835`. The existing navigation executable
now exposes `--ordered-operators` as a distinct CTest, isolating its eight-bit
alpha-buffer requirement from ordinary navigation, combined render and screenshot
paths. Both profile targets build; navigation, ordered operators and combined
render each pass with zero skips. Required effects/native transparency still
fails both behind-surface cases and passes front cases. Evidence:
`artifacts/hardening-evidence/operators-native-{full,diagnostics}.xml` and build logs.
The 20 RGBA restricted cases preserve native order, equal-depth behavior and two
effect depths. Negative witnesses reject nonlinear destination factors and even
additive factors after framebuffer saturation. Factors alone do not establish
an affine resolve domain. No atlas or runtime resolver was added. Next remains
opaque visibility and per-tap destination-depth coverage, followed by an exact
bounded transmission strategy; these tests do not certify complete features.


Cue visibility witnesses `b75b6563ab5e36a3b8798119572055266e615f31` are included
at source `97f65217a48d9199c3e6f39038463f4b34dcded4`. Both profile GPU targets
build; base GPU and expanded source/visibility/tap feasibility pass, zero skips.
Required cue transparency still fails the same two foreground cases. Evidence:
`artifacts/hardening-evidence/visibility-native-{full,diagnostics}.xml` and build logs.
Actual production cue composition proves identical final native color/depth and
earlier alpha inputs can require different output after a late opaque draw.
The controlled per-tap experiment separately proves destination-pixel coverage
and retained owned depth are required; it does not introduce a halo reduction
policy. These findings rule out reconstructing opaque visibility from final depth
plus translucent packets. Next is a narrowly scoped native scene-boundary proof
for opaque visibility, including late opaque submissions and equal-depth order;
no opaque-complete boundary, atlas, collector or package completion is assumed.


Queued movement `03ad0aa3c8e7dcfb02b0b8fc781f51c383d0104c` is integrated at
`fa49832c1b5d94a82da72082dafeb62d03d3d70c`. Both developer-only profile probe
targets build and pass against the exact reviewed `feb351...` client bytes:
whole-path destruction/retained actor lifetime through 1,024 elements, 144
continuation cases, pool contention and 64,256 container/pool sequences.
Evidence: `artifacts/hardening-evidence/path-lifetime-native-{full,diagnostics}.log`
and matching build logs. The probe uses private memory and probe-owned finalizers;
actual game-object destructors, connected-client behavior and complete Stop are
not claimed. It remains EXCLUDE_FROM_ALL and absent from runtime/package sources.
No process was attached or modified. Next movement work remains owner-scoped
ordered action/path/follow retirement, outgoing idle-message ownership, stale-stop
exclusion and real adapters. This is unfinished implementation, not an external
blocker or an owner gameplay request. Rendering transparency also remains open.


Production movement stop `fe0f26fcc3629840297fbce31e9837ec07012595` is merged
at `95fa869add3b354c6abe48651e531aca75d6235b`; builder ownership alignment is
`a0761b37be0b743afe54063c006a89d8ad858485`. Policy, native image verification and
stop composition now compile exactly once in both DLL profiles, but remain
unbound: no runtime input/transport capability is enabled. The developer-only
tree probe remains excluded. The existing builder's actual membership statements
were executed against both generated projects and passed; no alternate package
pipeline was created. Both complete native builds and nine targeted movement/
lifecycle tests per profile pass, zero skips. Python movement/package suites:
24 passed; builder Ruff and diff checks pass. Evidence:
`artifacts/hardening-evidence/stop-native-{full,diagnostics}.xml` and build logs.

Production composition tests use controlled native-call boundaries; their later
world-update driver is not unmodified game execution or server-effect evidence.
Integration review identified missing connection returning success without sending
an idle message, and replacement pending-request adoption during callbacks. The
movement owner accepted both focused corrections: fail/unavailable with owned
message release, and pin exact request identity for the transaction plus callback
replacement regressions. These remain open before runtime activation. Existing
manager grant ownership remains authoritative; no competing movement owner is
introduced. Next is those fixes plus complete adapters/activation, alongside
opaque-visibility/transmission work. No package or owner acceptance is certified.


Movement correction `36d62d92974da016fb5f7d11c558358c4b10cf66` is included at
`16c780c2ea5adedd67d79888e43b54b537bd07b0`. Both complete native profile builds
and both policy/production-stop tests per profile pass, zero skips. Evidence:
`artifacts/hardening-evidence/stop-request-native-{full,diagnostics}.xml` and logs.
Missing outgoing connection now fails unavailable with balanced owned-reference
cleanup. Each execution pins its current-player request; action/path/state
callback replacements are not adopted. Native current-player producer/consumer
ownership and noncallback container helpers are documented by the feature owner.

Review follow-up remains open: position/destination/waypoint and other actual
callback boundaries must check the pinned request before subsequent mutations,
not merely actor/world identity. The movement owner is adding those focused
regressions and consistent RequestCurrent checks. Runtime remains unbound; this
checkpoint does not certify complete Stop, adapters or a connected package.
Next is that correction and real movement/camera/picking/input integration;
rendering transparency and exact final package acceptance remain unfinished.


Movement callback correction `0203ff124373b747a923765583103bb3d9e611cf` is merged
at `1c73c51af86bc398e23cd9c5f473be4b5d635b75`. The owner first reproduced the
position/destination/waypoint gaps against 36d62; production stop now revalidates
the captured request before every subsequent mutation. Combined full and
diagnostics DLL builds pass, as do both policy/stop tests per profile, zero skips.
Evidence: `artifacts/hardening-evidence/stop-callback-native-{full,diagnostics}.xml`
and build logs. Regressions verify precise downstream call counts, untouched
replacement requests, balanced references and no stale movement/send, including
request-only state replacement and defensive retain-boundary invalidation.
This closes the identified callback request-revalidation finding; artificial
boundary injection does not claim sealed helpers invoke gameplay callbacks.
Next movement work is the actual native-update integration and movement/camera/
picking/input adapters. Runtime activation and connected/server effects remain
unverified; rendering transparency and final installed-package acceptance remain
open. No new manager authority, capture or deployment was introduced.


Native camera binding `d58b56d84073f48ae948a96acb953734ad30e3bd` is included at
`cf59526d0b1b8dac3e6753e7b7d3fd672fae14dc`. Both complete DLL profiles build;
each executes policy, native backend, shared scene-context and combined-render
tests successfully, zero skips. Evidence: `artifacts/hardening-evidence/camera-native-{full,diagnostics}.xml`
and build logs. Production policy/backend tests cover elapsed-time intervals,
native pitch limits, preserved distance/inertia and route grant, phase/thread
rejection and camera-only failure isolation. Native calls remain controlled doubles;
these tests do not certify real camera update or coupled camera/sky behavior in
a connected client. No runtime activation, grant transport or deployment occurred.
Next is owner-complete steering/picking/input/native-update integration, then
cross-feature activation checks and exact installed-package verification.
Rendering transparency remains unresolved; no complete candidate is pinned.


Shared native-update ownership `eea575d9613ff04c14250d251ada04d5f3cb2848` is
included at `7fd53a5de59d301dc911bfa1bfbfdbb8bed1a51f`. Both complete DLL profiles
build and each executes 13 targeted movement/startup/telemetry/publisher tests:
all passed, zero skips. Evidence: `artifacts/hardening-evidence/shared-update-native-{full,diagnostics}.xml`
and build logs. Both consumer start orders preserve one verified slot; retiring
trace preserves controls and vice versa. Held controls callbacks retain immutable
callback/original identity, partial installation failure preserves call-through,
and final retirement leaves foreign slot replacements intact. No loader-lock
shutdown work or second update hook was added. The runtime must perform its native
stop on the owning update thread before final consumer retirement. This retirement
is terminal for the process-pinned registration; ordinary settings disable/re-enable
must not misuse it as a restartable registration API. No controls consumer is
activated yet. Next remains real steering/picking/input/settings/grant wiring,
followed by combined activation and package gates; transparency is still open.


Native steering `f418b5f58acf69f66e0ffca5110e511d008f9ddd` is included at
`66cc1ef02cefeadabcd84954df5e649bf67c217a`. Both complete DLL profiles build;
each executes 11 movement/shared-update/startup tests successfully, zero skips.
Evidence: `artifacts/hardening-evidence/steering-native-{full,diagnostics}.xml`
and build logs. Production composition retains native collision/restriction
admission, coalesces pending solves/deferred actions, balances outgoing references
and pins cleanup to the actor captured by the movement. Replacement-actor failure
cannot cause a cleanup stop to recapture a new actor under an old policy grant.
Direction is normalized parent-local X/Z; no analog movement speed is invented.
Local updates and 400ms message refresh are distinct; native solver, network
cadence and connected obstacle behavior are not certified by controlled-call tests.
No controls consumer is activated. Next is camera-basis/terrain-pick/Windows-input
composition, settings and manager grant transport, then combined runtime and
package gates. Native transparency remains unresolved.


Native picking `e7237d2c6dbfa007d64f35751d913bb81e0cf6cb` is merged at
`3ee0ec715b1cc6bdce1316531ab0c08a9e8edd04`. Both complete DLL profiles build;
each executes 11 movement/shared-update/startup tests successfully, zero skips.
Evidence: `artifacts/hardening-evidence/picking-native-{full,diagnostics}.xml`
and build logs. The production adapter composes native unprojection, full 3D
collision and parent-local conversion. Hit actor/parent references retire on
replacement pick or owning-thread EndUpdate; foreign-thread EndUpdate is rejected.
Misses have no plane fallback and scene replacement prevents stale conversion.
Tests exercise production composition with controlled native calls, not live
terrain or camera certification. No runtime controls consumer is active. Next is
drag destination actuation and camera-basis/input/UI composition, then settings/
grant transport and combined package validation. Transparency remains unresolved.


Native drag `7a9385d63bc52078dd3d04d38ca7e9efa64db251` is included at
`5a913015ad5c22989fa8bc29e30b87469b706213`. Both complete DLL profiles build;
each executes 11 movement/shared-update/startup tests successfully, zero skips.
Evidence: `artifacts/hardening-evidence/drag-native-{full,diagnostics}.xml` and logs.
Drag consumes only the current update's native pick, retains/releases native
marker/target references and coalesces pending/deferred work. Captured transactions
now reject parent-coordinate-frame changes even for the same actor. Input.scene
must advance on those transitions; input composition remains owner work.
No native solver/server or active runtime capability is certified by these tests.
Next is camera-basis/Windows-XInput/UI consumer composition, settings and manager
grant transport, then complete combined package checks. Transparency remains open.

Branch map metadata was rechecked via GitHub: PR28/29/30/31 are all merged against
hardening. PR28 merge is `4e908b411570122a07cc15fd98dc9888ab74fc37`; PR29 merge is
`5519a8e4026136d04231c9c66cfe71fc23fdac97`. They represent historical checkpoints,
not open reviews or certification of later source/package work. No main merge,
PR closure action or deployment was performed by this audit.


Native camera basis `c401c0e4763e59ace394b68c10636cc7d09dff58` is included at
`e01a054531c83b40c6a7801563b720b7a97aca34`. Both complete DLL profiles build;
each executes policy/backend, scene-context and combined-render tests successfully,
zero skips. Evidence: `artifacts/hardening-evidence/basis-native-{full,diagnostics}.xml`
and build logs. Current native center/right rays and inverse-parent conversion
produce movement axes; conversion references retire immediately and frame changes
during conversion/cleanup reject the result. Native calls are controlled in these
tests; no rendered client-camera behavior is certified. CameraBasis invalidates
its scratch pick, so runtime composition must calculate basis before its final
terrain pick or deliberately repick before drag actuation.

Existing scene_frame/cel counters reset per render frame; scene_context observes
GL-context changes, and cue generation/epochs cover feature or hook lifetimes.
None is a durable game scene-generation source proving same-pointer replacement.
The movement owner was told to preserve that distinction and establish specific
native lifecycle evidence for Input.scene; changed identity tuples or observed
invalid intervals alone do not prove an unobserved ABA transition impossible.
Next remains input/UI consumer plus settings/grant transport, with that lifetime
contract explicit. Rendering transparency and final package gates remain open.


Native destruction observer `245e605eddf759d96e87a4dacf679dc7e61003a3` is merged
at `79aa4a0578e0dec2cc0ab2c3ad5ca0b2f4f011ad`; builder membership alignment is
`d94c705132d85f0bc5a27a5650f07207870e1e89`. Both complete DLL profiles build;
each executes 22 targeted movement/lifetime/startup/publisher tests successfully,
zero skips. Actual builder membership statements pass against both generated
projects, requiring exactly one movement_lifetime.cpp and excluding the probe.
Builder Ruff and diff checks pass. Evidence:
`artifacts/hardening-evidence/lifetime-native-{full,diagnostics}.xml` and build logs.
The observer records destruction before original finalizer/free call-through,
retains process-pinned callback records and preserves foreign slots on retirement.
Production backend admission now consumes observed NativeScene epochs rather
than a render-frame counter. No runtime controls consumer is activated.

Integration follow-ups remain open: NativeMovementLifetimeCurrent must reject
lost hook integrity during an already admitted update, without waiting for the
next Observe; first/replacement watch publication must not miss destruction
between capture/registration and arming. The movement owner was asked to reproduce
these gaps with production-path barriers or establish a verified native thread
constraint, rather than infer coverage from held already-watched callbacks.
Next is those focused lifetime corrections and complete input/UI/settings/grant
consumer wiring. Rendering transparency and final package acceptance remain open.


Lifetime integrity correction `b29fcff8be58c4b1c1d79017b6c4d10b54b50b3e` is
included at `6f457db3e42cde1b876a32522a2dcd28e6cd6b3e`. Both complete DLL profiles
build; each executes 13 policy/backend/lifetime tests successfully, zero skips.
Evidence: `artifacts/hardening-evidence/lifetime-integrity-native-{full,diagnostics}.xml`
and build logs. Current now validates the watched actor/parent finalizer interfaces
and exact world-free slot within the admitted update, invalidates immediately on
loss and cannot revive after restoring a slot. Only owning Observe/Retire performs
cleanup; foreign slots remain intact. This closes the reproduced mid-update
integrity finding. First/replacement-watch arming remains explicitly unresolved
and is being corrected by the movement owner before activation. Input/UI/settings/
grant composition, rendering transparency and final package acceptance remain open.

Shared acceptance plan rechecked against the supplied owner document. The existing
`docs/combined-testing-acceptance.md` remains the controlling consolidated procedure.
At clean published source `47c1e23febd8f14588e3638f2a36a88cc9333eb7`, both complete
native CTest suites executed 55 entries: 51 passed, two required transparency
checks failed, and two private-image binding checks skipped for absent arguments.
JUnit evidence is `artifacts/hardening-evidence/combined-47c1e23-native-full.xml`
and `combined-47c1e23-native-diagnostics.xml`. The skipped cue and sky binding
executables were then run explicitly in both profiles against the reviewed private
client SHA256 `feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff`;
all four runs exited zero, verifying exact code, relocation and byte-drift rejection.
This supplements, rather than rewrites, the recorded CTest skips. It is offline
binding validation, not installed-client or connected gameplay acceptance.
The two failures remain selected_cue_native_transparency and
effects_native_transparency. Combined-render and all movement/lifecycle entries
passed. No complete package is certified and no installation was changed.
Next: owner-supplied first/replacement lifetime arming correction, complete movement
consumer wiring, and the existing cue/effects native transparency repairs. After a
complete candidate is pinned, obtain the independent integration review and run
the existing exact-source package/installed checks before consolidated owner testing.

First/replacement lifetime arming correction b99f65051d5210d8a67fe443433930061b37965c
is included at 347b4ca6082cd9e14aed5056965d39744567ec31. Both complete native DLL profiles build;
each executes 34 policy/backend/lifetime tests successfully, zero skips. Evidence:
artifacts/hardening-evidence/arming-native-full.xml and arming-native-diagnostics.xml,
with matching build logs. Exact supported finalizer slots are prebound before
observation. The observation fence rejects uncertain concurrent destruction;
publication-edge callbacks invalidate a newly matching watch before original
call-through. Production-path barriers cover first/replacement capture, preexisting
held callbacks, prepublication and publication-edge entry, plus batch rollback
with foreign-slot preservation. These close the reproduced watch-arming gap;
they do not certify live client input or server behavior. No extra runtime cpp
membership or active movement consumer was introduced. Next remains complete
input/UI/settings/grant composition, cue/effects transparency repair, independent
review of a complete candidate, and exact-source package/installed validation.

Native UI checkpoint eac3cd06e1995ed16f90063aff35d9078b4dc13c is included at
ea5ac8ebd220dd3b7ce31e4fdab1092429e9194e. Both complete DLL profiles build;
each executes 35 movement policy/backend/UI/lifetime tests successfully, zero
skips. Evidence: artifacts/hardening-evidence/native-ui-full.xml and
native-ui-diagnostics.xml with matching build logs. UI text/focus/modal/drag
ownership and native pointer conversion now share the reviewed binding;
terrain and camera-basis unprojection consume that same conversion in production.
The existing package builder now requires movement_native_ui.cpp exactly once
in both profiles. Its actual movement/probe membership statements executed
successfully against both generated DLL projects; builder Ruff and diff checks pass.
No runtime controls consumer is activated or package identity certified. Next:
Windows/XInput consumer and settings/grant integration, existing transparency
repairs, then complete-candidate review and installed-package validation.

Action-channel producer ownership repair (integration-owned, before movement wire
revision): real Windows IPC tests exposed absent kernel32 Interlocked exports on
64-bit Python, concurrent read/exchange lease claims, same-PID competing hosts,
and stale close/renew affecting a replacement generation. The transport now uses
one named producer mutex per exact client mapping for claim, command transaction
and release; captures generation; rejects active same-PID contenders; and never
wraps exhausted generations. Process exit releases the OS mutex. Native consumers
must not take this host-only transaction mutex while completing commands.
Captured host PID/creation and lease generation are exposed for the movement owner.
No wire/schema/product version changed in this repair; native full-identity
admission is part of the coordinated forthcoming movement schema revision.

Missing Win64 exports are replaced by aligned scalar access with explicit Windows
FlushProcessWriteBuffers ordering. This requires 64-bit Python and rejects
unaligned accesses. Read-modify-write ownership comes from the producer mutex;
these scalar stores are not compare-and-swap. Windows reference:
https://learn.microsoft.com/en-us/windows/win32/sync/interlocked-variable-access
The local 1000 fenced store/read-pair measurement was 1.786 ms; this is a host
micro-measurement, not connected-client performance acceptance.

Validation: 45 action-channel/trace/manager-worker tests passed, zero skips;
Ruff passed. Evidence: artifacts/hardening-evidence/producer-lease-python.xml.
New tests use independently spawned processes and actual Windows shared memory/
mutexes, covering simultaneous claim, held producer transaction, abrupt test-owned
process death, unrelated-client admission, stale same-PID close/renew, generation
exhaustion and exact current host lifetime. A test-fixture event cleanup deadlock
was corrected before the passing run. No client process was opened or changed.
Next: integrate typed movement sessions/consumer, preserve operation cancellation
and immutable grants at manager composition, resolve visual transparency, then
complete-candidate review and installed-package validation.

Stop-only HWND admission 15659286dccbf86cccab7517fe96a09d9381ee6a is included
at 1ad1455570386d34a4346d2f577bfd77d3f8a792. Both complete DLL profiles build;
35 targeted movement/UI/lifetime tests per profile pass, zero skips. Evidence:
artifacts/hardening-evidence/owner-stop-full.xml and owner-stop-diagnostics.xml,
with corresponding build logs. Admission requires the owned HWND/thread and
observed native lifetime; this phase rejects movement, pick and camera operations.
Emergency cancellation uses the existing grant authority and requires neutral
input before rearming. These tests verify the API/backend contract, not the
unfinished window-event consumer, nested stop deferral or connected focus loss.
Those remain owner work alongside input/runtime/settings and typed transport.
Visual transparency and complete-candidate package/review acceptance remain open.

Windows capture ebdafce11385e75f843124478621f4798f72fe75 is included at
a07726dc736a1c0aa967bb89b6e359a8ed447a4d. The producer repair dependency was
retained without replay; the chronological handoff conflict retained the existing
stop-only validation record. Both complete DLL profiles build; 41 targeted
movement/UI/lifetime/capture tests per profile pass, zero skips. Six exercise
real Windows subclass/capture paths, including rollback and foreign subclass.
Evidence: artifacts/hardening-evidence/windows-input-full.xml and
windows-input-diagnostics.xml with build logs. Actual builder membership checks
execute successfully for both generated projects, requiring exactly one
movement_windows_input.cpp; builder Ruff passes. These certify capture components,
not the unfinished runtime consumer or connected WASD/controller/drag behavior.
A repeated Bind/XInput module reference issue was routed back to the movement
owner before activation. Next remains that correction, nested safety/runtime,
settings and typed grants, existing transparency repair, complete-candidate review
and exact installed-package acceptance.

Native consumer e5b910deb93727fa7f6e8bb6ef39bcca8b2ec1c8 is included at
0287cd97cfc72fdf9054cf0dfc57ecd126a8fdaa, with this shared integration correction.
The first combined all-target build exposed an unresolved new dependency in the
existing extension_startup_test. Its external-service seam now supplies the
controls entry point and tests actual production initializer ordering: heartbeat
success precedes registration; repeat initialize does not register twice;
unsupported optional controls preserve success; shared rollback never registers.
Both complete DLL profiles subsequently build. Each executes 66 movement/runtime,
shared-update, startup, context and combined-render checks successfully, zero skips.
Evidence: artifacts/hardening-evidence/movement-runtime-full.xml and
movement-runtime-diagnostics.xml, with build logs. These runtime tests exercise
production composition with real HWNDs and controlled native callees, including
focus without updates, nested interruptions, drag release, chat and stale tickets.
They do not certify actual server/gameplay behavior. The repeated Bind/XInput
reference issue is closed by admission-before-load and its passing regression.

The consumer now registers only after shared startup success and defaults disabled;
ordinary disable retains it for re-enable. Existing builder checks now require
movement_runtime.cpp exactly once in both generated DLL projects; their actual
membership statements and builder Ruff pass. Branch map reflects that registration,
without advertising completed settings/transport capability. Next: native settings
and Graphics Lab discovery, immutable wire/session API and manager composition,
existing cue/effects transparency repair, complete-candidate independent review
and exact installed-package verification before owner acceptance.

Native settings b5e139570444c34c8282cdd112fb6c6819594261 is included at
112d8d4144834e55da1ee8d2459c644fccd10823. Both complete DLL profiles build;
68 movement/runtime/settings/startup/context/combined-render tests per profile
pass, zero skips. The native settings test includes isolated preference reload
in another process and real panel validation/stale apply. Python selected-client
settings, Graphics Lab and producer tests: 44 passed, zero skips. Ruff passes.
Evidence: artifacts/hardening-evidence/movement-settings-{full,diagnostics}.xml,
matching build logs and movement-settings-python.xml.

Existing builder membership statements execute successfully against both DLL
projects with movement_settings.cpp exactly once. Wheel/sdist membership and
installed Graphics Lab button/module checks are extended in that same builder;
installed smoke syntax is checked, but no new installed-wheel execution is claimed.
Required native gate checks now explicitly include all three runtime inputs,
focus/nested interruption/chat/stale settings and the native preferences panel,
so absent/skipped entries cannot produce a successful receipt. These supplement
the still-failing required cue/effects transparency gates. Saved preferences are
defaults for future clients; applying the panel changes only the selected current
client and uses its immutable grant/revision. Next is typed native command/session
and manager operation composition, visual transparency repair, final independent
review and exact package/installed verification before consolidated owner testing.

Lossless movement codec 7791888b21c02dc3ecc704d5c97f2ecf39144eea is included at
1e7bcaa7f983d27b0d5ce51b97b64aa3c394cf0b. Both complete DLL profiles build;
18 targeted wire/preferences/runtime/startup tests per profile pass, zero skips.
Python codec/settings/action/producer checks: 25 passed plus 15 malformed-input
subtests; Ruff and diff checks pass. Evidence: artifacts/hardening-evidence/
movement-wire-{full,diagnostics}.xml, matching build logs and movement-wire-python.xml.
Shared synthetic bytes verify exact Python/native command, receipt and status
layout; native preferences now reuse the existing 52-byte settings encoding.
Existing package checks require the codec module, source header/fixture and a
successfully executed native wire test. This adds no runtime cpp source.
Active action-channel schema remains 1: schema-2 payloads are defined but no
producer/consumer switch or usable movement session is claimed yet. Product and
installed artifact identity remain unchanged/unverified for this combined source.
The movement owner is correcting the touched command-channel timed-out shutdown
ownership with production held-worker tests while implementing admission/status/
receipts. Next: coordinated live wire switch, typed session and manager operation
composition, visual transparency repair, complete-candidate independent review
and exact package/installed checks before owner acceptance.

Schema-2 transport b8380f2aac41818104dc435abd25464fe2d169aa is included at
4dd02e4684ba5d6074d38837695ac2588b63f5b2 with the shared probe link correction
in this checkpoint. The existing probe now links movement_controls.cpp for the
validator reached through event_channel; the first combined all-target build
correctly failed before that dependency was supplied. Both complete builds now
pass. 70 movement/startup/event/channel tests per profile pass, zero skips.
Real Python-to-native tests ran against each exact newly built runtime fixture:
22 tests plus 15 subtests per profile passed, zero skips, including acquire/retry/
stop while the Python producer mutex remains held and read-only/mixed-schema checks.
Evidence: artifacts/hardening-evidence/movement-channel-{full,diagnostics}.xml,
matching build logs and movement-session-{full,diagnostics}-python.xml. Ruff passes.

Active action schema is now 2 (command768/result512/status512); legacy action and
learned-power payload prefixes remain, but schema-1 peers are rejected. Product
version is unchanged. Command-channel stop disables admission immediately; a timed
out worker retains handles/state, and admitted lease references retain mappings
until released. The production held-worker test verifies repeated-start rejection,
release/final cleanup and later restart. Package builder requires this lifecycle
and runtime command gate, and runs the real IPC pytest with each freshly built
fixture explicitly, rejecting missing/skipped cases. Inherited fixture paths are
cleared. These package steps are not claimed executed by a new complete package.

Open cross-feature work: arbitrary world destination currently returns unavailable;
manager dispatcher injection will preserve the accepted LT/LG planner decisions.
The owner is implementing that adapter, bounded acquisition-receipt retention,
nonterminal movement stop versus terminal grant release, and navigation with manual
controls disabled. Manager operation/session composition remains integration-owned.
Visual transparency, final independent review and exact installed-package acceptance
remain open. No client/VM installation was changed.

Shared CLI dispatcher boundary is now explicit: _run_travel and _run_pve accept
an optional TravelDecisionDispatcher and pass that exact object to their existing
runners. Native movement does not create a minimap reader; travel also avoids the
unused desktop movement backend. PvE retains its existing separately guarded
combat-input adapter. Default standalone callers preserve existing behavior;
no route/planner policy changed and no native dispatcher is silently substituted
on failure. Existing CLI reader-binding tests now cover both default and injected
paths, asserting no minimap/desktop-movement construction for the injected path.
Validation: 152 CLI/travel/adaptive/PvE/manager tests passed, zero skips; Ruff passed.
Evidence: artifacts/hardening-evidence/movement-dispatcher-injection-python.xml.
Next: manager-owned immutable operation session/grant lifecycle and sub-second
renewal while movement is paused, using the owner's pending pause/renew/dispatcher
API. Renewal must not reacquire or revive expired ownership; manual takeover
must latch interruption for PvE combat as well as movement. Native destination
and final acceptance remain unfinished; no owner-facing candidate was produced.

Worker supervision now accepts an explicit operation-maintenance callback. When
configured, it polls at most every 250 ms independently of the configured heartbeat
publication interval; heartbeat frequency remains unchanged. Exact game identity
and the operation's latched permit/cancellation signal are checked before renewal.
A controlled-clock production serve-loop regression holds the strategy thread,
verifies three maintenance calls between heartbeats, then revokes the permit and
verifies maintenance stops without an extra renewal. Existing workers without a
maintenance callback retain their previous cadence. 26 worker/ownership tests pass,
zero skips; Ruff passes. This is the worker-side cadence boundary for the native
session's pending synchronized renew method; manager callback wiring follows that
API, with no reacquisition or heartbeat-expiry revival permitted.

Combined-source Python verification at dc392007b6b2b76853f19bd146c890d4fe224f6b:
1777 passed, 8 skipped, 238 subtests passed (43.59 s). The real movement IPC fixture
was explicitly configured to the combined full-profile runtime executable and ran.
Seven skips were Windows symlink-permission cases; one inspector Tk creation skip
was investigated with a focused rerun of the exact replay/control-rebind test,
which passed with zero skips. The original suite skip remains recorded rather than
rewritten. Evidence: artifacts/hardening-evidence/combined-dc39200-python.xml/log
and combined-dc39200-inspector-tk.xml. Ruff for src/tests/existing builder passes;
all 36 tracked PowerShell scripts parse successfully. This is combined source
validation, not a new package/installed-wheel receipt or connected-client acceptance.
Next remains manager operation grant/renewal composition against the owner pause/
renew/dispatcher checkpoint and the unresolved visual transparency implementation.


### Manager native operation composition (September 5)

Integrated movement destination/pause/renew checkpoint
`95a3b363189557c529ebeecd4d5e1ec2004b6c67`, camera correction
`429d0de3de8972ddd1c352455414b33c95ca4261`, and session lifecycle serialization
through `5af4908`. These build on the combined `cc8895e` checkpoint; no deployment.

Manager operations now reserve one per-operation context before native IPC,
acquire one immutable grant, inject the existing native dispatcher into the
unchanged travel/PvE engines, and renew from the worker maintenance cadence.
Permit loss/manual takeover/status failure latch cancellation for movement and
combat. Cleanup stops only the captured grant, retries ambiguous stop with the
same UUID, and closes its producer lease. Idle STOP cannot acquire or stop a
manual owner. Unresolved cleanup is a failed operation receipt, not success.
Shared source ownership remains manager/CLI/package integration here and native
session/input/standalone CLI feature delivery with the movement owner.

Validation: 64 focused Python tests passed, zero skips, including an actual
separate native fixture process exercising production operation acquisition,
destination/pause/renew/destination/pause/terminal cleanup. Barrier regressions
cover overlapping executor requests, held acquisition, independent client
maintenance, renewal versus closure, latched takeover, and exact retry IDs.
Evidence: `artifacts/hardening-evidence/manager-movement-python.xml`.
Existing package builder now requires dispatcher/context/test membership and
execution of the operation interprocess regression for both profiles.

Both complete native DLL/profile builds succeeded. Broader movement/startup
CTest selection ran 69 tests/profile: 68 passed, one failed, zero skips.
`movement_native_stop` has five camera-yaw assertions still expecting the earlier
sign after the camera correction; routed to the feature owner for an evidence-based
fix. Logs/JUnit: `artifacts/hardening-evidence/movement-destination-*`.
Required cue/effects transparency failures remain open. No complete candidate,
installed package receipt, independent final review or owner acceptance is claimed.
Next: consume the owner camera regression fix and direct live CLI ownership
composition, then rerun combined gates and resolve remaining render coverage.


Combined validation follow-up: full Python at exact source
`d3f3af3d9752485a2e9468cf0215e45ba87b6c2f` passed 1793 tests and 238 subtests,
with seven environmental symlink-permission skips (42.60 s); the actual native
IPC fixture was configured and executed. Evidence: combined-d3f3af3-python.xml/log.
Diagnostics-profile operation/session IPC separately passed 14 tests, zero skips
(manager-movement-diagnostics-python.xml).

Owner camera assertion correction `595ca1e6e992c0a768609361e0039a80ce66b656`
was reviewed and integrated at `43f5dfee2d2e5e13a64b6d7d3fa481b4ca3a4d66`.
The changed expectation agrees with the previously verified negative native yaw
for rightward controller input; no runtime behavior changed in this correction.
A cherry-picked CLI dependency introduced a handoff-only merge conflict; retained
the integration history. An initial native run during that conflict is only a
working-tree check (combined-camera-full.*), not a pinned-source certificate.
After resolving and committing, both complete native profiles rebuilt and all
102 CTests/profile executed at 43f5dfe: 98 passed, 2 failed, 2 skipped. The movement
camera test now passes. The two required failures remain selected-cue native
transparency and effects native transparency. Evidence: combined-43f5dfe-*.xml/log.
The skipped selected-cue and sky binding executables were then explicitly run
against the reviewed private client SHA256
feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff;
all four profile/binding runs passed, recorded in the matching separate logs.
Do not reinterpret the original CTest skips as passes.

No final package built/installed, no final independent review requested, no owner
client testing requested. The shared acceptance plan remains authoritative.
Remaining: standalone live CLI same-owner composition (movement owner), production
cue/particles native transparency (existing feature owners), complete combined
candidate review, exact installed package verification and one consolidated live
acceptance session. Ordinary source pushes continue; no main merge or VM/client
replacement is authorized by these receipts.


Standalone live movement integration: feature checkpoint
`55e30ccbddabf217a49e2cc847e56901d46b83b4` included by merge
`9f22b1baef76f5b51d8377daea20e07ff2786bba`. Default travel/PvE now establish one
exact native operation with independent renewal and latched window/parent/native
cancellation; no minimap movement fallback remains. Manager-injected dispatcher
is retained. PvE combat uses the same cancellation signal. The feature-owned
standalone context uses the synchronized common session; manager maintenance
continues on its existing worker cadence. No planner policy changed.

71 combined focused tests passed with the full-profile real IPC fixture, zero
skips; 28 context/session/manager tests passed with the diagnostics fixture, zero
skips. Evidence: standalone-combined-{full,diagnostics}.xml. Ruff passes.
Builder now requires installed/source membership of movement_operation.py and
its regression, and requires the named standalone slow-planner native IPC test
alongside session and manager IPC tests in both profiles. This is a builder
source update, not an executed full package receipt. Next shared fix is the cue
owner's public-source program-pipeline state correction; transparency remains open.


Shared shader pipeline integration: included cue source
`6ca19048e3eb4c40a52d1c2527cef5d0ae2840b5` at
`4e61fd56daa3a8bda930916580dc462583f6a661`. Reconciled the guard contract to retain
both verified background and scene/UI stage authority while preserving current
program and separate pipeline bindings. Both complete native profiles built;
102 CTests/profile again yielded 98 pass, 2 transparency failures and 2 private
binding skips. Logs: combined-4e61fd5-{full,diagnostics}.*. The new shader case
explicitly logged execution in both profiles; it does not resolve transparency.

Included standalone thread-start rollback `2be1a650cde19a46c6301062418f7d9f698d2d10`
at `fd207a3c521bd38f6a4e77a409caeac867bcc3ec`. Full Python at that exact source:
1807 pass, 8 skips, 238 subtests pass (45.42 s). Seven environmental symlink skips
and one transient Tk display skip; exact Tk replay/control-rebind rerun passed.
Evidence: combined-fd207a3-python.xml/log and combined-fd207a3-inspector-tk.xml.
Ruff passes; all 36 tracked PowerShell scripts parse.

Cue follow-up `f1a56c27db0e3bc90b221f7c2a3f4f5ce256884c` makes pipeline testing
an explicit --pipeline-guard mode. Shared CMake registers the dedicated
wonderbane_extension_scene_pipeline_guard test, and the existing package builder
requires its actual nonskipped execution. The test returns 77 on an unsupported
context without changing runtime fallback behavior. Before this checkpoint commit,
both complete native profiles rebuilt; five affected scene/context/cue/pipeline/
sky tests/profile passed, zero skips (pipeline-gate-{full,diagnostics}.xml).
Executed the existing builder's three runtime source-membership loops against
both generated DLL projects: exact intended movement sources and profile-specific
visual sources, with developer probe excluded. Both passed. No installed package
receipt is inferred from these source/build checks. Remaining production blocker:
cue/effects foreground transparency, followed by finished-candidate independent
review and actual installed-package/connected acceptance.


Independent affected-area verification: cue owner rebuilt the full DLL and GPU
fixture from exact `1b0b6c5f29c7015c85006a570686253f30676f92`. Base cue GPU,
dedicated scene pipeline guard and source feasibility each executed and passed;
required cue native transparency executed and failed unchanged. Zero skips.
Integrator read the actual JUnit at
`E:/Projects/shadowbane/artifacts/cue-combined-native/1b0b6c5/lane-cue.xml` and
confirmed those four outcomes. The owner also reviewed the reconciled header,
CTest registration and builder rejection of missing/skipped/failing pipeline gates.
Public receipt: `8b52bb79192e193b4cb69d29c97d3b32c553d924` on the cue branch;
that documentation-only commit is not needed for runtime inclusion. The shared
pipeline-state defect is closed. This focused feature-owner verification does
not replace the independent review required after a complete candidate is pinned.
Next remains production opaque-visibility/ordered-transmission correction for
cue and particles; final package verification and consolidated acceptance follow.


Coordination authorization update (September 5): the owner explicitly approved
sharing the private client-binary analysis among the existing cue, particles and
integration tasks to resolve transparency. Both feature owners were notified.
The earlier sharing hold is lifted within that scope; it is not a remaining
user-input blocker. Private binaries/captures remain outside public source, and
this does not authorize deployment, client replacement, main merge or broader
disclosure. Existing owners resume the production visibility/transmission repair;
shared scene, lifecycle and state integration remains here. Next: reconcile the
verified boundary and implementation division, integrate fixes and rerun the two
required transparency gates before preparing a complete acceptance package.
