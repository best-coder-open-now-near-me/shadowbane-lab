# Evidence spine delivery plan

This plan implements [the evidence-spine architecture](evidence-spine.md) adopted by ADR 0004.

## Delivery policy

The evidence spine is delivered as production vertical slices. Each slice must leave behind a
usable contract, migration path, tests, operator documentation, and a coherent Git checkpoint.
Disposable command surfaces or unversioned intermediate stores are not delivery milestones.

The first objective is not to capture every possible channel. It is to make three representative
cases fully reproducible and queryable while establishing boundaries that later binary, asset, and
protocol tooling can extend.

The modular CLI consolidation remains a prerequisite for adding the new installed command groups.
Integrity, storage, model, and adapter work may proceed independently, but it must not add temporary
top-level parsers that will immediately be replaced.

## Dependency order

```text
ES-0 shared integrity primitives
  -> ES-1 artifact store and evidence manifests
      -> ES-2 fingerprint envelope
          -> ES-3 case and experiment runner
              -> ES-4 capture alignment and differential cases
                  -> ES-5 coverage, planning, and impact
                      -> ES-6 deeper forensic producers
                          -> ES-7 operational reporting and retention
```

No later slice should introduce a competing digest, canonical JSON, artifact, fingerprint, or case
contract.

## ES-0: Shared integrity foundation

### Scope

Extract the strict primitives duplicated by client baselines, patch packages, alignment reports,
runtime consistency evidence, and PvE evidence.

### Deliverables

- `shadowbane_lab.integrity` internal package
- Strict JSON decoder with duplicate-key and non-finite-number rejection
- Canonical JSON encoder and canonical payload digest
- Identifier, SHA-256, timestamp, relative-path, and size validators
- Bounded immutable tree inventory and deterministic tree digest
- Safe create-only JSON and binary placement
- Reparse-point, traversal, overwrite, and root-boundary protection
- Unit fixtures proving existing artifact digests remain stable where contracts already exist

### Migration

Existing packages adopt the primitives one at a time without changing their public schema or CLI.
Compatibility tests compare old and new serialized payloads before each migration commit.

### Gate

All existing tests pass; every migrated producer emits byte-identical canonical content or carries
an explicit schema revision and migration receipt.

## ES-1: Artifact store and evidence manifests

### Scope

Create the immutable evidence substrate without changing live capture behavior.

### Deliverables

- `artifact-descriptor-v1`, `evidence-manifest-v1`, and `verification-receipt-v1` schemas
- Filesystem object store keyed by SHA-256
- Two-phase staging, hashing, redaction-policy validation, placement, reread, and sealing
- Manifest verification and portable evidence bundles
- Configurable object-store resolver separated from manifest paths
- Rebuildable SQLite index for artifact, manifest, run, case, and reference lookup
- `evidence ingest`, `verify`, `bundle`, `query`, and `rebuild-index` commands
- Quarantine report for unreferenced staged objects; no automatic deletion in version 1

### Migration

Provide import adapters for:

- checked-in `evidence/pvp` manifests;
- runtime consistency captures and reports;
- client baseline, patch-diff, package, and deployment evidence;
- PvE trace evidence;
- local screenshots and generated reports selected explicitly by an operator.

Imports preserve source bytes and produce migration receipts. They do not rename, rewrite, or delete
the source files.

### Gate

An evidence bundle can be copied to a clean directory and verified without access to the original
paths or generated SQLite index.

## ES-2: Complete fingerprint envelope

### Scope

Compose existing identity evidence into one mandatory execution fingerprint.

### Deliverables

- `fingerprint-envelope-v1` schema and typed model
- Client installation, runtime, service, environment, fixture, and lab-execution sections
- Adapters for baseline, PE inspection, package/deployment, extension status, manager health,
  character snapshot, native observations, and Git/package revisions
- Stable digest that excludes explicitly volatile observations
- Section completeness and `not_applicable` policy
- `fingerprint capture`, `verify`, and `diff` commands
- Machine-readable compatibility and invalidation findings

### Migration

Runtime consistency continues to own its release artifacts. It includes or references the common
fingerprint rather than growing a second identity model. Existing native profiles remain hash-pinned
and require reviewed layout-family evidence.

### Gate

Two captures of an unchanged environment receive the same fingerprint despite process IDs, module
bases, handles, and wall-clock changes. Every declared durable change produces a new fingerprint or
a failed capture.

## ES-3: Research cases and experiment runner

### Scope

Make one bounded research question executable and reviewable from a versioned definition.

### Deliverables

- `research-case-v1` and `experiment-definition-v1` schemas
- Bounded experiment step algebra
- Preconditions, variables, capture requirements, repetition, oracle, safety, and output policies
- Case lifecycle validation and revision history
- Deterministic boundary, pairwise, and permutation expansion
- Runner orchestration over existing guarded adapters
- Create-only run manifests and resumable repetition plans
- `case create`, `validate`, `run`, `verify`, and `review` commands
- `experiment validate`, `expand`, and `run` commands

### Safety gate

Experiment definitions cannot contain shell commands, Python callbacks, raw memory access, packet
injection, screen coordinates, or unbounded loops. Live input still requires an approved target,
confirmed calibration, rate limits, emergency stop, and explicit operator invocation.

### Gate

The same validated experiment expands into the same ordered run plan. Recorded and dry-run tests
exercise the full runner without generating desktop input.

## ES-4: Capture alignment and representative cases

### Scope

Seal synchronized evidence from several existing producers and derive a semantic trace.

### Deliverables

