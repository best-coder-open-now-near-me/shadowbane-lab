# Maelstrom lag investigation journal

This is the canonical human-readable journal for the Maelstrom degradation investigation. Append
new dated entries after every observation, capture, intervention, or conclusion change. Preserve
earlier entries; correct them with a later entry instead of silently rewriting history.

Keep these evidence classes distinct:

- **Operator observation**: what a player directly saw or felt.
- **Instrumented evidence**: what a named, verified artifact measured.
- **Inference**: an explanation consistent with current evidence but not yet demonstrated.
- **Ruled out or weakened**: a hypothesis contradicted by a controlled intervention or capture.

## Current case summary

- **Question:** Why does the older client/character develop severe stuttering and input starvation
  around the large turtle creatures in Maelstrom after repeated exposure or combat?
- **Current state:** Collecting evidence; no root cause has been demonstrated.
- **Strongest discriminator so far:** A later-arriving second character/client in the same area,
  after fighting only one or two turtles, is materially smoother than the older degraded
  character/client.
- **Working model:** Repeated turtle exposure or combat accumulates per-client state whose cost is
  paid while the turtles are visible or active. Candidate owners include animation, mesh/LOD,
  effect, combat-created object, and visibility/scene bookkeeping systems.
- **Important boundary:** The whole rendered world and UI/input stall when the problem is active;
  this is not merely the turtle models visibly animating poorly. Moving away from the turtles
  appears to relieve the lag, so the degradation may not remain costly outside their locality.
- **Not established:** Whether the accumulated state belongs to the process, character, zone
  session, renderer, or a specific turtle resource; whether the main thread, render thread, GPU,
  or guest scheduler is the immediate stall site.

## 2026-08-31 — Backfilled observations and first sealed degraded capture

Times in this entry are America/New_York unless suffixed `Z` for UTC. The live capture crossed
midnight in UTC on 2026-09-01.

### Runtime and build identity

**Instrumented evidence / operator-verified setup**

- Target VM: regular `shadowbane` VM, not `shadowbane-testing`. An earlier test-VM/release
  misunderstanding was resolved before this capture.
- Target game: vanilla Shadowbane client running expansion content; Maelstrom is a later-game
  expansion area.
- Degraded process: PID `7492`, creation time
  `2026-08-31T22:44:22.3422809Z`, executable
  `C:\Users\admin\Downloads\WonderbaneClient\Wonderbane\sb.exe`.
- Later-arriving control candidate: PID `3184`, creation time
  `2026-09-01T00:00:40.8808988Z`, using the same executable path. This process has not yet received
  a paired sealed capture.
- Live `sb.exe` SHA-256:
  `55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc`.
- No frozen reviewed reference executable was available in the documented guest/share roots.
  Therefore this run intentionally has no client-alignment authority; it fingerprints the exact
  live executable but does not claim compatibility with another build.
- Collector/analyzer Git revision:
  `6f892f2afd4ebfa448eeae405c01585dc1afd9ef` on `codex/evidence-spine`.

### Operator observations before capture

**Operator observation**

- Initial pattern: Maelstrom becomes extremely laggy after roughly half an hour rather than being
  maximally bad immediately on arrival.
- The degraded state includes frame stuttering, short apparent translocations, visibly poor
  environment streaming, ignored/delayed clicks, and whole-client responsiveness loss.
- The entire world stutters when the problem is active, not only the turtle animation.
- The turtles are especially large creatures. Turtle proximity and combat strongly correlate with
  the problem: moving away produced a large frame-rate improvement; returning to them reproduced
  the stuttering.
- Stopping turtle combat stopped an obvious worsening trend, although lag near the turtles
  remained consistently bad during later observation.
- The latest clarification is locality-sensitive: the lag is consistently severe by the turtles
  but does not appear to carry at the same severity when the affected character leaves them.
- A second character/client brought into the area later, after only one or two turtle fights, was
  definitely not lagging as hard as the older character/client.
- Water plus travel-stance changes to base speed were separately suspected of causing position
  prediction mismatch and short translocations. This movement hypothesis is not yet tied to the
  turtle stutter mechanism and should be tested as a separate case unless evidence connects them.

### Interventions already tried

**Ruled out or weakened**

- Forcing the degraded client's working set resident for five minutes did not improve the lag.
  This weakens simple working-set eviction/residency as the primary cause.
