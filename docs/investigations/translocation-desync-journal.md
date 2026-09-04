# Shadowbane translocation and movement-desync investigation journal

This is the canonical human-readable journal for the intermittent long-path movement correction
case. It is intentionally separate from the Maelstrom turtle-camp degradation journal. The two
symptoms may interact, especially through environment streaming, but no evidence currently proves
that they share a root cause.

Append new dated entries after every observation, capture, intervention, or conclusion change.
Preserve earlier entries and correct them with a later entry instead of silently rewriting history.
Do not ask the operator to reconstruct observations already recorded here unless a new result
directly contradicts them or requires one missing discriminating detail.

Keep these evidence classes distinct:

- **Operator observation:** what the player directly saw or felt.
- **Instrumented evidence:** what a named, verified artifact measured.
- **Inference:** an explanation consistent with current evidence but not yet demonstrated.
- **Ruled out or weakened:** a hypothesis contradicted by a controlled intervention or capture.

## Current case summary

- **Symptom:** During extended click-to-move travel, the displayed character can become materially
  displaced from its subsequently corrected position. The client eventually snaps the character
  to another position. Some events also show the translocation transition screen.
- **Occurrence:** Intermittent. It does not happen on every environment-load batch or every long
  movement command.
- **Strongest known precursor:** One click-to-move instruction covering roughly a full minimap
  distance without another click. Reclicking during the route appears to reset or bound the
  divergence.
- **Streaming relationship:** A correction can happen while another environment batch is already
  loading. Consequently, waiting for a fully settled loading state is not a valid prerequisite for
  reproduction; sufficiently long traversal naturally crosses streaming boundaries.
- **Candidate inputs:** Long command duration or distance, environment streaming, water traversal,
  and travel-stance changes to base speed. Their individual contributions have not been isolated.
- **Leading model:** Client-side movement, path, collision, or speed prediction accumulates a
  difference from the authoritative position during a long uninterrupted movement command. A
  later correction crosses either a visual snap threshold or the threshold that invokes the
  translocation presentation. This is an inference, not yet a directionally measured client/server
  position delta.
- **Evidence boundary:** Current sealed evidence has process counters and event timing around one
  observed event, but no authoritative client/server position pair, movement-command lifecycle,
  network-packet summary, streaming-batch state, or exact frame timing.

## Established operator observations

These observations have already been reported and should be treated as the working behavioral
baseline:

1. An early Maelstrom occurrence looked like a short translocation of only a few meters while the
   environment was streaming poorly.
2. Water and travel stance were suspected because they change base movement speed. A mismatched
   speed transition could make client prediction and authoritative movement disagree.
3. A later event occurred on the Druid/Summoner client during a paired live capture.
4. The reproducible precursor is a single long click-to-move route of approximately one full
   minimap distance without reclicking.
5. At the end of the divergence, the character snaps to a corrected position. The translocation
   transition screen appears on some events, not all events.
6. Reclicking during travel appears to reset or limit the problem.
7. The event is intermittent, which makes a cleanly settled loading state impractical as a test
   requirement.
8. A long route can trigger the correction while the client is already loading another environment
   batch. Streaming may amplify the mismatch or delay its resolution, but it is not established as
   the initiator.
9. The apparent server/client desynchronization becomes especially conspicuous during zone or
   environment loading. This is an operator interpretation pending direct position evidence.

## 2026-08-31 — Initial Maelstrom movement-correction observations

### Operator observation

- While investigating whole-client stutter in Maelstrom, the character translocated once by only a
  few meters and environment streaming appeared badly delayed.
- The entire client could also stutter and stop accepting clicks during the broader turtle-camp
  degradation. That input-starvation symptom belongs to the Maelstrom lag case unless evidence
  connects it directly to the movement correction.
- Water and travel stance were identified as plausible movement-speed mismatch inputs before the
  long-click precursor was refined.

### Interpretation boundary

- The short snap and the turtle-camp performance degradation were contemporaneous, not proven to
  have the same cause.
- Neither a visible snap nor the transition screen proves that the server issued a teleport
  operation. Both can be client presentation of an authoritative position correction.

## 2026-09-01 — Paired vanilla capture contains one observed event

### Runtime identity

**Instrumented evidence / operator role mapping**

- VM: regular `shadowbane` VM, not `shadowbane-testing`.
- Both processes were ordinary already-running clients at
  `C:\Users\admin\Downloads\WonderbaneClient\Wonderbane\sb.exe` and were attached read-only.
- Summoner/Druid exposure process: PID `5416`, creation FILETIME
  `134327166591639685`.
- Later-arrival comparison process: PID `8856`, creation FILETIME
  `134327179791160804`.
- Both captures reported execution fingerprint ID
  `sha256:9b9c672c5ab66496727c0ac3a214f7404f5910e819cb5fef535663a43b736f60`.

### Event and trigger

**Operator observation**

- The operator saw the Druid/Summoner translocate after the paired collector had attached and
  created the shared trigger marker immediately after the event.
- The exact start and end positions, displacement, movement surface, stance, click time, streaming
  phase, and transition-screen presence were not recorded for this occurrence.

**Instrumented evidence**

- Shared marker:
  `C:\Users\admin\shadowbane-lag-trigger-maelstrom-pair-c06ea3d-01.marker`.
- Both runs started at `2026-09-01T06:39:50.198Z`, retained the shared trigger, completed their
  post-trigger windows, and reported no channel omissions.
- PID `5416` run:
  - run ID `diag-4a9ea59795d94ff39ff0932a7d93c66d`;
  - manifest ID
    `sha256:63843f63b5b0adc28a4ad3755353a171304517d10701163d0f71f22fcc71d118`;
  - analysis report ID
    `sha256:95373e59a2f08c4e422fe01a6ec609bcb80344758c898631ebdfb30ba4ddfff9`;
  - 1,051 samples over 288.297 seconds, ending `2026-09-01T06:44:03.104Z`.
