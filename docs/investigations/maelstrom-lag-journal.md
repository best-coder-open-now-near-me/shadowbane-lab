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