- Resetting the D3D renderer did not improve the lag. This weakens a transient renderer-state
  explanation that should clear on that reset, but it does not rule out resource or scene state
  owned elsewhere in the client.
- Merely standing near the turtles without continuing to fight did not show the same obvious
  worsening trend. This weakens pure elapsed proximity as the sole accumulator and raises combat,
  spawn/effect, animation-instance, or visibility-lifecycle work.

### Capture provenance

**Instrumented evidence**

- Run ID: `diag-134fdd1a853b403099795dbf2ae2e2e2`.
- Manifest ID:
  `sha256:e6f8a72a147378bfa8593c5923286822ddbf9e19ebf08da3e4e83949debba1c3`.
- Fingerprint ID:
  `sha256:858d5fe245981f95ca3e881672ba502a6a489d43de282f34166d960c631064d5`.
- Capture-stream artifact ID:
  `sha256:bd0d9caffd38d4fe9c91435def29d52226ed0a3f1b849d4a69e4f405b4a1991b`.
- Independent verification receipt ID:
  `sha256:3de70fd702960a1c20b946976ea431b1fa03a93819f1fb04dbc2ef3a7b182af3`.
- Offline analysis report ID:
  `sha256:3f114a9bcfa49b1b5ab03ce5ce05a4d9610d61d11f3ddec17b85fd49d4b684dc`.
- Capture interval: `2026-09-01T03:05:20.354Z` through
  `2026-09-01T03:06:20.001Z`; 187 samples over 62.641 seconds.
- Trigger observed at approximately `2026-09-01T03:05:55Z`; collection completed the requested
  30-second post-trigger window.
- Terminal state: complete. All five referenced objects passed size and SHA-256 verification. No
  channel omissions, producer drops, sequence gaps, warnings, or identity changes were reported.
- **Trigger semantics:** Lag was already present continuously before the capture, remained present
  for the whole capture, and continued after the marker. The marker identifies a confirmed
  degraded-state point; it is not the onset of lag and pre/post comparisons are stability checks,
  not healthy-versus-bad comparisons.

### First-pass counter findings

**Instrumented evidence**

- No monotonic resource-growth candidate was detected.
- Private bytes changed from 1,080,389,632 to 1,078,968,320 bytes (`-1,421,312`).
- Working set changed from 202,665,984 to 201,568,256 bytes (`-1,097,728`).
- Process handles changed from 407 to 411; USER objects from 163 to 167; GDI objects remained
  effectively flat at 366. These small changes do not resemble the leak required to explain the
  accumulated severe lag.
- The process performed no writes during the retained window.
- One discrete read burst occurred about 7.86 seconds before the marker: 792,142 bytes across
  1,547 read operations. The lag was continuous outside that burst, so the burst alone cannot
  explain the sustained degraded state.
- Excluding the invalid startup interval described below, mean process CPU consumption was stable
  at about 2.17 core-equivalents before the marker and 2.18 after it. Short intervals approached
  four core-equivalents. This establishes ongoing CPU work but does not identify a thread or prove
  CPU saturation without paired system/thread data.
- Sample gaps reached 0.656 seconds on both sides of the marker. These are collector-process
  scheduling gaps, not direct frame times, so they cannot by themselves prove a game main-thread
  stall.
- A notable no-read page/working-set churn event occurred 10.75–11.03 seconds after the marker:
  2,113 page faults with a 31,272,960-byte working-set drop, followed by 6,180 page faults with a
  25,313,280-byte working-set increase. No process read bytes accompanied it. Windows' process
  page-fault counter combines soft and hard faults, so this is consistent with memory re-fault or
  working-set churn but is not proof of disk paging or root cause.

**Ruled out or weakened**

- A straightforward private-byte, working-set, handle, GDI-object, or USER-object leak during the
  already-degraded minute is not supported.
- Sustained file-write pressure is absent.
- A single contemporaneous streaming read is insufficient to explain continuous lag throughout
  the capture.

### Capture-tool findings that affect interpretation

**Instrumented evidence / tooling defect**

- The first shared-folder capture attempt never armed. The immutable object store publishes with
  a hard link, which the VirtualBox shared folder could not provide. The successful capture was
  written to guest-local NTFS and copied only after sealing.
