# Client update - September 26, 2026

**Current deployment policy:** [No retained rollback artifacts](deployment-policy.md).
Do not retain deployment copies, archives or old runtimes for rollback, and do not
reserve disk space for them. Recover from committed Git and official client assets;
preserve settings and job records in place. Older rollback requirements are superseded.

Official client **1.3.38.12** changes the executable and two data files. The
candidate is native **1.8.32** / host **0.3.52** on `codex/client-update-20260926`.
The branch starts from freshly fetched main plus vendor PR #38 through `a87a7af`,
including the deployed saved-recipe source and the reviewed dashboard selection
routing fix. It excludes the separate PvP and cancelled carpenter drafts.
Integration destination: `main`, with vendor inclusion made explicit in review.
Exact package source is `e9bf9334043e989cf7438f634de2b488f6ac5569`.
[Draft PR #40](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/40)
targets `main`; no merge is implied. Later documentation commits do not change
the installed/package source identity.

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
complete file verification, settings/job preservation and healthy manager activation.
A failed or incomplete update keeps readiness blocked until the intended committed
version is rebuilt or repaired; retained deployment rollback copies are not used.
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

Next: launch WonderBane Vendor Test and log in, then diagnose manager attachment
and complete saved-recipe/one-batch acceptance. Client installation is verified
below; live gameplay acceptance remains open.

## Exact-source package qualification

Private package: `artifacts/c32/f3228ad3`. Required qualification passed:

- 3,665 host tests (18 explicit skips), Ruff and installed-wheel entry points.
- 172 native tests in each of full and diagnostics-only profiles; the three
  private-client tests skipped by generic CTest ran separately and passed.
- 63 movement IPC tests in each profile; actual-client selection, movement,
  sky binding and render checks passed. Vendor menu controller/channel/native
  tests executed and passed in both profiles.
- All 60 receipt artifacts, archive contents/SHA and installed-wheel source
  identity match exact source. All 15 hosted checks passed on `e9bf933`.

Two existing ideal-transparency diagnostic failures remain recorded separately;
no required gate failed and no improved transparency claim is made.

| Artifact | SHA-256 |
| --- | --- |
| Acceptance archive | `168bd6c1efe0c9c5dc0aa13525bdd359539bad5a253162d44fd4c52ad1b4c35c` |
| Full DLL | `2e94313a93c261ad862437f4fd263ef9b33fe7c1e665fdd7cb35ec70310cd114` |
| Host wheel | `3b393583fab3f5a5f7e4225d521f8fbcac0d2f175ba72d55e53d87260cd7e4f3` |
| Receipt | `287d598713985ec116df8d4a176ff8744f2e06f093ce67d9b433e723c3287f92` |

The first preparation attempt stopped before writes because the VM had
759,132,160 bytes free, below a blanket 1 GiB check. No existing runtime was
changed and no new host/update directory was created by that attempt. The final
updater checks only current payload/host/atomic-write needs. The user explicitly rejected retained rollback artifacts and
rollback-space gates afterward; the successful deployment follows that policy.
This preparation failure is historical evidence, not a requirement to preserve
old deployment copies. Settings and job records remain preserved in place.

## Verified VM installation

Both VM client copies now contain official 1.3.38.12 data. The normal executable
matches the official hash; Vendor Test matches the reviewed prepared hash and
full DLL above. Native 1.8.32 / host 0.3.52 are exact source `e9bf933`.
All 436 installed module files match the wheel. All five desktop shortcuts and
non-launching launcher preflight passed; use **WonderBane Vendor Test**.

Application preserved 9,450 historical records/settings files in place, including
17 normal-client CFG files. Activation left 9,449 unchanged and made only the
expected revoked/unbound `dispatch.permit` transition. The actual manager uses
the 0.3.52 interpreter and reports healthy, unbound status with no game running.
No game launch or crafting command was issued. Healthy unbound status does not
resolve the previous live attachment failure.

**No deployment rollback copies were created.** Removed 35 inspected obsolete
VM rollback directories (213 files; 54,855,078 bytes) and three old host-side
client preparation backup directories (3,730,448,084 bytes). After checking
interpreter, process, launcher and package-asset ownership, removed all 30
obsolete `host-0.3.22` through `host-0.3.51` environments (619,542,556 bytes).
The current 0.3.52 runtime uses the separate system Python installation; no
active runtime depends on the removed environments. Original user data and
diagnostic evidence are preserved. Recovery uses committed Git and official
client assets; historical rollback instructions are superseded by the policy.
Private verification receipts remain with the September 26 deployment artifacts.

The source branch remains unmerged in draft PR #40, including vendor PR #38
through `a87a7af`. Normal project checkout remains clean on `main@a91dfd5`.
Separate PvP PR #39 is not installed. Next active todo: user login, then manager
attachment and recipe acceptance; no client-update implementation todo remains.
