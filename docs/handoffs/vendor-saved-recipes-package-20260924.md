# Saved random recipes candidate - September 24

Native **1.8.31** / host **0.3.51** is built from exact pushed source
`9f96813a31fcd2073cf32cd23798e77a1b1a8b06` on `codex/vendor-town-workflow`,
[draft PR #38](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/38)
targeting `main`. Feature checkpoint `eb7c239` adds actual recipe loading, immutable
per-character/building/vendor preferences, exact random preparation, one
available-capacity batch, automatic Inventory opening and Keep. Unknown affixes
are retained. Town visits and repeat scheduling remain unfinished.

The candidate starts from canonical main plus the vendor lane. Cancelled carpenter
preview and recorder drafts are excluded. The installed 1.8.30 / 0.3.50 runtime
and its rollback remain preserved. No game command or live crafting was performed.

## Exact-source validation

Private successful package: `artifacts/v31/58165a7b` under the normal repository.
Its immutable source archive, all 60 receipt-listed artifacts, package ZIP, wheel
metadata and embedded source identity were independently checked. The ordinary
client realigner/bootstrap author produces seven reviewed writes and exactly the
same prepared executable bytes as the currently installed client.

| Artifact | SHA-256 |
| --- | --- |
| Acceptance ZIP | `aab877db358e7cfb4326820d85d75f50b76484e92448a1dd9cdf03539d4b5baf` |
| Receipt | `318557d8dc3c125c49a6fb5795c1445e4e3df1ac0448d5e34a29354fac8eeab3` |
| Full-profile DLL | `5f06e82f897aa6fc7b82e43be7edb743d53f45582c75f15d6cf92efe4be46524` |
| Host wheel | `8c0d0563c6d1404349c2bfe5dbeb2d307c4f98b301e931fd717e2cba56a6798f` |
| Prepared executable | `7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f` |

- Complete host suite: 3,647 passed, 19 skipped; Ruff passed.
- Both Release Win32 builds and 172 required native tests per profile passed.
  Three private-image tests skipped in each general run execute as separate
  exact-client gates and pass. All three vendor menu tests explicitly execute
  without skips in both profiles.
- Both profiles pass 63 movement IPC tests plus exact-client selected-cue,
  movement/bootstrap and sky binding/render checks.
- Installed-wheel entry points, panels, vendor wire/session and navigation
  contracts and trace readers pass.
- The two established ideal-transparency counterexamples remain recorded as
  deferred diagnostics in each profile. They are not new vendor regressions or
  claimed visual acceptance; required production gates pass.
- Earlier attempt `artifacts/v31/eca1cbb5` failed the version consistency test.
  The missed public version macro was corrected in `9f96813`; that failed attempt
  is excluded from the candidate and retained only as private diagnostic evidence.

All hosted required checks pass on exact PR head `9f96813`. No merge is implied.

## Deployment boundary

The new payload is separate under `upgrades/vendor-saved-recipes-1.8.31`, with a
new `host-0.3.51` environment. Preparation installs that isolated wheel and validates
the existing runtime without replacing its loaded DLL or stopping the game.
Application requires closure and verifies the old source `8ba1818`, DLL, current
host, exact executable/cache and launch metadata before any replacement.

The apply helper creates an immutable rollback for the DLL, package evidence,
launchers and readiness metadata; readiness is published last after verification.
Every worker/job/recipe record, prepared-client CFG and guard qualification JSON
is inventoried. Normal-client CFG files are independently hash-checked. The existing
five shortcuts retain the same launch behavior; Vendor Test remains the user entry.
Neither the old payload nor its rollback is overwritten.

At 2026-09-25 00:26:17 UTC (September 24 local), isolated preparation passed.
All 436 installed host module files match the exact wheel; the validator inventories
9,426 retained worker/settings/qualification files and 17 normal-client CFG files.
The prepared executable is unchanged, crafting journals are untouched and the
running 1.8.30 client remains active. State: `prepared_not_applied`.

## Installed and activated after confirmed closure

After the user confirmed closure, the game-process check returned no instances.
The exact old idle manager was verified and stopped. Application completed with
five verified rollback files, unchanged executable bytes and unchanged crafting
journals. All 9,426 retained files and 17 normal-client CFG files passed preservation.
All five shortcuts and the non-launching preflight passed.

Native **1.8.31** / host **0.3.51**, exact source `9f96813`, is now installed.
The new manager is healthy and unbound; its process identity was independently
verified against the `.51` interpreter. During activation, 9,425 retained files
remained byte-identical; only the expected idle `dispatch.permit` changed, and it
was verified revoked/unbound. All 17 normal-client CFG files remain unchanged.
The game was not launched by the update, and no crafting action was submitted.

Private receipts live under `upgrades/vendor-saved-recipes-1.8.31`: update receipt,
retained-file inventories, immutable rollback, shortcut verification, launch
preflight, activation and manager-process verification. The previous 1.8.30
payload/rollback remains intact. Private helpers and package files stay outside Git.

Next: launch **WonderBane Vendor Test**, log in as Bart, then supervise actual
recipe loading, saving a choice and one batch. Preserve the original journals and
unknown-affix policy. Gameplay acceptance and full town scheduling remain pending.