- Raw interval analysis must exclude sample 1 → sample 2. The collector obtains the initial
  process sample, performs client fingerprinting, then timestamps and records that older sample at
  session start. The next sample therefore contains CPU and counter changes accrued during
  fingerprinting but assigns them only the first short sampling gap. Aggregate analyzer deltas
  that include this interval overstate interval rates. This needs a collector fix before future
  rate comparisons.

### Current hypotheses

These are inferences, ordered by present fit rather than certainty.

1. **Per-client accumulated turtle state.** Repeated turtle combat/exposure leaves animation,
   mesh/LOD, effect, combat-object, or visibility bookkeeping attached to the older client. Its
   cost is activated while turtles are visible or active, explaining both locality and the
   smoother later-arriving client.
2. **Turtle-triggered page/resource churn.** Large turtle resources or repeated instances provoke
   working-set churn after enough exposure. The observed no-read fault burst is compatible with
   this but a single event is not enough to establish it.
3. **Character- or session-scoped server state.** Repeated combat could increase replicated state
   delivered only to the older character. This remains possible because no network summary or
   paired process capture was collected.
4. **Zone-wide or VM-wide degradation.** Weakened by the smoother second client in the same area,
   but not eliminated until both clients are captured simultaneously with equivalent viewpoints
   and actions.
5. **Movement-speed prediction mismatch.** Plausible for water/travel-stance translocations, but
   currently separate from the accumulated rendering/input-stall case.
6. **Unknown other.** Thread synchronization, GPU queue stalls, driver behavior, guest scheduling,
   or another unobserved subsystem may dominate; current process counters cannot distinguish them.

### Next discriminating tests

1. Capture degraded PID `7492` and the later-arriving control PID `3184` simultaneously while both
   are co-located and viewing the same turtles. Mark approach, first visibility, combat start,
   combat stop, departure, and return. Compare raw samples rather than only summaries.
2. Repeat a bounded exposure ladder on a clean client: approach without combat; fight one turtle;
   fight a fixed repeated count; remain nearby without fighting; leave visual range; return; zone
   out/in; restart client. Record exactly which transition creates, activates, deactivates, or
   clears the cost.
3. Add thread-level CPU/wait and frame-present timing. Process totals cannot distinguish main-thread
   work, renderer work, a synchronization wait, GPU back-pressure, or VM scheduling.
4. Add bounded network summaries for both clients to test character-specific replicated traffic
   without assuming the issue is purely graphical.
5. Test another comparably large creature with the same exposure ladder to separate turtle-specific
   assets/animation from size, skeleton complexity, LOD, or generic large-creature handling.
6. Run the water/travel-stance translocation experiment separately with movement-state and
   client/server position markers.

## 2026-08-31 — Relog completely clears the degraded state

### Intervention and result

**Operator observation**

- After the complete degraded-state capture, the affected character/client was relogged.
- The severe turtle-area lag cleared completely after the relog.
- No post-relog instrumented capture has been collected yet.
- It is not yet recorded whether this was a character logout/login within the same `sb.exe`
  process or a full client restart. That distinction controls whether the demonstrated reset
  boundary is character/world-session scoped or only process scoped.

### Updated interpretation

**Supported or strengthened**

- The bad state is resettable and accumulated rather than an unavoidable baseline cost of loading
  Maelstrom or initially seeing the turtles.
- A per-character, per-world-session, or per-process collection of turtle-related animation,
  render, effect, combat, visibility, or replicated objects is now the leading model.
- The smoother later-arriving character/client is consistent with less accumulated exposure rather
  than a universally slow turtle scene.

**Ruled out or weakened**

- Static turtle geometry or animation cost alone cannot explain the full symptom: the same content
  is smooth again immediately after a reset boundary.
- A persistent VM-wide degradation is strongly weakened because relogging one affected
  character/client clears its symptoms.
- Permanent client-file corruption and an always-bad Maelstrom zone state are weakened.

**Still unresolved**

- A relog may destroy many systems at once. This result does not yet identify animation, rendering,
  effects, combat objects, network replication, or another owner.
- The result does not contradict the flat degraded-window resource counters. Accumulated state can
  remain at a stable high-water count or impose per-frame work without continuing to grow during
  the captured minute.
- The exact reset granularity remains unknown until the post-relog PID and process creation time
  are compared with degraded PID `7492`.

### Immediate next experiment

1. Record the current `sb.exe` PID and process creation time before further turtle combat.
2. Capture a clean control window in the same location and viewpoint with turtles visible but no
   combat.
