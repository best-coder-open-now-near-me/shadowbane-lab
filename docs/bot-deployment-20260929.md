# Bot deployment and live qualification - September 29, 2026

## Current boundary

The user is ready to start the game and choose a test character/target after login.
No attack is authorized against an unspecified target. Automatic retaliation stays
disabled until the authoritative server character-session contract is supplied.

Fresh read-only VM inspection found no game running and a healthy, idle, unbound
manager. Installed Vendor Test is still host 0.3.52 / native 1.8.32 from
`e9bf9334043e989cf7438f634de2b488f6ac5569`; official/prepared client 1.3.38.12
hashes match the September 26 review. The new host 0.3.53 / native 1.8.33 source
is based on merged main `d3389d4`. Source merge alone did not deploy it.

The earlier general wheel smoke test did not embed the runtime source stamp
required by the installed launcher. Deployment uses the existing exact-source
acceptance packager, which injects and checks build_identity.json, validates the
installed wheel, and emits qualified native artifacts and a receipt. It does not
reuse the unstamped smoke-test wheel as a deployable runtime.

The first acceptance run at `127bf944` exposed a reproducible Windows localhost
HTTP abort on an unauthorized dashboard POST. The correction is published at
`dbc99bf`: complete the response before a bounded, non-dispatching socket drain.
Independent review, 22 focused tests with 39 subtests, the full 3,797-test suite
(33 skips and 766 subtests), and Ruff passed. Exact-source package qualification
is the remaining active gate before runtime replacement.
The failed package receipt remains private under artifacts/b33/a20edfa9; no
runtime files were changed by that failed attempt and no gate is skipped.

## Update contract

Replace only the full native DLL and install the exact source-stamped host.
Client executable and official assets remain unchanged. Update the package's one
DLL inventory entry, launcher source/hash pins, manager host path, preparation
metadata, and existing shortcuts. Verify game closure and exact idle-manager
identity before replacement. Preserve settings, jobs, journals, and tokens in
place; retain compact hashes and validation receipts, never rollback runtimes or
copies. A failed update stays blocked and is repaired from committed source.

The reviewed updater also removes the dormant obsolete settings-copy/archive
branch from the existing launcher. A missing settings import receipt must stop
startup for inspection; it must not restore from a retired deployment.

Local helpers and compact inspection evidence are under artifacts/bot-deploy/20260929.
Only the coordinator controls VM actions; helper audits and package builds run
independently. Current update capacity excludes any rollback allowance.

## Active todos

1. COMPLETE: merge the bot lanes, verify all 15 hosted gates, and inspect the installed VM baseline.
2. ACTIVE: qualify the exact source-stamped deployment package; the dashboard correction and its full local validation are complete.
3. PENDING: apply the pinned update, verify preserved data and startup, then open Vendor Test for login.
4. PENDING: obtain the test character/target and run bounded manual-list attack/cancel/recovery acceptance.
5. PENDING: obtain server source or the session-fencing contract before implementing automatic retaliation.

No deployment or live-combat success is claimed by this preparation record.
