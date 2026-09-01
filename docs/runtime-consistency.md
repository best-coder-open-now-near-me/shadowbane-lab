# Runtime consistency gate

The runtime consistency pipeline treats an existing patcher-produced deployment as the build
under test. It does not alter the patcher, patch manifest, frozen baseline, or published client
trees. Before executing a scenario, it rereads `runtime-deployment.json`, verifies its stored patch
manifest and extension, and runs the complete package-inventory verification for every selected
runtime slot.

The pipeline has four immutable artifacts:

1. A **suite** declares the environment, scenario commands, repetition floor, numeric tolerance
   policy, and hard counter ceilings.
2. A **capture** binds every observation to the exact baseline, patch manifest, executable,
   extension, package tree, resolution, client slot, and host details.
3. A **baseline** is an explicit promotion of complete passing captures. Promotion refuses missing
   runs, failed runs, undeclared instrumentation, counter-ceiling violations, and semantic
   instability between repetitions or slots.
4. A **report** compares one candidate capture with a baseline and returns `pass`, `warn`, or
   `fail`. Release-blocking anomalies produce exit code `1`; invalid inputs or infrastructure
   failures produce exit code `2`.

Artifacts are create-only. Reusing an output path fails instead of replacing prior evidence.

## Built-in WonderBane health scenario

The example suite at
[`configs/wonderbane-runtime-consistency.example.json`](../configs/wonderbane-runtime-consistency.example.json)
runs the manager health probe against every produced runtime slot. The probe requires the client,
worker, and extension to already be running and healthy. It records:

- exact manager binding, attached state, and dispatch state;
- exact worker health, dispatch permit, and active-worker cardinality;
- initialized extension state and ABI version;
- extension event-channel readability, capability flags, pending events, producer errors, and drops;
- game-process working set, private bytes, and handle count;
- manager status latency and worker-heartbeat age; and
- worker issues, rejected windows, competing candidates, and queued or active operations.

The manager bearer token remains in the process environment and is never written to a capture,
baseline, report, command argument, or subprocess log. Configure the current dashboard endpoint
and token immediately before capture:

```powershell
$env:SHADOWBANE_MANAGER_URL = 'http://127.0.0.1:PORT'
$env:SHADOWBANE_MANAGER_TOKEN = Read-Host 'Dashboard bearer token'
```

The URL must be plain loopback HTTP. The probe rejects remote hosts, URL credentials, queries, and
fragments.

## Establish a known-good baseline

Use a fresh output path for every command. First validate the reviewed suite:

```powershell
shadowbane-runtime-consistency validate-suite `
  .\configs\wonderbane-runtime-consistency.example.json
```

With the known-good deployment running and all slots healthy, capture it:

```powershell
shadowbane-runtime-consistency capture `
  'C:\ShadowbaneLab\client-runtimes\known-good\runtime-deployment.json' `
  .\configs\wonderbane-runtime-consistency.example.json `
  'C:\ShadowbaneLab\runtime-evidence\known-good.capture.json'
```

Promote one or more independently reviewed captures. All captures must match the exact suite and
environment and satisfy its repetition floor:

```powershell
shadowbane-runtime-consistency promote `
  --baseline-id wonderbane-runtime-20260831 `
  --suite .\configs\wonderbane-runtime-consistency.example.json `
  --output 'C:\ShadowbaneLab\runtime-evidence\accepted.baseline.json' `
  'C:\ShadowbaneLab\runtime-evidence\known-good.capture.json'
```

Promotion is deliberate. A candidate does not teach or widen its own baseline.

## Gate a patcher-produced candidate

The `gate` command performs capture and comparison as one release step while retaining both
artifacts even when the comparison fails:

```powershell
shadowbane-runtime-consistency gate `
  'C:\ShadowbaneLab\client-runtimes\candidate\runtime-deployment.json' `
  .\configs\wonderbane-runtime-consistency.example.json `
  'C:\ShadowbaneLab\runtime-evidence\candidate.capture.json' `
  --baseline 'C:\ShadowbaneLab\runtime-evidence\accepted.baseline.json' `
  --report-output 'C:\ShadowbaneLab\runtime-evidence\candidate.report.json'
```

Exit status is the release boundary:

- `0`: pass, or warnings only;
- `1`: at least one release-blocking runtime anomaly;
- `2`: the deployment, suite, evidence, command, or comparison could not be trusted.

Warnings remain visible in the report. Build fingerprints are recorded but are not required to
match an accepted build: comparing a newly produced build is the point of the gate. Suite revision
and `environment_id` must match exactly so results from materially different VMs or calibrations
cannot be mixed accidentally.

## Scenario result contract

Every scenario is executed directly with `shell=False`. The pipeline supplies these environment
variables:

- `SHADOWBANE_RUNTIME_DEPLOYMENT_EVIDENCE`
- `SHADOWBANE_RUNTIME_DEPLOYMENT_DIRECTORY`
- `SHADOWBANE_RUNTIME_BUILD_FINGERPRINT`
- `SHADOWBANE_RUNTIME_CLIENT_ID`
- `SHADOWBANE_RUNTIME_CLIENT_DIRECTORY`
- `SHADOWBANE_RUNTIME_ENVIRONMENT_ID`
- `SHADOWBANE_RUNTIME_SCENARIO_ID`
- `SHADOWBANE_RUNTIME_REPETITION`
- `SHADOWBANE_RUNTIME_RESULT_PATH`

The command must create the result path as schema-v1 JSON:

```json
{
  "schema_version": 1,
  "scenario_id": "example",
  "passed": true,
  "terminal_reason": "completed",
  "semantic": {"state": "stable"},
  "metrics": {"observation_latency_ms": 12.5},
  "counters": {"event_drops": 0}
}
```

`semantic` must be deterministic, finite JSON and is compared exactly after canonicalization.
Metrics are non-negative finite numbers. Counters are non-negative integers. The pipeline adds the
reserved `pipeline.wall_duration_ms` metric; scenario output must not provide it. Metric and counter
names must exactly match the suite so instrumentation cannot disappear silently.

Numeric tolerance is declared per metric. The baseline stores count, minimum, median, 5th and 95th
percentiles, maximum, and median absolute deviation. Candidate medians, tails, and variability are
checked against the maximum of the declared absolute tolerance, relative tolerance, and MAD
multiplier. Counters use baseline maximum plus an explicit permitted increase, optionally capped by
an absolute maximum. Drops, errors, restarts, and rejected observations should normally use an
absolute maximum of zero.

Additional scenarios can cover controlled movement, combat, event-channel drops, resource usage,
and long-running soak behavior without changing the pipeline contract. Each should emit semantic
state rather than volatile process IDs, timestamps, or evidence paths.