3. Apply a bounded exposure ladder: one turtle fight at a time, with a marker and symptom rating
   after each fight, stopping as soon as degradation returns.
4. Capture the first degraded step and compare its raw counters with the clean control.
5. Relog again without restarting the process if possible, then repeat the same view to determine
   whether character/world-session teardown alone clears the state.

## 2026-08-31 — Warlock turtle-exposure test begins

### Active procedure

**Operator observation / experiment in progress**

- The operator is deliberately fighting Maelstrom turtles on a Warlock to determine whether the
  severe lag can be accumulated on another class after the relog reset.
- The Warlock's exact PID, process creation time, starting symptom level, and completed turtle-fight
  count have not yet been recorded. No class-specific conclusion is authorized until those
  conditions and the outcome are known.
- The working comparison is Druid versus Warlock. If comparable turtle exposure degrades both,
  turtle/client-lifecycle state is favored. If the Druid reliably degrades and the Warlock remains
  clean, Druid-specific forms, animation/effect combinations, powers, pets, or replicated combat
  state become stronger candidates.

### Suspected early degradation and monitoring result

**Operator observation**

- During continued Warlock turtle exposure, the operator reported that the frame rate appeared to
  be dropping. This is the first suspected Warlock degradation signal, not yet a quantified FPS
  result or a confirmed severe-stall threshold.

**Instrumented evidence**

- A regular-VM screenshot at `2026-09-01T03:26:26Z` visually identified the active character as
  the male Shade Warlock `Qualgnarr`.
- Twelve additional VM screenshots were sampled from `2026-09-01T03:27:28.736Z` through
  `2026-09-01T03:27:36.220Z`. Capture intervals were approximately 0.58–0.78 seconds because the
  VirtualBox screenshot path is slow.
- Every consecutive image differed, so presentation continued advancing during those coarse
  samples. This rules out repeated 0.6-second-or-longer complete presentation freezes in that
  short window; it cannot quantify FPS or rule out a substantial drop from normal.
- No readable FPS counter was present in the captured display.

### Diagnostic coverage gap exposed by this run

**Tooling finding**

- No diagnostic capture was armed on the Warlock. The sealed degraded capture for PID `7492` had
  ended approximately 20 minutes earlier.
- The host-side screenshot sequence was outside the evidence collector and is not a substitute for
  synchronized frame telemetry.
- Existing process metrics contain CPU, memory, page-fault, handle, GUI-object, and I/O counters;
  they do not contain presentation timestamps or frame times.
- Existing `graphics-present` evidence establishes static import identity and can accept an
  external runtime status/count. It does not currently publish every present timestamp, frame-time
  distribution, or hitch marker.
- ETW, screenshot, packet, and dump paths in the capture tool are bounded ingestion channels for
  explicitly requested or externally produced artifacts. They are not silently started and were
  not enabled for the prior capture.

**Required production improvement**

1. Add an identity-bound graphics-present producer with monotonic per-present timing, sequence and
   drop accounting, and bounded aggregation.
2. Derive frame-time median, p95, p99, maximum, and explicit hitch counts/timestamps in offline
   analysis while retaining raw present records.
3. Arm the triggered process/frame capture before an exposure ladder begins; fail visibly when the
   requested frame producer is unavailable instead of implying that process counters measure FPS.

### Renderer diagnostics 1.5.4 integration available

**Reviewed repository evidence and operator release report**

- Graphics producer commit `c9933ee` adds extension `1.5.4` identity-bound graphics-present
  diagnostics for the reviewed client. Commit `1df6f4a` pins the package identity. Both are on the
  graphics branches, not yet ancestors of `codex/evidence-spine`.
- The producer hooks the exact `GDI32.dll!SwapBuffers` import at IAT RVA `23789964`, increments an
  in-memory present counter, samples a newly observed OpenGL context once, and delegates status
  publication to a background thread. The hook itself performs no hashing or filesystem I/O.
- Its atomic status binds PID, process-creation FILETIME, executable path, and executable SHA-256.
  It reports the active present entry, observed present count, GL/GLSL versions, depth-buffer
  precision, viewport, depth-texture capability, and framebuffer-object capability.
- Evidence-branch commit `f2b82db` already auto-discovers the matching status by PID and creation
  time. This completes exact producer/consumer identity once both sides are deployed together.
