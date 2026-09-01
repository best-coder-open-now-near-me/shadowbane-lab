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

## Profiles

| Profile | Default window | Process interval | Heavy-channel retention | Completion condition |
| --- | ---: | ---: | --- | --- |
| standard | 300 s | 1 s | All requested bytes, within per-channel bounds | Requested window and channels complete |
| full | 300 s | 250 ms | All requested bytes, within per-channel bounds | Requested window and channels complete |
| triggered | 1,800 s max | 250 ms | Last 60 s before the trigger plus 30 s after it | Trigger observed, post-window complete, and requested channels complete |

Full means higher-frequency core counters plus every channel explicitly requested on the command.
It does not silently start privileged collectors. This distinction keeps a run honest: an omitted
ETW trace is not reported as captured.

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

## Exact process and patched-client identity

Every process sample reads the image path, PID, and Windows process creation FILETIME through the
same live handle as the counters. PID reuse, process restart, or image-path drift fails closed and
seals the partial evidence. The run also fingerprints:

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