- PID `8856` run:
  - run ID `diag-98a43b8b52c943eba0c1da9ea07fdad3`;
  - manifest ID
    `sha256:c9ac6368750062227ebf318785615e67eef3791a610d9faa5a2780281c10ed02`;
  - analysis report ID
    `sha256:379820e46a76bdde55355e8967eefac7a27239157ab598b8f61e51c52fe2ac91`;
  - 1,053 samples over 288.422 seconds, ending `2026-09-01T06:44:03.262Z`.

### Counter context and limitations

**Instrumented evidence**

- PID `5416` performed sustained CPU and page/working-set work across the capture: about 6,214
  process page faults per second, 1.356 user plus 0.381 kernel core-equivalents, and approximately
  259 KB/s of process reads. Private bytes and working set both ended lower than they began despite
  large internal ranges.
- PID `8856` was in a major load/build-up phase: about 15,492 process page faults per second,
  approximately 950 KB/s and 734 process read operations per second, with private bytes growing by
  about 641 MB and working set by about 628 MB. It is not a settled control for the event.
- These different aggregate signatures establish that substantial client work was occurring. They
  do not isolate the event second or identify movement correction as the cause of either signature.
- Both capture summaries explicitly state that exact frame timing was omitted because no
  identity-bound runtime producer was supplied. Static graphics-present import evidence is not
  frame telemetry.
- No capture channel recorded client position, authoritative/server position, movement command,
  packet timing or payload, stance, surface, collision result, or streaming-batch boundaries.

### Result

- This is a valid time-bounded capture around an operator-observed translocation on PID `5416`.
- It is not yet proof of a client/server position delta, its direction, its magnitude, or its
  initiating subsystem.
- Raw sealed samples remain useful for correlating future reconstructed event timing, but process
  totals alone cannot decide between movement prediction, collision/path delay, streaming stalls,
  network delivery, or a server correction.

## 2026-09-01 — Long-path trigger refined after repeated occurrences

### Operator observation

- The behavior is intermittent.
- A characteristic reproduction uses one long click covering roughly a full minimap distance with
  no reclick. The character eventually snaps into the corrected location.
- Some corrections invoke the translocation transition screen.
- Periodic reclicking appears to reset or bound the divergence.
- The correction can occur while another environment batch is already loading. The test therefore
  must include normal streaming activity instead of waiting for a condition that the long traversal
  itself invalidates.

### Updated interpretation

- **Strengthened:** Command duration or uninterrupted path length is a discriminating variable.
- **Strengthened:** A client movement/path/prediction lifecycle reset on reclick is plausible.
- **Plausible but unproven:** Streaming delays collision, path, or movement updates long enough for
  the apparent divergence to become large.
- **Plausible but unproven:** Water or travel-stance base-speed changes supply the initial speed
  mismatch.
- **Not established:** Whether the corrected endpoint comes from server authority, delayed client
  path evaluation, collision resolution, a zone-boundary mechanism, or another source.
- **Not established:** Whether the transition screen is keyed to correction distance, loading
  state, zone boundary, elapsed divergence, or a different condition.

## Controlled reproduction matrix

Use the same character, route, camera, and starting conditions within each pair. Do not require
loading to settle. Mark command start and the correction itself.

1. **Command segmentation**
   - Trial A: one full-minimap-distance click, no reclick.
   - Trial B: same route with short segmented clicks or a reclick every few seconds.
2. **Surface and speed state**
   - Repeat the pair entirely on land in normal stance.
   - Repeat entirely on land in travel stance.
   - Repeat across entry into and exit from water.
   - Repeat across a travel-stance speed transition.
3. **Streaming pressure**
   - Repeat the pair on a previously traversed route.
   - Repeat on a route expected to load new environment batches.
4. **Character and session boundary**
   - Repeat on the same character after relog.
   - Repeat on a second client/character using the same route and click pattern.

Record event count as `events / completed trials`; do not treat one non-event as a failed
reproduction because the case is intermittent.

## Instrumentation required to resolve the case

The next durable tooling slice should attach to already-running clients and tag every stream by PID
and creation time. It should not require a restart.

1. Record monotonic markers for movement-command start, reclick, manual symptom mark, snap, and
   transition-screen onset where each can be observed safely.
2. Add a reviewed read-only client-position producer with sample time, position, movement state,
   target/path state, stance, and zone identity. Unresolved mappings must remain unavailable rather
   than guessed.
3. Add a bounded network summary sufficient to correlate receive gaps, bursts, sequencing, and
   latency around the event without claiming packet semantics that have not been decoded.
4. Add identity-bound exact present timing so the snap can be separated from a presentation stall.
5. Correlate process reads, page faults, CPU, and working-set oscillation with the event window and
   any observable environment-load boundary.
6. Preserve the raw streams and clock anchors so alternative offline hypotheses can be tested
   without asking the operator to reproduce the event again.

## Journal maintenance rule

After every trial or spontaneous event, append one entry containing:

1. local and UTC time;
2. VM, executable fingerprint, PID and creation time, character, zone, and route;
3. starting surface and stance plus every water or stance transition;
4. initial click time and approximate commanded distance;
5. whether and when the operator reclicked;
6. streaming/loading state before and during the correction;
7. snap direction and approximate distance, and whether the transition screen appeared;
8. exact event marker plus immutable manifest, artifact, and report IDs;
9. what the result supports, weakens, or leaves unresolved; and
10. the smallest next discriminating trial.