- The operator reports that the VM-facing DLL built and all four native tests passed, and that a
  transient read-only `codexevidence` VM share was added. Those deployment-state claims have not
  yet been independently captured in the regular `shadowbane` VM.
- Publication and launch commands require `sb.exe` to be closed. They were deliberately not run
  during the active Warlock reproduction, so the sealed local capture remains undisturbed.

**Integration boundary**

- `1.5.4` closes present-hook identity and renderer-prerequisite discovery. Its cumulative present
  count can prove that presentation occurred between status publications.
- It does not publish per-present monotonic timestamps, frame intervals, or hitch records. It does
  not by itself quantify the reported Warlock FPS decline.
- The production frame-telemetry improvement should extend this exact bounded hook/status producer
  with sequence/drop health and monotonic timing rather than add a second unverified presentation
  hook.
- The graphics commits sit atop a long renderer feature branch. Integration must isolate the
  producer/package changes or deliberately merge the complete renderer line; it must not silently
  import unrelated visual behavior into the evidence branch.

### Camp-boundary activation result

**Operator observation**

- After the Warlock degradation became clearly noticeable, the operator moved out of the turtle
  camp while a turtle remained engaged and following/attacking the character.
- The lag let up outside the camp despite that turtle remaining active.
- Heading back into the camp caused the Warlock to become substantially laggy again almost
  immediately.
- The character was not relogged between the relief and recurrence, so both states occurred within
  the same accumulated client/session state.

**Supported or strengthened**

- The active cost is spatially gated by the turtle camp or its visible/loaded entity set. Candidate
  gates include multiple turtle instances, scene-cell streaming, camp environment resources,
  visibility/LOD bookkeeping, and region-scoped replicated state.
- The result fits a two-part model: exposure accumulates latent state, while camp presence or
  visibility activates its expensive per-frame cost.

**Ruled out or weakened**

- One engaged turtle's ordinary animation or combat loop is not sufficient to maintain the severe
  lag outside the camp.
- A continuously global process slowdown is weakened because responsiveness improves without a
  relog or process reset when the camp is left.

**Next boundary test**

- Repeat one out/in pass without additional kills, keeping camera direction and travel stance as
  stable as practical. Record the approximate spatial or visibility threshold, visible turtle
  count on each side, and whether the recurrence is immediate on crossing or delayed until models
  appear.

### Different-camp control result

**Operator observation**

- Without relogging the Warlock/client, the operator moved to a different camp.
- The different camp was quite smooth, with no comparable lag.
- The comparison camp's creature type and turtle presence have not yet been recorded.

**Supported or strengthened**

- The expensive state is activated by the original turtle camp or its particular loaded/visible
  set, not by a continuously global process slowdown.
- The accumulated client/session can still render another camp smoothly, which further narrows the
  candidate boundary toward original-camp entities, density, resources, scene-cell streaming, or
  region-scoped replication.

**Interpretation branch awaiting one fact**

- If the smooth camp also contains turtles, generic turtle species/animation cost is strongly
  weakened and the original camp instance, composition, density, asset set, or scene cell becomes
  the lead.
- If the smooth camp contains different creatures, the result confirms locality but does not yet
  distinguish turtle-specific handling from the original camp's environmental state.

### Observations to record during this run

1. Approximate completed turtle fights from this point.
2. First appearance of frame stutter, environment stutter, click starvation, or translocation.
3. Whether severity increases per fight, with elapsed visibility, or only after a particular
   ability/effect.
4. Whether leaving turtle visual range clears the active cost without relogging.
5. Do not relog after the first symptom until a degraded capture and PID identity are recorded.

## 2026-09-01 — Sealed Warlock degraded capture and paired offline comparison

### Capture provenance

**Instrumented evidence**

- The copied guest-local capture verified successfully and is complete, with no omissions,
  warnings, channel failures, identity changes, producer drops, or reported sequence gaps.
- Run ID: `diag-0ba7023f655f4179834957388926cf5c`.
- Manifest ID:
  `sha256:be6872b43f520a7e0c622ae0c4397c68683434f10a39be8ce3ef33c74d75213d`.
- Fingerprint ID:
  `sha256:5fe737dd2a809b4d68c9347be0a4f0c1e2c434ddc62550a3301101ceaeb177e5`.
- Capture-stream artifact ID:
  `sha256:9f3ba5b36316800211d62bafa566996f7302dab7b5feb9d0c7b4bdfe7d4bb551`.
