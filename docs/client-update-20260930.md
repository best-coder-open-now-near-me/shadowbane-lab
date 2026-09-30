# Official client data patch — September 30

The official updater manifest at `http://87.99.132.84/manifest.json`, fetched
September 30 with the vendor patcher user agent, still lists 211 files. Relative
to the September 26 installed baseline, exactly two files changed; no paths were
removed. Both payloads were downloaded from the manifest's `client/` base and
verified against its exact size and SHA-256 before staging.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `Config/Config.wpak` | 2,954,064 | `cf2d8c1ea07588aab999563411b95981127d5ef10e32243940b185dbb99dde7a` |
| `cache/CObjects.cache` | 5,433,593 | `a6310236dc6c0ea3f2d5fe26b22bf1e1d767be781c7009507d4ff83cec524562` |

The official `sb.exe` is unchanged: 21,143,613 bytes, SHA-256
`3891fcab09dac06d858ac55911046448e75f3519e2f58e1d7c2ccc954aa410b7`.
It remains client 1.3.38.12. This patch therefore does not introduce a new
executable admission or native binding; exact-source package qualification still
runs against that reviewed original and its prepared image. The manifest's
`version` and `gameVersion` fields are unchanged and are not used as proof that
file contents are unchanged.

Private payloads and manifest comparison are under
`artifacts/guard-deploy/client-update-20260930/`; third-party binaries and caches
are not committed. The data-only patch was applied and verified at
`2026-09-30T16:54:23.758150+00:00` in both the official and prepared VM client
installations. The prepared package inventory changed exactly two records;
9,557 settings, jobs and diagnostic files retained their hashes. Both executables,
the native DLL, host runtime, launchers and shortcuts were preserved. No rollback
copies were created. Launch preflight passed without starting the game.

The installed bot remains host 0.3.54 / native 1.8.34, source
`ab5e043a84808eea776b2e463e7d6e3d2cf63116`. The object-tracking candidate in
PR #46 is separate and has not been installed. VM receipts are under
`C:\ShadowbaneLab-Guided\vendor-1.8.3-bd08ffc\upgrades\client-data-20260930`,
with exported hash/preservation/preflight receipts in the private host patch
artifact directory. Next: qualify the selection-independent native bot action
path before packaging and supervised gameplay validation.
