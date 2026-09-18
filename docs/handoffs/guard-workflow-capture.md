# Continuous guard workflow capture

Branch: codex/guard-upgrades. Review into codex/vendor-rolling, then the documented
integration branch and reviewed main. This diagnostic is host-only and does not
require a game extension reinstall.

Run src/shadowbane_lab/client_observation/workflow_capture.py with the installed
host Python, an exact --process-id and --creation FILETIME, --output JSONL path,
and a distinct absent --stop-file path. Default duration is 30 minutes and sample
interval is 200 ms. Create the stop marker to finish gracefully. Output is exclusive
and flushed after every record. Keep captures private in the local artifact area.

The recorder holds a read-only process handle for one reviewed executable lifetime.
It never connects to an action channel or sends game actions. It continuously joins
ordered HUD and owned management-control observations, nearby building cache,
complete current building roster, guard quotes/progress, warehouse withdrawal quotes
and structure deposit quotes. Closed, inconsistent and unsupported panels become
explicit unavailable records; other channels and later samples continue. Unknown
HUD identities remain visible without interpreting their layouts. Repeated states
are deduplicated; health records retain observation/error counts and sample timing.

This is sequential state sampling, not exhaustive function-call tracing or atomic
cross-channel evidence. Brief transitions between polls can be missed. Leave each
new window visible briefly during the manual walkthrough. Existing strict readers
still determine semantic validity. Raw manager fields can be uninitialized and never
grant transaction authority. Session completion does not prove workflow completeness,
server acceptance, town coverage or maximum rank.

The capture ends on the explicit marker, duration limit, process loss or interruption.
It never rebinds to another process. Unexpected errors leave an error end record;
partial files without an end record must be treated as interrupted evidence.

Validation: recorder tests and existing building/guard/withdrawal/deposit observer
checks passed (139 tests). Tests cover unavailable-to-observed transitions, continued
capture, deduplication, explicit stopping, process loss, identity mismatch, exclusive
files, unknown HUDs and changing controls. Lint passed. Live preflight confirmed
in-world window observations with the currently installed 1.8.15 extension; no
management panels were open, and semantic channels correctly reported unavailable.

Active todo: capture a complete manual sequence through City Command/buildings,
warehouse withdrawal, structure deposit and guard upgrade, including return visits.
Analyze all transitions together before selecting the next native changes. Automatic
funding, full-town coverage, maximum-rank evidence and integration remain unfinished.