- Offline analysis report ID:
  `sha256:80ae081ca903f3c1a1a2bef112762637a5a70c511d7cadb8da33a4f63921e48b`.
- Capture interval: `2026-09-01T03:31:08.050Z` through
  `2026-09-01T03:31:46.965Z`; 144 samples over 43.968 seconds.
- Manual marker time: approximately `2026-09-01T03:31:18Z`, about ten seconds after capture
  began. Lag was already active; the marker was a confirmed-degraded point, not symptom onset.
- Target process: PID `3184`, creation FILETIME `134326944408808988`, exact executable SHA-256
  `55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc`.

### Corrected raw-sample findings

**Instrumented evidence**

- The known stale first-sample interval was excluded from every rate below. Samples 2 through 144
  cover 43.593 seconds.
- The Warlock accumulated 302,556 page faults, or 6,940.47 faults/second. The Windows process
  counter includes soft faults, so this is page/working-set churn evidence rather than proof of
  disk paging.
- Mean process CPU consumption was 1.479 user plus 0.328 kernel core-equivalents. Process reads
  averaged only 7,939.62 bytes/second and 0.321 read operations/second.
- Private bytes fell by 7,462,912 and working set fell by 7,602,176 bytes. The capture therefore
  does not support a simple monotonic memory leak during this degraded window.
- Before the marker, aggregate fault rate was 5,846.14/second; after it, 7,348.67/second, a 25.7%
  increase. Interval median rose from 6,758.7 to 9,774.4/second, or 44.6%. Post-marker p95 was
  14,744/second and maximum was 18,079.9/second.
- The largest fault bursts coincided with rapid private-byte and working-set swings of roughly
  13–26 MB while process read-byte deltas were zero. This is consistent with intense allocation,
  touch/release, resource-residency, or already-cached scene/resource churn inside the client; it
  does not establish which subsystem owns the work.

### Comparison with the earlier degraded capture

**Instrumented evidence**

- Raw-sample comparison report ID:
  `sha256:0a896aa5d1fa12b037def4a2e8b7692a430fe595685310e08a90b13aaafdd167`.
- The earlier PID `7492` degraded capture, also corrected by excluding its stale first sample, had
  an aggregate fault rate of 558.69/second. Its post-marker median interval rate was 310.4/second.
- Warlock fault churn was about 12.4 times the earlier capture overall, and its post-marker median
  was about 31.5 times higher. The Warlock used less CPU and performed fewer reads, so its signature
  is not ordinary file streaming or greater total CPU alone.
- The earlier capture contained one isolated process-read burst. The Warlock's largest fault and
  memory-oscillation bursts had no accompanying process reads.
- Both captures used the exact same `sb.exe` and matching PE section hashes. Their client-directory
  tree fingerprints differed by 22,889 total bytes despite identical file counts. Mutable runtime
  files are a likely explanation, but the sealed inventory is not file-granular, so exact tree
  equality cannot be claimed and the drift remains a comparison confound.

**Interpretation**

- The two degraded sessions do not share one simple sampled-counter signature. They may represent
  different stages or manifestations of one scene/resource lifecycle defect, or distinct pressure
  paths that process totals cannot separate.
- The Warlock evidence strongly supports severe client-local page and memory-residency churn. It
  fits the whole-world stutter and click-starvation report better than a turtle-animation-only
  explanation, but it is not yet a root-cause identification.
- Combined with immediate recurrence on re-entering the original turtle camp, relief outside that
  camp even with one turtle engaged, and a smooth different-camp control, the best current model
  remains two-part: session/client state accumulates, then the original camp's loaded or visible
  entity/resource set activates expensive repeated work.

### Analyzer defect exposed by the paired comparison

**Tooling defect**

- The built-in analyzer currently includes the stale initial sample. On this Warlock run it
  produced an impossible first interval: 9.23 user CPU seconds and 2.44 kernel CPU seconds were
  attributed to only 0.297 elapsed seconds because fingerprinting occurred between sampling and
  timestamping.
- That interval also changed the apparent memory result from a corrected net decline to misleading
  positive growth. Until fixed, all first-interval rates and whole-window deltas require raw-sample
  correction.

### Next discriminating instrumentation

1. Add exact renderer-present timestamps with a bounded producer ring, producer clock anchors,
   sequence/gap accounting, and continuous capture-side draining.
