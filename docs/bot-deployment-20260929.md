# Bot deployment and live qualification - September 29, 2026

## Current state

Vendor Test is running client 1.3.38.12 with host 0.3.53 and native 1.8.33.
The deployed source is `b5016c491d2b51e0f0ed99b62acaedf134c54c9a`.
[PR #44](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/44)
merged it into main as `5945a00fd160097c5f43e49bbf3386337beabc4f` after all
15 hosted checks passed and the user approved the merge. The normal checkout
was fast-forwarded cleanly to main. PR #43 previously integrated all bot lanes.

The game was opened for user login. Its captured process lifetime and loaded
DLL hash match the deployment. A passive inspection observed no local character,
no consistent movement scene, and no manual-list readiness yet. The manager is
healthy and unbound. Login and character/target selection remain user input;
no combat commands were sent. Automatic retaliation remains disabled until the
authoritative server character-session contract is supplied.

## Qualified package

The exact-source acceptance packager produced local artifact `artifacts/b33/8b432cb3`.
Its receipt reports acceptance_eligible=true, no failed required gates, all three
private binding checks true, and 36 validation steps. All 60 receipt file hashes
and the wheel's embedded build_identity.json were independently checked.

- Python: 3,797 passed, 33 skipped, 766 subtests; Ruff passed.
- Both native profiles: 186 required CTests passed and three image-dependent
  CTests skipped in the public suite, then those private image checks passed
  explicitly against the reviewed original/prepared executable.
- Real host/native IPC: 63 tests and 15 subtests passed per profile.
- Installed wheel: source identity, entrypoints, panels and contracts passed.
- Two known optional transparency diagnostics per profile remain recorded
  separately; this deployment does not claim they were fixed.

| Artifact | SHA256 |
| --- | --- |
| Acceptance archive | `70ffd5529fc412b4064135d36bb9b6dc56ccc174ff97251acf73191c7ebc2dec` |
| Host wheel | `21be0126087e76f539aa4094de0f7e4f979ebdf3aac28afbefa9594a5b26294a` |
| Full native DLL | `9450160c8fefec50522dc9bcb9a1fd4093246853e79c5b43c132556fd619a48e` |
| Unchanged prepared client | `2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289` |
| Unchanged official client | `3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7` |

The first package attempt (`artifacts/b33/a20edfa9`) exposed Windows losing an
unauthorized dashboard POST response while closing with unread bytes. PR #44
fixes response completion with a bounded socket drain. That failed attempt is
retained as diagnostic evidence, and no validation gate was skipped. The earlier
unstamped smoke-test wheel was never used for deployment.

## Applied update and preservation

Only one client inventory record changed: the native DLL. The official assets
and client executable remained unchanged. The updater installed the source-stamped
host in an isolated environment, updated exact launcher pins and preparation
metadata, and verified all five existing shortcuts plus the non-launching
preflight. The healthy idle manager was stopped using its captured process
identity before replacement, then restarted with the new host.

Nine exact, hash-pinned client dependency wheels were installed offline for
CPython 3.12 / Windows AMD64, including PyAutoGUI 0.9.54 and Pillow 12.3.0.
Dependency resolution, pip check, exact versions/import locations and input
backend construction passed without sending input.

The update verified 444 installed host files and 9,560 preserved files. Settings,
jobs, journals, tokens, normal-client files and diagnostic evidence stayed in
place. Manager startup revoked only the expected unbound dispatch permit.
The dormant settings-copy/archive branch was removed from the launcher; a
missing settings import receipt now stops startup for inspection.

No rollback copies or fallback runtime archives were created. The obsolete
host 0.3.52 was verified against its installed-file records and venv scaffolding:
892 files, no unknown files or directories, no active process/configuration/shortcut
dependencies. It and three exact obsolete September 26 payload binaries were
removed, freeing 42,463,971 bytes. Compact hash receipts remain. Diagnostic job
records under the older recovery-validation directory remain in place. Recover
source/builds from committed Git and original third-party assets from their
official source.

Private deployment helpers, dependency pins and compact receipts are under
`artifacts/bot-deploy/20260929`. Guest update receipts are under
`C:/ShadowbaneLab-Guided/vendor-1.8.3-bd08ffc/upgrades/bot-update-20260929-1.8.33`.
Private captures, credentials, runtime binaries and dependency wheels are not
published to Git. Active validation worktrees remain available for live testing.

## Active todos

1. COMPLETE: integrate bot source and dashboard fix after all hosted checks pass.
2. COMPLETE: qualify and deploy the exact source-stamped package and client dependencies.
3. COMPLETE: verify preserved files, shortcuts, manager startup and loaded game DLL.
4. COMPLETE: verify and retire obsolete runtime files while preserving diagnostic records.
5. ACTIVE: obtain login/character/target input for bounded manual-list attack/cancel/recovery acceptance.
6. PENDING: obtain server source or the session-fencing contract before implementing automatic retaliation.

No live-combat acceptance success is claimed by this deployment receipt.
