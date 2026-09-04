# Evidence spine architecture

ADR 0004 establishes this architecture. The staged implementation and migration sequence is in
[the evidence-spine delivery plan](evidence-spine-delivery-plan.md).

## Purpose

The evidence spine is the research and forensics control plane for Shadowbane Lab. It turns existing
client, simulation, runtime, source, and asset tools into one repeatable knowledge-production
workflow:

```text
question
  -> hypotheses
  -> exact fingerprints
  -> experiment definition
  -> controlled runs
  -> synchronized raw evidence
  -> normalized semantic traces
  -> differential results
  -> reviewed claims
  -> implementation and regression coverage
```

It answers four operational questions:

1. What exact Shadowbane, WonderBane, lab, and environment state produced this result?
2. Which immutable evidence supports or contradicts the conclusion?
3. Which readers, claims, simulator fields, policies, and tests depend on that result?
4. What is the smallest next experiment that can close the most important remaining gap?

The spine is not a new authority for game behavior. Controlled runtime observations remain
authoritative for the exact observed service and fingerprint. Source snapshots explain named
implementations. The simulator remains authoritative only for its declared model.

## System placement

The existing semantic runtime stays unchanged:

```text
Observation -> Affordances -> Decision -> Events
```

The evidence spine wraps producers and consumers around that runtime:

```text
sources / client trees / processes / fixtures
                     |
                     v
             fingerprint envelope
                     |
experiment --------> case runner
definition            |
                     v
      native / input / screen / log / network / process / simulator producers
                     |
                     v
          synchronized capture records
                     |
                     v
       content-addressed evidence store
                     |
                     v
       normalization and trace alignment
                     |
                     v
         differential and statistical results
                     |
                     v
       claims / coverage / impact / next work
```

Acquisition producers never update claims directly. Normalizers never mutate raw artifacts.
Coverage reports never grant compatibility. Every promotion remains an explicit reviewed action.

## Durable records

### Contract inventory

The delivery program introduces the following public JSON contracts. Each contract receives a
checked-in JSON Schema, typed Python model, strict codec, canonical digest tests, bounded decoder,
and compatibility policy before its first producer is merged.

| Contract | Canonical owner | Role |
| --- | --- | --- |
| `artifact-descriptor-v1` | `shadowbane_lab.evidence` | Exact immutable byte identity and derivation |
| `evidence-manifest-v1` | `shadowbane_lab.evidence` | Sealed artifact set for one run or import |
| `verification-receipt-v1` | `shadowbane_lab.evidence` | Independent read-only integrity result |
| `migration-receipt-v1` | `shadowbane_lab.evidence` | Traceable import of a legacy artifact family |
| `fingerprint-envelope-v1` | `shadowbane_lab.fingerprints` | Complete stable execution identity |
| `research-case-v1` | `shadowbane_lab.cases` | Question, hypotheses, evidence, and review lifecycle |
| `experiment-definition-v1` | `shadowbane_lab.cases` | Bounded reproducible procedure and oracle |
| `capture-record-v1` | `shadowbane_lab.cases` | Synchronized producer record or artifact reference |
| `statistical-result-v1` | `shadowbane_lab.differential` | Repetition design and stochastic comparison |
| `coverage-report-v1` | `shadowbane_lab.knowledge` | Generated integrity and evidence-lifecycle findings |
| `impact-report-v1` | `shadowbane_lab.knowledge` | Fingerprint-change dependency traversal |

Schema versions are independent. An additive change to one contract does not force unrelated
contracts to increment. Manifests record the exact schema ID and version of every embedded or
referenced structured artifact.

### Artifact descriptor

An artifact descriptor identifies one immutable byte sequence. Required fields are:

- `artifact_id`: `sha256:<lowercase digest>`;
- `sha256` and `size_bytes`;
- `media_type` and a closed `artifact_kind`;
- `created_by` producer identity and version;
- `captured_at_utc` when the bytes came from a live environment;
- `redaction`: policy ID, state, and source artifact when derived;
- `parents`: input artifact IDs for derived evidence; and
- `logical_name`: a non-authoritative review label.

Initial artifact kinds are:

- `client_tree_manifest`, `pe_inspection`, `build_diff`, `runtime_snapshot`;
- `character_snapshot`, `service_snapshot`, `environment_snapshot`;
- `native_event_stream`, `semantic_trace`, `input_audit`, `client_log`;
- `screenshot`, `video`, `packet_capture`, `packet_summary`;
- `process_metrics`, `simulation_result`, `differential_report`;
- `source_snapshot`, `asset_extract`, `coverage_report`, and `impact_report`.

