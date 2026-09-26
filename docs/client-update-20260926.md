# Client update - September 26, 2026

Official client **1.3.38.12** changes the executable and two data files. The
candidate is native **1.8.32** / host **0.3.52** on `codex/client-update-20260926`.
The branch starts from freshly fetched main plus vendor PR #38 through `a87a7af`,
including the deployed saved-recipe source and the reviewed dashboard selection
routing fix. It excludes the separate PvP and cancelled carpenter drafts.
Integration destination: `main`, with vendor inclusion made explicit in review.
This source checkpoint does not imply package qualification or deployment.

## Binary and alignment evidence

The existing client comparison/realignment tool compared official 1.3.38.12
against reviewed 1.3.38.11. Both files are 21,143,613 bytes. Exactly one byte
changes, at file offset/RVA `0x12dc18c`: ASCII `1` becomes `2` in the embedded
version. Every other byte is unchanged, including executable code, PE headers,
sections, imports and relocations. The `.text` SHA-256 remains
`5cab14307005f6ebdfa268107aa2a1aeba35cb071b17cdf3d01665a3f3294607`.
No reviewed anchor intersects the changed byte. The bootstrap aligner resolves
all seven loader sites exactly, without relocation or ambiguous matches.

| Executable | SHA-256 |
| --- | --- |
| Official original | `3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7` |
| Prepared loader copy | `2dc0e19c3fcf43bc19508939fb9c63982bc370a868f810208394324a12cdc289` |

The source adds only these reviewed identities to the relevant existing layout
admissions. Prepared-only boundaries remain prepared-only; this does not qualify
future executable variants or gameplay behavior. Private comparison and bootstrap
reports remain under `artifacts/guard-deploy/client-update-20260926`.

## Official data and installation boundary

The current official manifest has 211 files. Relative to September 24, only
`sb.exe`, `Config/Config.wpak` and `cache/CObjects.cache` change; no files are
removed. Downloads match every expected size and SHA-256. Both VM client copies
need those three files; only Vendor Test receives the loader transform and DLL.
User settings, saved jobs, historical journals and normal-client CFG files must
be preserved. The existing Vendor Test entry point remains the default.

Read-only VM inspection found the game closed and both copies still on reviewed
1.3.38.11. Installed native 1.8.31 / host 0.3.51 is exact source `9f96813`.
Deployment requires a successful exact-source package and fresh baseline checks,
immutable rollback, complete file verification and healthy manager activation.
No game launch or crafting action is part of the client update.

## Included vendor correction and remaining work

`a87a7af` fixes three outer dashboard selection guards that previously rejected
saved vendor recipes before reaching the worker. Its regression exercises the
actual authenticated HTTP route, live wrapper, manager, worker queue and complete
saved-recipe batch; 104 focused tests passed. Malformed selection and stale-instance
rejection remain intact. This correction is included to avoid reinstalling a known
blocked recipe path during the client update.

The prior live game loaded 1.8.31 and Bart was observed, but the manager reported
no attached game. Attachment diagnosis and real saved-recipe/one-batch acceptance
remain unfinished; package validation is not gameplay acceptance. Full town
scheduling and separate PvP attack/cancel integration also remain unfinished.
Guards are set aside and carpenter work remains cancelled.

Next: complete compatibility validation, build and qualify the exact-source
package, update both VM copies and verify launcher/manager behavior, then resume
vendor attachment and recipe acceptance.
