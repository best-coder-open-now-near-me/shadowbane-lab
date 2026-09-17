# Guard manager update: 1.8.10 / 0.3.19

Branch: codex/guard-upgrades. Packaged source: 25f607e (pushed).
Integration destination: codex/vendor-rolling, then codex/native-lifecycle-hardening,
then reviewed main. This source is not merged. The normal main checkout is clean.

## Source behavior

The update joins typed guard discovery, exact warehouse selection, journaled
withdrawal/deposit/upgrade transactions, persistent rank scheduling and manager
controls. The dashboard exposes Find guards, Upgrade verified guards, Pause,
Resume and Stop, with confirmed gold/upgrade totals. Start pins the prepared
selection displayed in the dashboard. Repeated ranks require observed rank
advancement before more spending. Interrupted transactions cannot be replayed or
bypassed by creating a new job. Original vendor jobs keep their separate records.

Full-town coverage and maximum rank remain explicitly unverified. This is a
funding/guard queue with a nearby discovery source; it does not establish a
complete town census.

## Validation

- Exact-source isolated host suite: 2,671 passed, 19 skipped; whole-source Ruff passed.
- Required native, IPC and reviewed binding gates passed for both build profiles.
- Installed wheel checks and six additional installed guard/native wire comparisons passed.
- Package artifact integrity and local update preparation were verified.
- Two existing stretch transparency diagnostics remain unresolved per profile;
  this does not claim whole-product visual acceptance or live guard acceptance.

## Next steps

The coherent host/native update is prepared but not activated. The user has been
asked to close the running game before replacing its loaded extension. Next:
activate the verified package, verify loaded identity, then qualify the live
funding/guard sequence. Keep the existing shortcuts and historical journals.
Do not replay unresolved actions or rebuild a later documentation-only commit.

Local activation instructions, rollback information, exact file hashes and build
logs are retained in the ignored task artifacts. No private deployment records
or binaries are included in this source handoff.

Remaining after activation: live qualification, positive maximum-rank evidence,
full-town membership/coverage, and review/integration into the shared branch.