Unknown kinds are rejected in schema version 1. Adding a kind is an additive schema revision only
when existing consumers can safely treat it as an opaque artifact.

### Evidence manifest

An evidence manifest seals a coherent set of artifacts. It records:

- schema version and manifest ID;
- artifact descriptors in canonical path-independent order;
- the fingerprint, case, experiment, and run IDs;
- capture-channel completeness and declared omissions;
- producer warnings and terminal state;
- a canonical manifest digest; and
- a verification receipt reference when independently checked.

The manifest never embeds large artifacts. It may embed small finite JSON payloads only below a
strict byte limit and only when doing so produces the same artifact digest as standalone storage.

### Verification receipt

A receipt records a later read-only verification of one manifest:

- verifier version and Git revision;
- verification time;
- artifact-store identity;
- every checked digest and size;
- schema and reference validation results;
- missing, extra, corrupt, or policy-rejected artifacts; and
- an overall `pass` or `fail` state.

A receipt does not modify or supersede the sealed manifest.

## Identifier model

Identifiers are semantic where humans curate stable identity and content-derived where exact bytes
or canonical payloads define identity.

| Identifier | Derivation | Purpose |
| --- | --- | --- |
| `artifact_id` | SHA-256 of exact bytes | Immutable blob identity |
| `manifest_id` | SHA-256 of canonical manifest content excluding the ID | Sealed evidence set |
| `fingerprint_id` | SHA-256 of canonical fingerprint payload | Complete execution identity |
| `fixture_id` | Human ID plus immutable revision | Reusable character/environment setup |
| `case_id` | Curated stable ID | One atomic research question |
| `experiment_id` | Curated ID plus revision | Reusable discriminating procedure |
| `run_id` | Case, experiment revision, fingerprint, and unique run nonce | One execution attempt |
| `trace_id` | SHA-256 of normalized semantic trace | Producer-independent behavior trace |
| `claim_id` | Existing curated corpus ID | Atomic behavior statement |

Paths, timestamps, process IDs, window handles, and memory base addresses never define durable
identity.

## Complete fingerprint envelope

Every controlled run requires all applicable fingerprint sections. A section may be explicitly
`not_applicable`; it may not disappear silently.

### Client installation fingerprint

- Frozen tree manifest and tree digest
- Main executable PE inspection and complete file digest
- Patcher, launcher, and auxiliary executable digests
- Cache, data, configuration, and resource inventories
- Extension package, patch manifest, ABI, and capability versions
- Build source: official patcher, reviewed baseline, or named package

This section composes the existing client baseline, patch diff, package verification, and PE
alignment capabilities. It does not reimplement them.

### Runtime fingerprint

- Executable path relative to the frozen installation
- Process architecture and start provenance
- Loaded module names, sizes, and file digests
- Native-layout profile and reviewed compatibility-family evidence
- Extension runtime status, ABI, event-channel layout, and capabilities
- Manager and worker package revisions
- Window client bounds, render resolution, DPI, and display topology
- Relevant renderer, GPU, and driver identity

Volatile process IDs, module bases, handles, and timestamps may be recorded as observations but are
excluded from the stable fingerprint digest.

### Service fingerprint

- Named behavior profile and service label
- Server endpoint identity with credentials and session tokens removed
- Observable protocol, handshake, patch, shard, world, and zone information
- Server-provided time or tick marker when exposed
- Acquisition method and confidence

Network evidence is limited to environments and accounts the operator is authorized to observe.
Raw packet capture is never required when a safe semantic or summary capture answers the question.

### Environment fingerprint

- Environment ID and immutable VM image or machine configuration revision
- Operating system build and architecture
- Python package/version lock, native extension build, and lab Git revision
- Locale, time zone, clock source, display configuration, and input backend
- Capture-tool versions and relevant security policy IDs

Secrets and machine-unique identifiers that do not affect behavior are redacted or replaced with
stable local aliases.

### Character fixture fingerprint

- Character fixture ID and revision
- Race, base class, profession, disciplines, sex, and level
- Attributes, derived statistics, skills, powers, and training ranks
- Equipment, inventory, active effects, stance, resources, and life identity
- Position, zone, group, selected target, and controlled nearby entities
- Source artifact IDs for native, visual, log, or manual declarations
- Completeness and coherence findings

A fixture can be reused only when its live precondition snapshot matches its declared revision.

### Lab execution fingerprint

- Ruleset, behavior profile, formula, source, and simulator revisions
- Policy ID and revision
- Scenario and experiment revisions
- Input calibration and action-map revisions
- Random seeds, repetition index, and deterministic runtime settings
- Declared compatibility or override acceptances

