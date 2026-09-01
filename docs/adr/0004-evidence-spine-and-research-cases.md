# ADR 0004: Use an immutable evidence spine and research cases

- **Status:** Accepted
- **Date:** 2026-08-31

## Context

Shadowbane Lab can freeze and compare client trees, inspect PE files, read typed client state,
record semantic traces, run deterministic simulations, maintain behavior claims, and gate produced
runtimes. Those capabilities currently produce several independent artifact families. Operators
must manually carry build identity, character state, experiment intent, capture paths, claim IDs,
and simulator revisions between them.

That manual assembly makes a result difficult to reproduce and makes client updates difficult to
assess. A file or executable change can invalidate a native profile, observation, behavior claim,
or simulator input without one system showing the complete impact. Free-floating screenshots and
generated reports can retain useful information while losing the exact conditions under which they
were captured.

The project needs a durable research boundary above its existing probes. That boundary must retain
raw evidence, keep conclusions reviewable, preserve the distinction between observed and simulated
behavior, and avoid turning a local database into an opaque source of truth.

## Decision

Shadowbane Lab will use an **evidence spine** built from immutable, canonical JSON manifests and
content-addressed artifacts. A **research case** is the unit that connects a question to its
evidence and resulting knowledge.

A case binds:

- one atomic research question and explicit competing hypotheses;
- exact client, runtime, service, environment, character, simulator, policy, and scenario
  fingerprints;
- a versioned experiment definition and its controlled runs;
- synchronized raw capture artifacts and normalized semantic traces;
- supporting, contradicting, and qualifying behavior claims;
- simulator bindings, differential results, coverage status, and invalidation conditions; and
- an explicit review state and conclusion.

Small manifests, experiment definitions, claims, and conclusions are suitable for source control.
Large or binary artifacts are stored once under their SHA-256 digest. A generated SQLite index may
accelerate queries, but it is disposable and must be completely rebuildable from canonical
manifests.

The evidence spine introduces versioned contracts for:

1. artifact descriptors and sealed evidence manifests;
2. complete fingerprint envelopes;
3. research cases and experiment definitions;
4. synchronized capture records;
5. coverage and impact reports; and
6. verification receipts.

Existing tools remain the owners of acquisition and domain decoding. The evidence spine
orchestrates them and records their outputs; it does not replace PE inspection, client observation,
runtime consistency, differential comparison, or the behavior corpus.

## Invariants

- Raw evidence is immutable. Corrections create a new manifest or derived artifact.
- Every artifact is verified by digest before use.
- A run cannot omit its complete fingerprint envelope.
- A conclusion cannot promote itself from its own candidate result.
- Wall-clock time is recorded for provenance; monotonic time and producer sequence establish event
  ordering within a run.
- Secrets, credentials, bearer tokens, and unredacted account identifiers are never evidence.
- Profile-specific claims never cross game or server profiles implicitly.
- Generated indexes, summaries, dashboards, and caches are not authoritative records.
- Unknown or changed fingerprints invalidate affected evidence until an explicit compatibility
  review narrows the impact.
- Live input remains subject to the existing client-window, calibration, rate, and emergency-stop
  guards. A case definition cannot grant input authority.

## Command and module boundary

Operator workflows remain under the installed `shadowbane-lab` command. The evidence spine adds
modular `fingerprint`, `case`, `experiment`, `evidence`, `coverage`, and `impact` command groups
after the current monolithic CLI is split. It does not add another console executable.

PowerShell remains limited to Windows process, privilege, VM, shortcut, packet-capture, and
fixed-path policy. A PowerShell wrapper must not become a second research API.

## Consequences

- A mechanic can be traced from source and live observation through implementation and regression
  coverage.
- Client updates can produce a targeted impact report instead of invalidating all knowledge or
  silently reusing stale offsets.
- Experiments can be resumed, compared, and independently verified without relying on file names or
  operator memory.
- Large evidence remains outside normal Git history while its identity, provenance, and conclusions
  stay reviewable.
- Initial implementation work is infrastructure-heavy: common inventory, canonical serialization,
  storage, ingestion, and migration must precede deeper binary or protocol analysis.
- Existing artifact formats need adapters and migration receipts; they are not rewritten in place.

## Alternatives rejected

### Treat the filesystem layout as the database

Paths alone do not establish content identity, parentage, capture conditions, or whether a file was
modified after collection.

### Store all evidence directly in Git or Git LFS

Git remains appropriate for small reviewed records, but capture volume, local authorization, and
binary retention policy vary by environment. The manifest contract must not depend on one storage
provider.

### Make SQLite the authoritative store

A mutable database is difficult to review, merge, verify, and recover. A rebuildable index gives
query performance without hiding the durable record.

### Add more independent capture commands

Additional producer-specific commands increase command and artifact fragmentation. New acquisition
capabilities must plug into the common fingerprint, case, capture, and evidence contracts.