- Capture-record and producer-health contracts
- Monotonic clock, UTC provenance, producer sequence, correlation, and marker rules
- Adapters for native snapshots, extension events, semantic decisions, input audits, simulator
  events, process metrics, screenshots, logs, and network summaries
- Required-channel completeness and drop accounting
- Deterministic trace alignment with ambiguity findings
- Existing differential comparator integration
- Statistical result contract for non-deterministic mechanics

### Case A: Runtime health

- No live input
- Exact runtime deployment and manager binding
- Worker, extension, event-channel, process, and latency evidence
- Demonstrates fingerprinting, storage, repetitions, health counters, and verification

### Case B: Vendor-dialog observation

- Exact character, target, zone, and build fixture
- Native vendor event stream and bounded network summary
- Screenshot only when needed as an independent visual cross-check
- Demonstrates cross-channel alignment and protocol claim linkage

### Case C: Combat breakpoint

- One mechanic with two explicit competing values or orderings
- Below/equal/above boundary sweep
- Live pre/action/post snapshots and simulator replay
- Demonstrates hypothesis discrimination, normalized traces, differential results, and gap updates

### Gate

Each case can be exported, verified, reviewed, and queried from a clean checkout plus its artifact
bundle. A reviewer can trace the conclusion to exact raw bytes and reproduce the normalized result.

## ES-5: Coverage, next evidence, and impact

### Scope

Turn repository knowledge and build drift into actionable reports.

### Deliverables

- Generated graph over behavior corpus, claims, sources, builds, layouts, cases, experiments,
  artifacts, simulator bindings, tests, differential gaps, and runtime gates
- Repository scanners with explicit naming/reference conventions
- `coverage validate`, `report`, and `next` commands
- Evidence lifecycle computation and stale-build detection
- Decomposed next-evidence ranking
- `impact report` for client tree, PE, resource, extension, ruleset, policy, and environment changes
- CI job validating graph integrity and uploading human/JSON reports

### Gate

CI rejects broken references, compiled fields without claims, live-verified claims without sealed
evidence, and evidence reused across invalidating fingerprints. A build diff names the exact readers,
claims, cases, bindings, and suites requiring review.

## ES-6: Deeper forensic producers

These capabilities begin only after they can emit ordinary evidence artifacts and impact edges.

### Binary semantic alignment

- Normalized x86 instruction fingerprints
- Function boundary and control-flow graph candidates
- Call-graph neighborhood matching
- String, import, RTTI, vtable, and field-access cross-references
- Confidence-scored anchor and structure relocation evidence
- Manual review and immutable layout-manifest promotion

### Asset and cache graph

- Bounded file-type and magic classifier
- Parser registry with source format and version identity
- Resource dependency and referential-integrity graph
- Structured row, object, terrain, mesh, texture, and configuration diffs
- Unknown-format, orphan, and parser-coverage reports

### Protocol workbench

- Authorized packet-capture ingestion and redaction
- Flow reassembly and message-boundary candidates
- Controlled field-change correlation
- Versioned candidate message schemas
- Packet-summary to semantic-action alignment
- No packet injection or credential/session material

### Read-only runtime discovery

- Candidate pointer-path stability across restarts and ASLR
- Cross-character invariant and difference scoring
- Bounded passive probes and plausibility checks
- Profile-draft evidence that cannot self-promote

### Gate

Every candidate result carries its source artifacts, algorithm version, confidence components, and
review requirement. Similarity never grants runtime compatibility or write authority.

## ES-7: Operational reporting and retention

### Scope

Make the evidence spine usable during ordinary development and patch response.

### Deliverables

- Read-only manager dashboard views for cases, captures, coverage, drift, and blocked work
- Patch-response workflow: fingerprint, diff, impact, targeted rerun, reviewed promotion
- Retention and export policies by artifact kind and redaction state
- Storage-health, missing-object, corruption, and orphan-staging reports
- Reproducible environment records and fixture preparation runbooks
- Periodic offline verification without automatic baseline widening

### Gate

An official client update can be triaged without manually searching reports: the impact report
identifies invalidated knowledge, targeted cases rerun, reviewed compatibility is recorded, and the
coverage graph returns to a trusted state.

## Cross-cutting test matrix

| Concern | Unit | Contract | Integration | Live/manual |
| --- | --- | --- | --- | --- |
| Canonical identity | Yes | Yes | Yes | No |
| Storage and corruption | Yes | Yes | Yes | No |
| Fingerprint stability | Yes | Yes | Yes | Target environment |
| Experiment expansion | Yes | Yes | Yes | Reviewed execution |
| Input safety | Yes | Yes | Recorded backend | Emergency-stop check |
| Capture alignment | Yes | Yes | Synthetic producers | Representative cases |
| Coverage integrity | Yes | Yes | Repository scan | Review findings |
| Build impact | Yes | Yes | Synthetic and frozen builds | Official update |
| Redaction/export | Yes | Yes | Bundle round trip | Operator review |

## Commit cadence

Each ES slice should use coherent checkpoints:

1. schema, typed model, and codec;
2. storage or execution service;
3. adapters and migration;
4. CLI and operator documentation;
5. integration fixtures and CI gate.

Before each commit, run the relevant focused tests, full unit suite when shared contracts changed,
Ruff checks, formatting checks, staged diff review, and documentation-link validation. Push every
validated checkpoint unless credentials or policy prevent it.

## Work intentionally deferred

- Learned hypothesis generation or autonomous live experimentation
- Memory modification, packet injection, or server-side administrative mutation
- A required remote database or hosted evidence provider
- Automatic compatibility promotion from similarity
- Automatic deletion of raw evidence
- Broad dashboard work before the three representative cases pass end to end
- Expansion to every mechanic before the evidence lifecycle is proven