Mechanics and policy revisions remain separate dimensions so their effects can be evaluated
independently.

## Research case contract

A case contains one question that can reach a reviewable conclusion. Broad subjects such as
"combat" or "movement" are coverage domains, not cases.

Required case fields are:

- `case_id`, title, owner, created date, and current revision;
- target behavior profile and affected coverage domains;
- one atomic question;
- two or more mutually distinguishable hypotheses, including an `unknown_other` escape when the
  candidate set is not exhaustive;
- referenced claims, contradiction groups, simulator bindings, and gap-ledger entries;
- required fingerprint sections and capture channels;
- experiment revisions and run manifests;
- review state, conclusion, limitations, and invalidation conditions; and
- follow-up case IDs.

Case states are:

```text
draft
  -> ready
  -> collecting
  -> evidence_complete
  -> reviewed
  -> closed
```

`blocked` is an orthogonal reason with a concrete missing authority, fixture, source, capability,
or external state. A blocked case retains its lifecycle state and does not masquerade as a
conclusion.

Reopening a closed case creates a new case revision and records the invalidating fingerprint or
evidence. Historical conclusions remain intact.

## Experiment definition

An experiment is a reusable, versioned procedure designed to distinguish named hypotheses. It is
data, not arbitrary executable code.

Required sections are:

1. **Intent**: question type, hypotheses, and discriminating observations.
2. **Preconditions**: exact fixture, location, resources, effects, target, and safety state.
3. **Variables**: independent variables, control values, boundary points, and allowed combinations.
4. **Procedure**: bounded semantic setup, action, observation, settling, and cleanup steps.
5. **Capture**: required and optional channels plus pre/action/post timing windows.
6. **Repetition**: seeds, ordering, repetitions, randomization, and statistical stopping policy.
7. **Oracle**: exact invariants, tolerance policies, distribution tests, and terminal conditions.
8. **Safety**: maximum duration, input count/rate, resource loss, stop conditions, and recovery.
9. **Outputs**: required normalized trace, metrics, counters, and result classification.

Procedure steps use a bounded algebra:

- `assert_precondition`
- `capture_marker`
- `semantic_decision`
- `wait_for_observation`
- `wait_virtual_or_wall_duration`
- `repeat`
- `branch_on_observation`
- `record_annotation`
- `stop`

The first implementation should not include arbitrary shell, Python, packet, memory-write, or
client-coordinate steps. Existing guarded adapters remain responsible for execution.

### Experiment generation

Generators create reviewed experiment candidates for repetitive families:

- below/equal/above boundary sweeps;
- pairwise effect and rank collision matrices;
- initial-versus-later periodic ticks;
- cast/launch/deferred-resolution interruption permutations;
- fixed-sheet stochastic distributions;
- range, line-of-sight, and vertical-tier boundaries; and
- metamorphic cases such as equipment swap, target death, or orientation reversal.

Generated definitions are validated and reviewed before live execution. A generator cannot expand
input authority or capture scope.

## Capture bus and clock model

The capture bus is a logical contract over existing producers, not necessarily one long-running
broker process. Every record contains:

- `run_id`, `channel_id`, producer ID, and producer version;
- producer-local monotonic timestamp in nanoseconds;
- UTC timestamp for cross-machine provenance;
- strictly increasing producer sequence;
- correlation ID when associated with a semantic decision;
- record kind and finite payload or artifact reference; and
- quality flags such as dropped, partial, delayed, or reconstructed.

The case runner emits synchronization markers before setup, immediately before and after each
controlled decision, at expected resolution boundaries, and at terminal capture. Producers that
cannot ingest markers are aligned using nearest observable markers and record that lower-quality
method.

Required initial channels are:

- fingerprint and precondition snapshots;
- semantic decisions and guarded input audits;
- native state and extension event streams;
- simulator observations and events when differential execution is requested;
- terminal state and producer-health counters.

Screen, video, client-log, packet-summary, packet-capture, and process-metric channels are optional
per experiment. Missing required channels make a run incomplete rather than silently reducing
confidence.

## Evidence ingestion and storage

The default local layout is:

```text
evidence/
  cases/                 # reviewed case manifests suitable for Git
  experiments/           # reviewed definitions suitable for Git
  manifests/             # sealed evidence manifests suitable for Git when small
  objects/sha256/aa/...  # large immutable local objects, ignored by Git
  receipts/              # verification and migration receipts
  indexes/               # disposable SQLite and generated reports
```

Deployments may map object storage to a separate volume or authorized remote provider. Manifests
refer only to artifact IDs, never provider-specific URLs. A local resolver maps artifact IDs to
configured stores.

