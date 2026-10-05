# Official client 1.3.38.14 update — October 4, 2026

PR #65 merged into shared `main` at
`03375a9b989aa4c01735ce70d91a4b8218744e18` after all 15 hosted checks passed.
Host **0.3.67** / native **1.8.47** are qualified from exact source
`a34a57ff9037018765a9ce6e3614b5792c5e6e43`, including the two reviewed client
1.3.38.14 hashes while retaining signature checks and unknown-image rejection.
Installation and launch are **verified**: host .67 / native .47 now run with
prepared client .14. Installation verified 463 host modules, 9,578 retained files
and exactly three client inventory changes: executable, CObjects cache and DLL.
Settings and jobs remain in place. Manager PID 6072 activated healthy and unbound,
with only the expected dispatch-permit revocation. Five shortcuts and startup
preflight passed.

Launch at **2026-10-05T00:34:41.1329652Z** verified the qualified DLL in PID 7516,
creation FILETIME `134356340764063745`, HWND `1115034`. Passive readiness was
**not ready** at login/loading; no gameplay action was issued. User login and
fresh in-world readiness remain pending. These process values are historical
receipt identity, not continuing session authority.

The exact-source package `artifacts/b47/d2707a93` passed 4,893 host tests with
37 skips. Each native profile passed 224 native tests, all 126 required native
gates, 73 movement IPC, 86 combat IPC and 146 actor IPC tests. The three skipped
CTest wrappers (movement image, cue binding and sky binding) each have separately
executed actual-image probes. The two known optional transparency findings per
profile are separate from those wrapper skips. Independent package
verification checked all 110 indexed artifacts and 82 stages.

| Qualified artifact | SHA-256 |
| --- | --- |
| Package archive | `9509c04d7f74d02a1ae238a8371dc8fa798375c6e784898915ee1ece72d74820` |
| Full-profile DLL | `2190c30b754f392021dd460b7b1d0e20e6d0cbf5eb14d58c06b0e95684586f88` |
| Host wheel | `5c972e988cc802e18c11f0fe6fdf83e463ac0dd95e95c4ccbb1bc6a25959026e` |

The official manifest fetched at 2026-10-04T23:57:17Z contains 211 files and has
SHA-256 `fa73867708fef4e53acbbdb173897d5eacc3d31f10cf66c43e96896025d56eee`.
Compared with the reviewed .13 manifest, exactly two files change and none are
removed. Metadata version strings remain insufficient to identify the client;
the file hashes and embedded executable version establish this patch.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| Official `sb.exe` | 21,143,613 | `e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e` |
| Prepared `sb.exe` | 21,143,613 | `78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903` |
| `cache/CObjects.cache` | 5,432,558 | `5979b544426669e1ffd89fdf95a7a7800d1b42a6cfc7840c942efed1656ff2f7` |

The official executable differs from reviewed .13 by one byte at file offset/RVA
`0x12dc18c`: ASCII `3` becomes `4` in the embedded version. Every other byte,
including executable code, headers, imports and relocations, is identical.
The `.text` SHA-256 remains
`5cab14307005f6ebdfa268107aa2a1aeba35cb071b17cdf3d01665a3f3294607`.
No inventoried calibration anchor intersects the changed byte. All seven loader
writes resolve at their reviewed locations, without relocation or ambiguity.
The derived prepared .14 image likewise differs from prepared .13 only at that
version byte. This proof does not authorize unknown future images.

The pre-deployment baseline had both games closed and the existing manager
healthy with no bound slots. The original client already matched official .14
and its new CObjects cache; Vendor Test matched prepared .13 and the prior cache.
Deployment verified those different starting states. Both clients retain the
unchanged official Config.wpak; Vendor Test now has prepared .14 and the new cache.

The user resolved the cursor offset and corrected the original display settings
to 1920x1080, fullscreen, hardware cursor. Those three settings were carried into
the closed Vendor Test client, with all other preference bytes preserved. Their
live behavior on the updated Vendor Test client remains to be checked.

Follow the [deployment policy](deployment-policy.md): preserve settings, jobs and
historical diagnostics in place; create no rollback runtime or archive. The
October 4 capacity audit found C: full and retired obsolete deployment assets
from five older clients. Receipts record 798 removed files / 11,667,960,650 bytes,
with 180 settings/log files verified unchanged. Those capacity removals did not
alter the then-active .66 installation. After .67 activation, exact ownership
checks retired the obsolete .66 host (2,116 files) and two .46 guest payloads,
totaling 50,827,934 bytes. Four obsolete host/share staging files totaled
5,631,830 bytes. No rollback copies were retained.

Retirement of 21 additional old Python environments remains blocked by automatic
approval review pending explicit user approval; none is recorded as removed. The separate non-test VM guest audit could not
authenticate and
its existing VM snapshots were not changed.

Private official inputs, binary comparisons, deployment baseline and completed
qualification receipts are under `artifacts/guard-deploy/client-update-20261004`.
Its `receipts` directory contains 12 compact deployment receipts and seven
verified installed-file hashes.
No private binaries, captures or credentials belong in source delivery.

Next: user login and fresh in-world readiness, then resume the pending
potion-overlap and repeated buff-expiry/reuse checks.
Automatic retaliation remains disabled pending authoritative character-session
provenance. The prior bounded NPC/buff acceptance remains historical .66 evidence.
