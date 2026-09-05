# Capture-once diagnostics

The diagnostic workflow captures one bounded live session into the immutable evidence store, then
lets analysis evolve without repeating the live reproduction. It is read-only: the collector opens
the exact client process for identity and counters, tails named files, and optionally captures a
screen rectangle. It does not send input, write process memory, generate a dump, start ETW, or start
a packet capture.

Use the local launcher for an ordinary run:

    .\scripts\capture-shadowbane-diagnostics.ps1 -Profile standard

The launcher never downloads source, invokes a network script, evaluates downloaded text, or
changes PowerShell execution policy. It resolves exactly one running process whose image path
matches -ClientExecutable, creates a unique local output directory, runs the repository CLI, and
reanalyzes the sealed capture.

The normal workflow attaches to a client that is already running. It does not restart the game,
patch the executable, inject a DLL, or write process memory. When several clients use the same
executable path, select one exact live process explicitly:

    Get-CimInstance Win32_Process -Filter "Name='sb.exe'" |
        Select-Object ProcessId, CreationDate, ExecutablePath

    .\scripts\capture-shadowbane-diagnostics.ps1 -Profile triggered -ProcessId 6888

The wrapper verifies that the selected PID still belongs to the exact requested executable path.
The collector then binds every sample to PID, process creation FILETIME, and executable identity;
restart, PID reuse, or path drift fails closed while preserving the partial evidence.

To attach to every live client using the exact executable path, run:

    .\scripts\capture-shadowbane-diagnostics.ps1 -Profile triggered -AllMatchingProcesses

The wrapper snapshots the matching processes, reports each PID and creation FILETIME, and starts one
concurrent capture per process. Each subcapture has its own PID-tagged directory, manifest, process
identity, and immutable store. Triggered subcaptures can share one manual marker, which makes their
pre-trigger and post-trigger windows comparable without merging their evidence.

## Profiles

| Profile | Default window | Process interval | Heavy-channel retention | Completion condition |
| --- | ---: | ---: | --- | --- |
| standard | 300 s | 1 s | All requested bytes, within per-channel bounds | Requested window and channels complete |
| full | 300 s | 250 ms | All requested bytes, within per-channel bounds | Requested window and channels complete |
| triggered | 1,800 s max | 250 ms | Last 60 s before the trigger plus 30 s after it | Trigger observed, post-window complete, and requested channels complete |

Full means higher-frequency core counters plus every channel explicitly requested on the command.
It does not silently start privileged collectors. This distinction keeps a run honest: an omitted
ETW trace is not reported as captured.

## Turtle-camp hotspot protocol

Use the focused protocol when one run must distinguish cold arrival streaming from warm resident
slowdown:

    .\scripts\capture-shadowbane-diagnostics.ps1 -HotspotProtocol -ProcessId 6888

`-HotspotProtocol` binds one exact PID and creation time, enables aggregate performance telemetry,
samples process/player state every 125 ms (8 Hz), and uses a 300-second safety limit. A manual
`complete` marker ends it early. The native producer publishes exactly one aggregate record per
present: frame time plus cache-read and texture-upload count, bytes, and summed duration. It does
not publish one event per read or upload.

The launcher prints the unique evidence directory and four exact marker commands before capture.
Run those commands in another terminal at these visible boundaries:

1. Mark `cold-approach` immediately before approaching and crossing the camp center.
2. Mark `stationary` on arrival, then stand still there for about 20 seconds.
3. Leave the area, mark `warm-return`, and cross the same center again.
4. Mark `complete` with `--finish` after the warm crossing.