Ingestion is a two-phase operation:

1. Stage files, validate bounds and type, hash bytes, scan redaction policy, and construct a
   candidate manifest.
2. Atomically place new objects, reread and verify them, then create the sealed manifest with
   create-only semantics.

Failure before sealing leaves no trusted manifest. Garbage collection may remove unreferenced
staging objects after a configured quarantine period, but never removes a sealed referenced
object.

## Normalization and differential analysis

Raw evidence preserves producer-specific detail. Derived normalization produces the smallest
semantic representation needed to test the case hypotheses.

The normalizer:

- retains raw artifact parent IDs and producer versions;
- removes volatile IDs only under reviewed mapping rules;
- aligns records by markers, correlation, monotonic time, and producer sequence;
- reports ambiguous or unmatched records;
- emits the existing observation/affordance/decision/event protocol where applicable; and
- creates a deterministic `trace_id` from canonical semantic content.

Differential comparison continues to treat every difference as unexpected. The existing gap
ledger may describe known work, but only narrowly reviewed accepted approximations can pass a
difference. Statistical comparisons record sample design, estimator, confidence interval, test,
effect size, and stopping rule; a bare p-value is not a conclusion.

## Coverage graph

Coverage is generated from repository contracts rather than maintained as a second prose status
list. Nodes include:

- behavior profiles, sources, claims, and contradiction groups;
- client builds, layout profiles, fingerprints, and artifacts;
- experiments, runs, traces, and conclusions;
- simulator fields, action keys, formulas, adapters, and policies;
- unit, fixture, differential, runtime, and regression tests; and
- gap-ledger and invalidation entries.

Edges are typed, for example:

- `supports`, `contradicts`, `qualifies`, `derived_from`;
- `observed_on`, `compatible_with`, `invalidated_by`;
- `tests`, `implements`, `normalizes_to`, `compares_with`;
- `blocks`, `resolves`, and `supersedes`.

The generated report fails when it finds:

- a compiled simulator field without a claim;
- a claim with an implementation binding but no relevant test;
- a live-verified claim with no sealed run and complete fingerprint;
- a native profile with no compatibility evidence or validation fixture;
- a referenced artifact, case, experiment, claim, or gap that does not exist;
- a closed contradiction group whose claims remain compile-blocked without explanation; or
- evidence reused after an invalidating fingerprint change.

### Knowledge lifecycle

Generated lifecycle states are:

```text
unknown
  -> sourced
  -> observed
  -> reproduced
  -> differential_pass
  -> regression_covered
```

These are evidence states, not confidence percentages. Contradictory evidence, incomplete capture,
and incompatible builds remain separately visible.

### Next-evidence queue

The planner ranks unresolved work using declared data rather than intuition:

- priority of the affected coverage domain;
- number and importance of downstream claims or bindings blocked;
- existence and cost of a discriminating fixture;
- evidence freshness and build applicability;
- safety and authorization requirements; and
- opportunity to resolve several hypotheses with one bounded experiment.

The score is advisory and fully decomposed in the report. It never schedules live input without
operator authorization.

## Change-impact analysis

Impact analysis starts with an immutable diff and traverses reviewed dependencies.

For executable changes:

```text
changed bytes or PE structure
  -> normalized function or anchor candidates
  -> layout profiles and native readers
  -> observation fields
  -> claims, experiments, and runtime suites
```

For data or asset changes:

```text
changed resource
  -> parsed rows and dependencies
  -> powers, items, zones, terrain, or formulas
  -> claims and simulator bindings
  -> scenarios and regression suites
```

Impact states are `unaffected`, `review_required`, `invalidated`, and `unknown`. Only exact identity
or reviewed compatibility evidence can produce `unaffected`. Similarity scores propose review
candidates and never grant compatibility.

## Command surface

The target installed interface is:

```text
shadowbane-lab fingerprint capture
shadowbane-lab fingerprint verify
shadowbane-lab fingerprint diff

shadowbane-lab case create
shadowbane-lab case validate
shadowbane-lab case run
shadowbane-lab case verify
shadowbane-lab case review

shadowbane-lab experiment validate
shadowbane-lab experiment expand
shadowbane-lab experiment run

shadowbane-lab evidence ingest
shadowbane-lab evidence verify
shadowbane-lab evidence bundle
shadowbane-lab evidence query
shadowbane-lab evidence rebuild-index

shadowbane-lab coverage validate
shadowbane-lab coverage report
shadowbane-lab coverage next

shadowbane-lab impact report
```

