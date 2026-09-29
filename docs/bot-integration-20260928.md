# Bot integration candidate - September 28, 2026

## Integration completed

[PR #43](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/43)
merged the approved head `127bf94476db0ec73199381a9057e6c8a263b799` into main as
`d3389d4eff992074f7a63394c735f5b4cfd1d993` after all 15 hosted checks passed.
All four exact lane tips below are ancestors of main; PRs #38-42 are also marked
merged. The normal checkout was fast-forwarded cleanly to main. This completes
the source publication, hosted validation, and approved integration todos.

The rest of this document is the pre-merge qualification receipt, not current
branch status. Continue with [the September 29 deployment handoff](bot-deployment-20260929.md).
The installed runtime was not changed by the source merge.


## Source and ownership

`codex/bot-integration-20260928` is the isolated combined review branch targeting
`main`. The normal checkout remains clean on `main@a91dfd5`. No merge into main,
deployment, or live attack is implied. Candidate package identities are host **0.3.53** / native **1.8.33** for the
reviewed prepared client **1.3.38.12**. The original feature worktrees remain
available while their reviews and live acceptance are unfinished.

| Included lane | Exact source tip | Review |
| --- | --- | --- |
| Current client and vendor workflows | `15657325430dc3a92ca10e49cb9079000dd794c5` | PR #40; includes vendor PR #38 through `a87a7af` |
| Exact PvE health-zero attribution | `8e87a47df171e4d13bd3370b84aef41c34e344e9` | PR #41 |
| Captured client command ownership | `daec3d17c45ff67bb0e9cf4fcdc6bffd1dc62aa2` | PR #42 |
| Explicit-list native combat | `a6e8114f98a4702153d775f3b8aef7f3546d2f1c` | Draft PR #39 |

These are ancestry-preserving source merges, not cherry-picked replacements.
PR #41 and #42 each passed all 15 hosted checks at the exact listed tips. The
combined validation below is separate; those earlier runs do not certify this branch.

## Current-client qualification

The ordinary manual-combat callback contract was reviewed against prepared
client 1.3.38.11. A fresh complete-file comparison of the retained prepared
1.3.38.11 and 1.3.38.12 images found exactly one changed byte, at offset
`0x12dc18c`: ASCII `1` becomes `2`. Both files have 21,143,613 bytes. All native
code, callback tables, imports, and PE layout remain identical.

The [compact comparison receipt](../evidence/pvp/combat-client12-qualification-20260928.json)
records both complete executable hashes and the identical prepared `.text`
hash. That prepared section differs from the official-original section hash
in the client-update review because the reviewed loader transform changes code.
Original binaries and private disassembly remain local and are not source exports.
The existing movement verifier must still validate the actual loaded image.
This does not admit arbitrary clients or qualify live gameplay.

## Combined validation

The final combined runtime source is `3897c8e` (later handoff edits are documentation
only). The full host suite passed **3,795 tests and 766 subtests**, with 33 explicit
skips. Repository Ruff and whitespace checks passed. Real Win32 fence/receipt/wire
interop passed 50 tests without skips using the built full-profile consumer.

Both MSVC Win32 Release profiles build. Each required native suite has 189 tests:
186 passed through CTest, and the three private-image fixtures passed separately
with the exact current original/prepared client files. Thus all 189 required native
checks were exercised successfully per profile. Host/native fence and wire interop
also passed 27 tests for each profile. Independent source reviews covered native
lifecycle, receipt retirement races, image admission, and the additive vendor/combat
channel merge. The merged vendor-menu channel needed an explicit BCrypt link;
both vendor and combat channel regressions pass with that correction.

The existing transparency diagnostics checker passed in each profile. Its two
optional renderer tests still have four reviewed counterexamples per profile;
this work does not claim those rendering failures are fixed. Required tests pass.
Local build logs and JUnit receipts remain in ignored `build/native-full` and
`build/native-diagnostics-only`; no private executable is part of the source PR.

Host 0.3.53 wheel construction and isolated installed-wheel import/CLI smoke checks
pass. The initial non-isolated wheel attempt lacked the local `bdist_wheel` tool;
the declared isolated build environment resolved that tooling issue without a
source change or a global Python installation change. Build outputs are validation
candidates, not retained deployment fallbacks. No VM runtime was replaced.

## Delivery gates

Manual-list combat, automatic response insertion, and live acceptance are
separate. Automatic response insertion remains blocked on the authoritative
[server character-session fence](pvp-response-provenance.md). No client timestamp,
chat name, or current connection substitutes for original-event provenance.

Follow [the native entry contract](native-combat-entry-contract.md) for local
cancel confirmation and queue-receipt limits. A queued attack cannot be recalled
by changing the saved list. Confirmed scene retirement stops the old encounter
and must never resume a replacement character's PvE run.

1. COMPLETE: inspect fresh origin, preserve main and feature ownership, merge the three completed lanes.
2. COMPLETE: integrate final combat source and validate the full host suite, both native profiles, real IPC, current image admission, and wheel smoke checks.
3. ACTIVE: publish the candidate and review evidence; inspect exact-head hosted checks and obtain main integration approval.
4. PENDING: current-client live acceptance; automatic retaliation requires the server session contract.

No retained deployment rollback copies are allowed. Preserve settings and jobs
in place and rebuild reproducible software from its committed source.

The earlier standalone PR #41 merge question is superseded by review of this combined
candidate, which includes its exact head and the other listed lanes. Keep the original
PRs/worktrees until integration and ownership are resolved; a source push alone does
not authorize their retirement. Other renderer, town, and cancelled carpenter drafts
are not silently merged or discarded. The normal checkout remains on main.