The underlying command is create-only and authenticated to that capture. For example:

    python -m shadowbane_lab.cli diagnose mark <evidence-directory> `
        'stationary at camp center' --phase stationary

It only writes a marker beside the capture. It never injects a key, sends window input, writes game
memory, or guesses an offset. Restart or PID reuse still fails closed. Player LT, LG, and altitude
come only from a reviewed exact-build mapping; camera samples are included when the exact
identity-bound graphics status is available.

The capture writes and seals one convenience file named `<run-id>.timeline.json` in the evidence
directory. It contains every retained frame, aggregate cache/upload totals, 5-10 Hz player samples,
camera samples when available, all observation markers, nearest-sample references, and phase-aware
hitch classifications. Its summary keeps the two expensive follow-ups evidence-gated:

- `cpu_stack_capture_recommended` becomes true only after at least three stationary slow frames
  have neither cache reads nor texture uploads.
- `texture_identity_followup_recommended` becomes true only when the warm return still uploads
  textures; IDs and lifetimes can then determine whether the same assets are repeating.

The aggregate timeline cannot identify a CPU call stack or prove that two uploads name the same
texture. Those remain separate optional captures so the normal reproduction stays low-overhead.

### Optional stationary CPU stacks

When `cpu_stack_capture_recommended` is true and the same exact client lifetime is still running,
stand still at the reproduced slowdown and run:

    .\scripts\capture-shadowbane-stationary-cpu-stacks.ps1 `
        -CaptureDirectory '<completed-evidence-directory>' `
        -ConfirmStationary

The default trace is 10 seconds and the accepted range is 1-30 seconds. Before arming WPR, the
launcher asks `diagnose stack-plan` to verify the content-addressed store and complete manifest,
prove that the convenience timeline equals its sealed artifact, require all three hotspot phases,
and require the timeline's positive recommendation. It then verifies PID, creation FILETIME, and
executable path before and after the trace. Restart, PID reuse, path drift, an incomplete run, or a
changed convenience file fails closed.

Windows CPU sampling is system-wide at collection time. The receipt says that explicitly; it does
not mislabel the ETL as a PID-filtered collection. Analysis must filter to the exact target PID and
creation lifetime recorded in `capture.json`. The launcher refuses to start when another WPR
session is active, uses the built-in CPU profile, limits the duration, and writes the ETL and a
hashed create-only receipt outside the sealed diagnostic directory. It does not inject game input
or write process memory. WPR may require an elevated terminal.

`texture_identity_followup_recommended` is a separate gate. When false, no texture-identity capture
is justified. When true, the next producer extension should record bounded texture IDs/generations,
allocation/deletion lifetimes, and aggregate upload bytes so repeated warm uploads can be proven;
the base capture intentionally does not pay that overhead or pretend aggregate bytes identify an
asset.

The triggered CLI supplies two conservative defaults when no explicit or manual trigger is given:

- private bytes grow by at least 256 MiB from the first sample for two consecutive samples; or
- process handles grow by at least 512 from the first sample for two consecutive samples.

Override them with repeatable rules:

    --trigger process_private_bytes:ge:134217728:3:delta
    --trigger process_handle_count:ge:2000:2

The operator form is METRIC:OP:THRESHOLD[:COUNT[:delta]]. Operators are ge, gt, le, and lt.
Delta compares with the first sample; omission means an absolute value.

For a manual lag marker, choose a path that does not exist before capture:

    $marker = "$env:TEMP\shadowbane-lag-marker.txt"
    .\scripts\capture-shadowbane-diagnostics.ps1 -Profile triggered -ManualTriggerFile $marker

    # In another terminal, at the visible lag:
    New-Item -ItemType File -Path $marker

The collector observes the marker but does not create or delete it.

When `-OutputRoot` is a UNC path, the launcher keeps the content-addressed store on the VM's local
filesystem because VirtualBox shared folders do not provide the atomic rename semantics required by
the store. After sealing and analyzing the capture, it creates a portable verified evidence bundle,
copies the bundle and derived analysis to the requested share, verifies their SHA-256 values, writes
an export receipt last, and removes the local staging directory. A failed or interrupted export does
not weaken store semantics or masquerade as a completed export.

## Exact process and patched-client identity

Every process sample reads the image path, PID, and Windows process creation FILETIME through the
same live handle as the counters. PID reuse, process restart, or image-path drift fails closed and
seals the partial evidence. The run also fingerprints:
Process discovery and metric capture use separate probes. The discovery identity selects and
fingerprints the exact executable; after the store and collectors are ready, the process is sampled
again and that fresh observation becomes sample 1 and the capture clock origin. PID/creation
identity or executable-path drift between those probes blocks capture start. Fingerprinting time and
counter changes are therefore never compressed into the first sampling interval, so whole-window
deltas and rates no longer require a manual first-sample exclusion.


- the exact live executable bytes and PE layout;
- the whole client tree when --client-directory is supplied;
- the runtime executable, repository revision, operating system, Python runtime, and scenario.

For a patched moving target, pass the last trusted or reviewed executable:

    .\scripts\capture-shadowbane-diagnostics.ps1 -Profile full -ReferenceExecutable 'D:\baselines\sb-reviewed.exe'

The diagnostic bundle stores the existing client-alignment report: exact hashes, PE and section
layout, changed ranges, applicable native profiles, and changed-range intersections with calibrated
RVA anchors. A non-exact result is always labeled candidate-evidence-only;
automatic_compatibility_promotion remains false, and dependent native decoders must treat unresolved
mappings as blocked.

The current alignment engine is conservative, not a completed semantic relocator. It does not yet
claim normalized instruction, control-flow, call-graph, or field-access equivalence. Those can be
added as new derived evidence without changing the raw capture.

## Graphics-present evidence

The PowerShell launcher always requests the first-class `graphics-present` channel. It reads the
exact live executable bytes, seals the complete PE identity, and inventories these supported frame
presentation imports without claiming that an imported function is the active runtime route:

- `GDI32.dll!SwapBuffers`
- `OPENGL32.dll!wglSwapLayerBuffers`

Static import presence has `exact-live-executable-bytes` authority. The active route remains
`unresolved`, and renderer work that depends on a proven frame boundary remains blocked, until the
extension publishes identity-bound runtime status with a positive call count. The launcher derives
the exact status filename from the selected process ID and its creation FILETIME and includes it
automatically when that file exists under
`%LOCALAPPDATA%\ShadowbaneLab\client-extension`. An explicit path remains available for offline or
relocated evidence:

    .\scripts\capture-shadowbane-diagnostics.ps1 -Profile full -GraphicsRuntimeStatus 'C:\ShadowbaneLab\graphics-status.json'

Runtime status must use schema version 2 and producer ID `wonderbane-extension.graphics`. It must
match the captured PID, process creation FILETIME, executable path, and executable SHA-256. Its
active entry must match an exact PE import and have a positive observed call count. A mismatched,
stale, malformed, or missing requested status file is retained as rejected evidence and makes the
capture incomplete rather than silently promoting a candidate.

Attaching to an ordinary uninstrumented client therefore keeps process, identity, static-present,
log, screenshot, and explicitly supplied channels, but does not invent renderer timing. The
capture summary warns that frame-timing was omitted because no identity-bound runtime producer was
supplied. An external PID-bound producer can fill that channel in the future without changing the
live-attachment contract.

Schema version 2 also makes renderer timing a required `frame-timing` channel whenever runtime
status is requested. The collector continuously polls the identity-bound status, establishes the
first accepted present sequence as its baseline, and drains only later QPC-stamped presents. It
deduplicates by sequence and seals the raw sequence, QPC counter, observation time, producer clock
anchors, query-failure delta, capture-side drops, and every missing range.

The extension retains only its newest 1,024 presents; capture therefore polls continuously rather
than reading status once at the end. If the producer ring overtakes the next expected sequence, a
timing query fails, a status poll fails, or the bounded two-million-sample capture limit is reached,
the artifact remains available but the required channel and manifest are explicitly incomplete.
Triggered capture retains timing first observed in its configured pre/post window plus the nearest
preceding clock anchor.

Offline analysis derives average FPS, frame-time minimum/median/p95/p99/maximum, and explicit hitch
counts at 33.3, 50, 100, and 250 milliseconds. Each retained hitch includes its exact present
sequence and QPC interval plus an estimated UTC presentation time derived from the nearest sealed
QPC/FILETIME anchor. The raw timing artifact remains authoritative and can be reanalyzed without
repeating gameplay.

## World position and camera state

The local launcher also requests reviewed native player position. Every successful observation
records LT, LG, and altitude on the exact same session-monotonic timestamp as its process-counter
sample. The reader is bound to PID, creation FILETIME, executable path and SHA-256, and a reviewed
native-layout profile. A patch without a reviewed compatible mapping produces a named
`native-position` omission; client-alignment candidates are never promoted into read authority.
Offline analysis retains the first and last position, sampled bounds and distance, and the largest
world-space transitions. The raw capture stream remains available for reconstructing a different
region or transition policy later.

When identity-bound graphics runtime status is available, the launcher also requires the
`camera-state` channel. This is a deliberately narrow producer/consumer seam:

- the native extension observes fixed-function scene-view state without changing it and publishes a bounded ring;
- diagnostics validates exact process and executable identity, drains new sequences, stamps the
  samples on the process-metric monotonic clock, records every producer/capture gap, and seals the
  retained ring; and
- offline analysis derives camera movement and angular change, matches camera samples to present
  frame times, and calculates descriptive correlations with process-counter deltas.

The producer object is additive under graphics runtime status schema 2 and uses this contract:

    "camera_state": {
      "schema_version": 1,
      "clock": "windows-query-performance-counter",
      "counter_frequency_hz": 10000000,
      "source": "unique-base-model-view-per-present",
      "mapping_authority": "runtime-observed-fixed-function-state",
      "latest_sample_sequence": 42,
      "oldest_available_sequence": 1,
      "sample_capacity": 256,
      "sample_count": 42,
      "producer_drop_count": 0,
      "samples": [{
        "sequence": 42,
        "present_sequence": 733,
        "counter": 123456789,
        "position": [1.0, 2.0, 3.0],
        "forward": [0.0, 0.0, -1.0],
        "up": [0.0, 1.0, 0.0],
        "zoom": 1.0,
        "vertical_fov_degrees": 60.0,
        "view_matrix": [16 finite column-major values],
        "projection_matrix": [16 finite column-major values],
        "viewport": [0, 0, 1280, 720]
      }]
    }

Sequences and QPC counters increase, `forward` and `up` are normalized and orthogonal, FOV is in
degrees, and the ring bounds and counts must
agree. The producer selection policy is named rather than inferred by diagnostics. A missing,
malformed, identity-mismatched, overwritten, or dropped camera stream leaves all other evidence
intact but makes the requested channel explicitly incomplete. Current renderer work owns production
of this object; non-render code must not install GL hooks or guess camera addresses to satisfy it.

Extension 1.6.2 implements that producer in both native profiles. It considers only filled,
perspective, depth-writing draws observed at model-view stack depth one. Every qualifying view,
projection, and viewport in a present must be byte-identical; a conflict rejects the whole camera
sample and increments `producer_drop_count`. `zoom` is the absolute vertical projection scale and
vertical FOV is derived as `2 * atan(1 / zoom)`.

The navigation-inspector branch replaces full-profile per-draw sampling with
`reviewed-main-scene-boundaries`: capture the outer model-view at the verified main clear,
then require byte-identical view/projection/viewport at the verified pre-UI boundary,
the same graphics context, stack depth one at both boundaries, and a nonempty,
uninvalidated main scene. Object transforms inside the world queue cannot nominate a
camera. Missing, duplicate, changed or stale scenes cannot publish one. This adds
only two bounded camera reads per eligible frame and removes the per-draw camera
queries. World alignment still requires the joint live acceptance pass.

The diagnostics-only profile retains the original passive rule and source name.
It uses a separate pass-through module
that redirects four exact, reviewed OpenGL imports and always invokes the original function without
changing OpenGL state. It performs no game-data memory writes and uses no client offsets or
alignment guesses; validated IAT redirection is its only in-process instrumentation.

The depth-edge prerequisite assessment is deliberately conservative. It becomes ready only after
runtime evidence observes an active present entry, an active graphics context, a nonzero depth
buffer, depth-texture support, and GLSL support. Framebuffer-object support is recorded separately;
its absence does not erase the evidence or imply that a copy-based depth path is impossible.

## Additional channels

Convenience switches cover common evidence:

    .\scripts\capture-shadowbane-diagnostics.ps1 -Profile full -Log 'C:\WonderBane\logs\client.log' -ExtensionEvents 'C:\ShadowbaneLab\events.jsonl' -NetworkSummary 'C:\captures\connections.json' -PacketCapture 'C:\captures\session.pcapng' -EtwTrace 'C:\captures\session.etl' -ProcessDump 'C:\captures\sb.dmp' -Snapshot 'C:\captures\manager-health.json' -ScreenshotRegion '100,100,1280,720'

Log and extension-event channels are tailed each sampling interval. They preserve bounded initial
context, source offsets, rotation/truncation, byte hashes, and drop accounting. Snapshot, PCAP, ETW,
and dump paths are read at session start and end; a producer can create the final file during the
session. Stop and finalize an external collector before this diagnostic window ends if its output
must be included.

Arbitrary producers use:

    --channel-file CHANNEL=KIND=MODE=MEDIA=PATH

For example:

    --channel-file semantic-decisions=semantic_trace=tail=application/x-ndjson=C:\captures\decisions.jsonl
    --channel-file gpu-snapshot=runtime_snapshot=snapshot=application/json=C:\captures\gpu.json

KIND must be an evidence ArtifactKind; MODE is tail or snapshot. Each channel is bounded by
--max-channel-mib. A size overflow is a named drop and makes the manifest incomplete.

Packet captures, dumps, logs, screenshots, alignment paths, and summaries can contain secrets or
machine/account identifiers. All diagnostic artifacts are marked redaction: pending under
diagnostic-sensitive-v1. Review and redact them before sharing.

## Direct CLI and offline reuse

The launcher is a convenience wrapper around:

    $env:PYTHONPATH = 'src'
    python -m shadowbane_lab.cli diagnose capture C:\captures\lag-001 --pid 1234 --profile triggered --client-executable C:\WonderBane\sb.exe --client-directory C:\WonderBane --reference-executable D:\baselines\sb-reviewed.exe --json

Reanalyze the same raw samples as often as needed:

    python -m shadowbane_lab.cli diagnose analyze C:\captures\lag-001\store C:\captures\lag-001\manifests\diag-....manifest.json --output C:\captures\lag-001\analysis-v1.json --json

Compare a known-good run with a candidate:

    python -m shadowbane_lab.cli diagnose compare C:\captures\good\store C:\captures\good\manifests\diag-good.manifest.json C:\captures\candidate\store C:\captures\candidate\manifests\diag-candidate.manifest.json --output C:\captures\good-vs-candidate.json --json

Analysis verifies the source manifest first, reads the immutable raw stream, and derives per-counter
minimum, maximum, mean, median, p95, p99, net delta, delta rate, and least-squares slope. It reports
sample gaps, producer health, explicit growth candidates, frame-time and hitch distributions when
present, capture omissions, and client-alignment authority. Before/after comparison rereads both
raw streams and includes descriptive counter/frame-timing differences, effect sizes, and
fingerprint-confounder warnings.

Derived reports contain stable content IDs and source manifest/artifact IDs. They do not mutate the
raw store.

## Output and exit states

Each capture directory contains:

    store/                       immutable SHA-256 objects
    manifests/<run>.manifest.json
    analysis.json                launcher-generated offline report

The manifest is the authority. Complete means every requested channel and window completed.
Incomplete preserves useful evidence but names missing channels, no-trigger outcomes, early process
exit, unavailable screenshot dependencies, and byte drops. Failed covers identity drift or a run
with no metric samples.

Exit code 0 means complete capture or successful offline analysis. Exit code 1 means a capture was
sealed but incomplete/failed. Exit code 2 means setup, validation, or source verification failed.

Sampled counters can show when private/working-set memory, handles, GUI objects, CPU time, page
faults, or I/O changed. They cannot alone prove which thread, GPU queue, kernel scheduler event, or
network message caused lag; request the matching raw channel and correlate it with the shared
markers.