2. Report frame-time median, p95, p99, maximum, and explicit hitch counts/timestamps so observed
   stutter can be correlated directly with process fault/memory oscillation.
3. Fix the stale first-sample timestamp boundary, then add thread-level CPU/wait and allocation or
   resource-lifecycle evidence to identify the owner of the churn.

## 2026-09-01 — Frame timing completed and stale first-sample defect fixed

### Tooling resolution

**Reviewed repository evidence**

- Integration commit `32765bb` adds extension `1.5.5`: the exact
  `GDI32.dll!SwapBuffers` hook now records a bounded 1,024-present sequence/QPC ring and publishes
  producer clock anchors and timing-query health from the background status writer.
- Integration commit `b1504af` continuously drains that ring during diagnostic capture, binds
  every poll to PID, creation FILETIME, executable path/hash, and exact PE present candidates, and
  seals raw timing as a required `frame-timing` channel. Ring overwrite, QPC failure, poll failure,
  or capture-side sample loss makes the channel explicitly incomplete.
- Offline analysis now derives average FPS, frame-time median/p95/p99/maximum, and hitch records at
  33.3, 50, 100, and 250 milliseconds. Each hitch retains its present sequence, exact QPC interval,
  and a clock-anchor-derived UTC estimate. Before/after comparison rereads both sealed timing
  artifacts.
- Integration commit `acb09b8` removes the stale first-sample defect. Process discovery and
  fingerprinting use an unrecorded discovery probe; after setup, a fresh identity-validated process
  sample becomes sample 1 and the capture clock origin.
- Focused validation passed: all six native extension tests, six graphics/frame-timing tests, nine
  core diagnostic capture/analysis tests, Ruff checks, and the two package-pin tests.

### Interpretation boundary

- The two existing Maelstrom captures remain immutable and still require the documented raw-sample
  correction; the fix applies only to captures made with the new collector revision.
- Renderer timing has been implemented and pushed but has not yet been deployed into a new regular-
  VM gameplay run. No historical FPS or hitch values are inferred from the old process-only captures.

## 2026-09-01 — Passive instrumentation boundary authorized

### Provenance correction

- Every reported Maelstrom/turtle-camp symptom and both completed process-metric captures occurred
  before any graphics-development share was attached to the regular shadowbane VM.
- A transient read-only codexgfx share was later attached to the regular VM by mistake. The graphics
  publisher failed on its first missing-baseline prerequisite before copying, patching, or launching
  a client. The transient share was then removed. This event cannot have caused or contaminated the
  earlier lag observations.
- The user subsequently authorized an explicitly instrumented client for future captures, with the
  understanding that tool-induced functional or performance changes become defects to measure and
  fix rather than grounds to pretend the client remains vanilla.

### Tooling boundary

- Extension 1.5.5 tied present timing to unconditional strong-cel renderer initialization. Its
  graphics package also carried texture overlays and a Mesa llvmpipe launch profile, so it was not
  suitable for Maelstrom performance diagnosis.
- Extension 1.5.6 adds a compile-time diagnostics-only profile. It publishes graphics status and
  observes only the exact GDI32.dll!SwapBuffers import. It does not start draw-call hooks, cel or
  outline rendering, texture replacement, Mesa overrides, world-map capture, or the extension event
  channel.
- The future instrumented capture must record runtime_profile: diagnostics-only. It is a new
  comparison cohort and must not be silently pooled with the two historical vanilla captures.
- Publication uses a separate copied client package. The reviewed source client remains untouched,
  the temporary full baseline payload is removed after verified publication, and its manifest is
  retained for provenance.

## 2026-09-01 01:31 EDT / 05:31 UTC — Passive client launched

### Exact launch identity

- VM: regular shadowbane VM, not shadowbane-testing.
- Process: PID 3196, creation FILETIME UTC 134327142791034606
  (2026-09-01T05:31:19.1034606Z).
- Package:
  C:\Users\admin\Wonderbane-diagnostics-wb-55fbad5f-present-1.5.6.
- Runtime profile: diagnostics-only, confirmed from the identity-bound live status document.
- Extension SHA-256:
  94a4f4043d429ad63775bb4bf77ecd31a29ffc7a01146fb919bfb25cc5c7cdcb.
- Renderer status:
  C:\Users\admin\AppData\Local\ShadowbaneLab\client-extension\graphics-status-3196-134327142791034606.json.