Commands use create-only output by default, deterministic JSON with `--json`, human review output
without it, and exit codes `0` for success, `1` for a valid negative/gate result, and `2` for
untrusted input or infrastructure failure.

The implementation lives in focused packages:

```text
shadowbane_lab/evidence/
  artifacts.py       manifests.py       storage.py
  verification.py    index.py           codec.py

shadowbane_lab/fingerprints/
  model.py           capture.py         compare.py
  client.py          runtime.py         environment.py
  service.py         fixture.py         execution.py

shadowbane_lab/cases/
  model.py           experiment.py      runner.py
  capture.py         review.py          codec.py

shadowbane_lab/knowledge/
  graph.py           coverage.py        impact.py
  planner.py         repository_scan.py

shadowbane_lab/commands/
  fingerprint.py     case.py             experiment.py
  evidence.py        coverage.py         impact.py
```

Common strict JSON, path, identifier, digest, tree-inventory, and atomic create-only helpers move
into a shared internal package before these modules are added. Domain packages consume those
helpers rather than depending on evidence orchestration.

## Security, privacy, and authorization

- Collection scope is declared by the experiment and fingerprint contract.
- Read-only observation remains the default; memory writes are outside the evidence spine.
- Live input authority comes only from existing guarded adapters and explicit profiles.
- Packet collection is optional, bounded, authorized, and redacted before sharing.
- Bearer tokens, credentials, chat, account names, machine identifiers, and unrelated window
  content are rejected or redacted under named policies.
- Original and redacted artifacts have separate IDs and explicit derivation edges.
- Artifact bundles declare their export policy and fail if required redaction is incomplete.
- Object-store resolvers prevent path traversal, reparse-point escape, and overwrite.
- Commands bound file counts, individual sizes, total bytes, nesting, JSON depth, and execution
  duration.

## Compatibility and invalidation

Every claim, experiment result, and native layout declares which fingerprint dimensions affect it.
An invalidation rule can match:

- exact file, tree, section, resource, or extension changes;
- layout-family or ABI changes;
- service profile or observable protocol changes;
- fixture changes affecting the mechanic;
- environment dimensions such as DPI or renderer when visual evidence is involved; and
- simulator, ruleset, formula, or policy revisions.

Unknown changes are `review_required` or `invalidated`, never implicitly compatible. A reviewed
compatibility decision records its evidence, reviewer, scope, and replacement tests.

## Validation strategy

### Contract tests

- Strict schema validation and duplicate-key rejection
- Canonical JSON round trips and stable digests
- Unknown, missing, excessive, and non-finite field rejection
- Cross-reference integrity and cycle rules
- Path, reparse-point, count, and byte-bound enforcement

### Storage tests

- Create-only placement and deduplication
- Interrupted staging and recovery
- Reread verification and corruption detection
- Missing object, wrong size, and wrong digest handling
- Redaction derivation and bundle policy
- Index deletion and deterministic rebuild

### Fingerprint tests

- Stable identity across volatile process changes
- Sensitivity to every declared durable dimension
- Explicit `not_applicable` sections
- Existing baseline, PE, package, runtime, and character evidence adapters
- Compatibility-family review without automatic promotion

### Case-runner tests

- Deterministic step expansion and bounded execution
- Required-channel completeness
- Clock markers, sequence gaps, drops, and partial producers
- Cancellation, failure, recovery, and create-only evidence
- No desktop input from automated tests

### Knowledge tests

- Corpus, ruleset, tests, layouts, experiments, and manifests scan into one graph
- Orphan and stale reference detection
- Build-diff impact traversal
- Stable decomposed next-evidence ranking
- Historical conclusions preserved after invalidation

### End-to-end fixtures

The first three sealed case families are:

1. Manager/worker/extension runtime health with no client input.
2. Vendor-dialog protocol observation with native and network-summary evidence.
3. One controlled combat breakpoint with live and simulator traces.

They exercise infrastructure, event alignment, source/claim linkage, differential comparison, and
coverage promotion without prematurely generalizing every game system.

## Definition of done for a mechanic

A mechanic is complete for one named behavior profile only when:

- its sources and atomic claims are revision-pinned;
- its live evidence is sealed under a complete applicable fingerprint;
- the experiment distinguishes relevant competing hypotheses;
- the normalized trace is reproducible or has a declared stochastic result;
- its simulator binding and engine test cite the claims;
- its differential result passes or retains a scoped open gap;
- its invalidation dimensions and replacement test are declared; and
- the generated coverage graph reaches `regression_covered` without integrity findings.

Anything less remains useful evidence, but it is reported at its actual lifecycle state.
