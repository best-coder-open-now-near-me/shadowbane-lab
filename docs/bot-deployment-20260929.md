# Bot deployment and live qualification - September 29-30, 2026

## Current state

Vendor Test is installed with client 1.3.38.12, host 0.3.54 and native 1.8.34.
The deployed source is `ab5e043a84808eea776b2e463e7d6e3d2cf63116`.
[PR #45](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/45)
merged that head into main as `79b374da0a446cce913238543ee737cc01ad3e78` after
all 15 hosted checks passed and merge authorization. The normal checkout is
clean on main. PRs #43 and #44 previously integrated the bot lanes and dashboard
response-completion correction.

The September 29 launch receipt identifies the exact loaded DLL listed below,
process 6960, creation FILETIME `134351902080088465`, and window 5112636.
The subsequent read-only readiness sample reported a fresh movement binding,
manual-list capability, readable living local player and party state, and no
readiness rejection reasons. Its executable verification was a disk check;
`loaded_image_hash_verified` was false. The launch receipt separately records
the loaded extension DLL hash. These samples are observations of that captured
process lifetime, not a promise of future readiness.

The fresh bounded live attempt did not pass attack acceptance. The recorded
local character was Umbra on Wonderbane and the selected target was `day`, the
user-confirmed Day Owl target. Automatic retaliation remains disabled until the
authoritative server character-session contract is supplied.

## Latest bounded live result

Evidence run `85193158420e4802af16fffdde28f706` used the installed PR #45 source.
The correlated native request `e590e01d49ad4081b9ef84b49450c16f` recorded:

- Diagnostic detail `combat_v1:query_match:stale:d0n0q0f0:m-1`.
- LOCAL_CANCELLED, flags 4, IDLE, mode/action 1, no combat target, and confirmed
  local cleanup. OUTBOUND_QUEUED was false.
- No observed dispatcher, native factory, queue append or followup entry. The
  movement result was not observed (`m-1`); this is not evidence of movement
  failure or of a successful native attack.
- A strictly later PvE SEEKING step at 1,500 ms, followed by the bounded stop.
  The watcher reported no error and the watchdog did not fire; run exit was 0.
- Removal of only the test-owned entry, leaving the original empty list at
  revision 6. No entered admissions required cancellation. Removal occurred
  after cleanup, so this run does not establish removal-triggered cancellation.

The acceptance result is `not_passed` and `engaged` is false. Target health was
unchanged. The diagnostic narrows the failure to the native query-match stage;
the exact mismatch still needs investigation. It does not establish a range,
weapon-type or target-protection cause. No live attack success or server damage
is claimed.

## Qualified package

The exact-source acceptance packager produced `artifacts/b34/1be8a982` from
`ab5e043a84808eea776b2e463e7d6e3d2cf63116`. Its receipt reports
acceptance_eligible=true, no failed required gates, all three private binding
checks true, 36 validation steps and 60 receipt files. The package's recorded
`live_acceptance` is still pending: package qualification does not certify
subsequent gameplay.

- Python: 3,821 passed, 34 skipped, 771 subtests; Ruff passed.
- Both native profiles: 186 required CTests passed and three image-dependent
  CTests skipped in the public suite. Those three private image checks passed
  explicitly against the reviewed original/prepared executable.
- Real host/native IPC: 63 tests and 15 subtests passed per profile.
- Installed wheel: source identity, entrypoints, panels and contracts passed.
- Two known optional transparency diagnostics per profile remain recorded
  separately; this update does not claim they were fixed.

| Artifact | SHA256 |
| --- | --- |
| Acceptance archive | `a3c05eca4417576b6627da4d82e61b1fc60000373813e06a309df3d64db23581` |
| Host wheel | `56c7566b781a28f41832f6a2914dad5a98cdb3a457bfb0a8d3c9106f29150bbe` |
| Full native DLL | `9604eec25aa1c9b55b980ceb6ea468270b4f24c1ba1c461b6b83fc03cb2b921e` |
| Unchanged prepared client | `2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289` |
| Unchanged official client | `3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7` |

## Applied update and preservation

The baseline was source `b5016c491d2b51e0f0ed99b62acaedf134c54c9a`, host 0.3.53 /
native 1.8.33. Only one client inventory record changed: the native DLL. The
official assets and client executable remained unchanged. A source-stamped host
was installed in a new isolated environment, exact launcher pins and preparation
metadata were updated, and all five existing shortcuts plus the non-launching
preflight were verified. The healthy idle manager was stopped before replacement
and restarted with the new host; the game was launched afterward.

The update verified 444 installed host files and 9,562 preserved files. Settings,
jobs, journals, tokens, normal-client files and diagnostic evidence stayed in
place. Manager startup revoked only the expected unbound dispatch permit.
The existing fail-closed settings-receipt guard was preserved; obsolete settings
copy/archive behavior was not reintroduced.

Nine exact, hash-pinned client dependency wheels were installed offline for
CPython 3.12 / Windows AMD64, including PyAutoGUI 0.9.54 and Pillow 12.3.0.
The installed dependency checks and backend construction were part of validation,
without sending client input.

Preparation resumed only after a successful read-only validation retry, recorded
by `prepare.json` with `resumed_after_readonly_validation=true` and
`validation_log=validation-retry.log`. The original exported `validation.json`
is empty and is not validation evidence. The exported `validation-retry.log`
confirms exact source, 444 installed modules, 9,562 preserved files and one client
inventory change. The later complete update, activation, shortcut, preflight and
launch receipts establish the applied state.

No rollback copies or fallback runtime archives were created. Obsolete host
0.3.53 was checked against its installed-file records and venv scaffolding:
2,078 files, 47,355,948 bytes, and no unknown files or directories. After checking
active process/configuration/shortcut dependencies, it and the two exact obsolete
1.8.33 guest payload binaries were removed, freeing 49,976,794 bytes. Compact
receipts and diagnostic records remain. Recover source/builds from committed Git
and original third-party assets from their official source.

Private helpers are under `artifacts/bot-deploy/20260929-b34`; the qualified
package is under `artifacts/b34/1be8a982`. Guest receipts are under
`C:/ShadowbaneLab-Guided/vendor-1.8.3-bd08ffc/upgrades/bot-update-20260929-1.8.34`.
Their private host export is under
`E:/virtual-machines/shadowbane-testing/diagnostics/bot-update-20260929-1.8.34`,
including `receipts` and `live-acceptance/85193158420e4802af16fffdde28f706`.
Private captures, credentials, runtime binaries and dependency wheels are not
published to Git. Active validation worktrees remain available for the open live
investigation. The bot-runtime worktree now uses
`codex/combat-target-query-20260930`, based on main, for the unfinished query-match
follow-up; that work is not part of the installed package.

## Source changes and earlier evidence

PR #45 preserves correlated host/native diagnostics across cleanup, retirement
and replay without changing Receipt384 or action admission. Host logs accept
opaque `native_detail` only after receipt correlation. The format is
`combat_v1:<stage>:<outcome>:dDnNqQfF:mM`: D is dispatcher entry, N is native
factory entry, Q is observed queue append and F is followup entry. M is the
native movement Result enum, or -1 when not observed. The original receipt
remains authoritative for local queue history and cleanup. Diagnostic text grants
no action authority and proves neither server acceptance nor damage. The legacy
`native_combat_receipt_v1` marker remains valid when no attempt detail exists.

Standalone PvE initializes the input backend, journal and navigation observer
before acquiring its expiring movement grant, then revalidates the exact client
and character. Preparation failures acquire no authority. Listed cleanup precedes
owner release, with observer/journal closure afterward; injected dispatchers
remain caller-owned. Focused CLI/lifecycle validation passed 48 tests and five
subtests with one expected native-fixture skip. This corrects startup ordering;
it does not prove cold-import starvation caused an earlier live ownership loss.

The previous 0.3.53 / 1.8.33 attempts remain historical evidence. Attempt
`b988013b56bb4bcaaaf9446f03e4010f` acquired generation 3, then received STALE on
pause at generation 4 about 4.1 seconds later, with no combat START receipt.
Attempt `01dc7d5480a545b497510307142b3965` acquired and paused generation 7;
START returned LOCAL_CANCELLED with no queued attack, confirmed cleanup and a
later SEEKING step. The original empty list ended at revision 4. Neither attempt
established attack acceptance or removal-triggered cancellation.

The user separately reported successful manual ranged hits. Correlated targeted
action records support that manual test but are not calibrated as authoritative
damage or retaliation events. Read-only samples passed reviewed mask, state and
peace-protection predicates. The prepared client 1.3.38.12 differs from reviewed
1.3.38.11 only in its version byte; all 13 inspected native dispatcher/mask/state/
peace/mode/factory ranges matched. The handler has no pre-factory distance or
equipped-weapon branch, and the request class name alone does not prove melee-only
behavior. These facts do not identify the newly observed query-match mismatch.

## Active todos

1. COMPLETE: merge PRs #43-45 after hosted checks and authorization.
2. COMPLETE: qualify and deploy exact source-stamped host 0.3.54 / native 1.8.34.
3. COMPLETE: verify preservation, shortcuts, manager startup and loaded extension.
4. COMPLETE: verify and retire obsolete host/payload files while retaining diagnostics.
5. ACTIVE: diagnose `query_match:stale`, then complete bounded manual-list attack,
   removal-triggered cancellation and recovery acceptance.
6. PENDING: obtain the authoritative server character-session contract before
   implementing automatic retaliation.

No live-combat acceptance success is claimed by this deployment receipt.