- Publication verified the copied package and removed the temporary full baseline payload. The
  reviewed source client remained untouched.

### Observation boundary

- Character, zone, turtle visibility, combat exposure, and symptom state had not yet been assessed
  at launch.
- This process is the first instrumented comparison cohort. Any result from it must remain labeled
  diagnostics-only and compared explicitly with, rather than merged into, the historical vanilla
  captures.
- Next test: enter Maelstrom near the original turtle camp, establish a smooth/lag state, then run a
  triggered capture that continuously drains exact present timing alongside process metrics.

## 2026-09-01 — Paired-process late-arrival experiment armed

### Experimental design

- Keep diagnostics-only PID 3196 logged in as the previously observed smoother late-arrival
  character, outside the turtle-camp exposure until the comparison point.
- Publish and launch a second diagnostics-only package with instance ID \`summoner\`. The package,
  current receipt, publication evidence, renderer status, PID, and creation time remain distinct
  from PID 3196. The launcher refuses a duplicate executable path while permitting another verified
  package path.
- Take the Summoner to the original turtle camp and deliberately build the familiar whole-world
  stutter and click starvation. Once degraded, summon the held-back character into the same local
  scene and capture both processes over the same wall-clock interval.
- Record exact present timing and process metrics for both PIDs. The comparison is within one VM
  session, so server state, turtle-camp population, and host load are substantially shared. The two
  simultaneous clients still add host contention and focus/background-window state as explicit
  confounds.

### Discriminating outcomes

- Degraded Summoner plus smooth late arrival in the same camp supports client-process-local
  accumulated state activated by the original camp.
- Immediate comparable degradation in the late arrival weakens the accumulated-exposure model and
  raises location/server/host-wide work.
- A difference that tracks character or class across repeated role swaps raises a character,
  ability, animation, or resource-set interaction; one paired run cannot establish that.

### Pending identities

- Late-arrival control: PID 3196, creation FILETIME UTC 134327142791034606, diagnostics-only
  package and extension identity recorded in the preceding entry.
- Summoner exposure client: pending publication and launch from named package instance \`summoner\`.
- Next action: publish and launch \`summoner\` without stopping PID 3196, then record its exact PID,
  creation time, and renderer-status path before movement.

## 2026-09-01 02:01 EDT / 06:01 UTC — Runtime-drift launch verifier defect

### Observed publication and failed launch

- Named diagnostics-only package \`summoner\` published and verified at
  \`C:\Users\admin\Wonderbane-diagnostics-wb-55fbad5f-present-1.5.6-summoner\`.
- A brief direct start opened and exited before an identity-bound renderer status was recorded.
  The following launcher preflight then refused the package because its entire working-tree digest
  no longer equaled the publication-time digest.
- Read-only audit expected tree
  \`e991ceb5fab8adc8745e260a4a41db4bce24747968211420ac5a14eba62218cc\` and found tree
  \`d2517ec450140aea236ebef9ab36a1b3e2d905dda96583ee637ea62a3da0cf46\`.
- No files were added. Changed files were \`DoubleFusion/dftm.dat\`,
  \`DoubleFusion/Engine.Log\`, \`DoubleFusion/User.var\`, and \`Logs/debug.txt\`.
  \`DoubleFusion/dfts.dat\` was missing. Every path was already classified by the package lifecycle
  as runtime-mutable.
- The audit did not report drift in \`sb.exe\`, the extension DLL, or any other immutable packaged
  asset. This is a tooling-verifier defect, not evidence of executable tampering.

### Tooling correction

- Publication retains exact whole-tree verification.
- Launch verification now permits changed or missing paths only from the existing bounded
  runtime-mutable allowlist. It rejects every added file and every changed or missing path outside
  that allowlist, then separately requires the exact packaged \`sb.exe\` and extension hashes.
- Next action: retry the named \`summoner\` launcher. If the process still exits, collect that
  startup failure independently of normal runtime-file drift.

## Journal maintenance rule

After every live test, append one entry containing:

1. local and UTC time;
2. exact VM, executable/fingerprint, PID/creation time, character role, and location;
3. turtle visibility and combat exposure count;
4. symptom state before, during, and after the action;
5. exact intervention or variable changed;
6. immutable manifest/artifact/report IDs when captured;
7. what the result supports, weakens, or leaves unresolved; and
8. the smallest next discriminating test.
