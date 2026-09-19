# Guard travel controls

Source feature on `codex/guard-upgrades`; not installed or live-qualified yet.
Integration destination: `codex/vendor-rolling`, then
`codex/native-lifecycle-hardening`, then reviewed `main`.

Travel and Continue here live in the manager dashboard, with no game overlay.
Travel completes and accounts for the current funding cycle before displaying
Safe to move. Continue here scans fresh building rosters, opens personal menus
only for newly discovered guards, and extends the same durable job. Guards outside
the current scan remain remembered but are not scheduled. New guards have priority;
known guards retain rank floors, timers, upgrade counts, and confirmed gold totals.
An area without remaining offers returns to Travel; it does not claim maximum rank.

Each area retains immutable discovery digests and exact process/scene ownership.
Worker restarts preserve this progress. This does not import progress into a new
game lifetime: original scene pointers and native receipts must not be rebound.
The upgraded manager requires the matching travel-capable worker. Uncertain
requests remain blocked; Travel cannot clear the existing live navigation failure.

Validation: focused scheduler, discovery, dashboard, and worker tests cover safe
transaction boundaries, area merging, new guard priority, retained rank timers,
wrong-scene rejection, and guard-menu skipping from a fresh owned roster.

Next: complete broader regression checks, resolve the existing navigation admission
failure without replay, and prepare the coherent VM update and live acceptance.
The installed client remains 1.8.21 / host 0.3.31; its prior failed request and all
174 confirmed first-pass upgrade records remain untouched.
