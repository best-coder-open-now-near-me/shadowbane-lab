# Official client 1.3.38.14 update — October 4, 2026

## Qualified .69/.49 buff scheduling repair - October 6

PR #69 merged at `490af652eaee83dd1914869ce99da9c908049f37` after all 15
hosted checks passed; exact qualified source is
`439d074051edc627ad8ba81a84113a345d2fd42c`. The .68 live run below exposed a
scheduler stall: after Beorc settled, fresh observations kept semantic revision
17 because the facts were unchanged. The policy incorrectly required that
revision to increase before submitting another buff. It now requires a later
validated native capture sequence, preserving semantic equality, lifetime,
immutable pending action, duplicate application and admission-refusal guards.

Package `artifacts/b49/4f564b4d` supplies host **0.3.69** / native **1.8.49**.
It passed 4,909 host tests with 37 skips; each profile passed 224 native tests,
126 required gates and 73 movement / 86 combat / 146 actor IPC cases. Independent
review verified 110 artifacts and 82 stages, both .14 client images, wheel source
and DLL identity. Known optional rendering findings are unchanged. Full DLL
SHA-256: `d4961bf0d50613d9d9e339691a4ef8ae0c29316c57c5842ed7f4e62cf7c36fae`.
The installer passed 20 offline tests and independent final pin review; the
bounded encounter helper passed 138 tests against the exact package. Private
receipts are under `artifacts/bot-deploy/20261006-b49`.

**Installation is pending client closure.** A fresh observation at
2026-10-06T19:46:02.3414972Z found PID 8832 running with .68/.48; the user was
asked to close it. No runtime replacement or .49 gameplay action is claimed.
Seven reviewed encounter helper files are staged on the testing VM share but
have not run. Next: fresh closed-client verification, install/activate and retire
only verified obsolete runtime files, then repeat the NPC and normal buff test.

## Current .68/.48 startup repair deployment - October 6

PR #67 merged into `main` at
`9cf9f20a322f4ce0b199c7806f509c1aa2c991cb` after all 15 hosted checks passed.
Exact package source `7aca53e3e6a66bbcddebdc6349ef96f86bbfdfaf` supplies host
**0.3.68** / native **1.8.48**. The stationary startup repair is merged and
**applied and verified**: 463 host modules, 9,583 preserved files and exactly one
DLL inventory change. Both client .14 executables, official data, corrected
1920x1080 preferences, settings and jobs remain in place. No rollback copies
were created. Manager PID 9108 activated healthy; all five shortcuts and startup
preflight passed. Launch at 2026-10-06T19:13:40.6492763Z verified the qualified
DLL in PID 8832, creation FILETIME `134357876109226569`, HWND `2687194`. Fresh
passive readiness reported ready with no actions sent. These are historical
receipt identities, not continuing session authority. The bounded live run below
completed NPC combat and cleanup but remains partial for buff preparation.

Package `artifacts/b48/64bc2349` passed 4,893 host tests with 37 skips. Each native
profile passed 224 native tests, all 126 required gates, 73 movement IPC,
86 combat IPC and 146 actor IPC cases. Independent verification checked all
110 indexed artifacts and 82 stages. The known image-wrapper skips remain
separately covered by actual-image probes, with only the recorded optional
rendering findings. The full DLL SHA-256 is
`d0fad978a7813f75eac3e0c2a0f90f483d35874b215c062a7885e658767e582e`.
Private qualification and deployment receipts are under
`artifacts/bot-deploy/20261005-b48`. Its `receipts` directory contains 12 compact
receipts and seven independently verified installed-file hashes. The obsolete
.67 host (2,116 files) and two .47 guest payload binaries were retired after
verified activation, totaling 50,832,946 bytes. Four exact old .47 host/share
staging DLL/wheel files were then removed, totaling 5,633,626 bytes. Settings,
jobs and diagnostic evidence remain in place; no fallback builds were kept.

The earlier .67 run observed all five buff groups PRESENT; its NPC acceptance
remained incomplete. Manual potion-overlap testing was canceled by the user.
The .68 run `actor-full-encounter-provisional-f6b83d15cdee407d9962c5a2b87e95f0`
remains **partial**. Shot queued, followed by one positively queued ATTACK; the
exact NPC `23886/37` reached observed native health zero at sequence 168. Child
cleanup confirmed NATIVE_STOPPED and parent cleanup LOCAL_RELEASED, with no
interruption or watchdog and zero retained list membership. Fresh readiness
afterward showed an idle, unowned client with no cleanup pending.

Concentration potion, Precision and Beorc coverage were PRESENT. Transform and
defensive stance remained READY/MISSING near 44 seconds; scheduler investigation
is active. These observations do not establish server kill credit or skill
consumption. Next: resolve why the ready missing groups were not scheduled, then
validate normal automatic buff refresh. The prior evidence remains unchanged.

## Historical .67/.47 client update and live attempts

PR #65 merged into shared `main` at
`03375a9b989aa4c01735ce70d91a4b8218744e18` after all 15 hosted checks passed.
Host **0.3.67** / native **1.8.47** are qualified from exact source
`a34a57ff9037018765a9ce6e3614b5792c5e6e43`, including the two reviewed client
1.3.38.14 hashes while retaining signature checks and unknown-image rejection.
Installation and launch were **verified**: host .67 / native .47 ran with
prepared client .14. Installation verified 463 host modules, 9,578 retained files
and exactly three client inventory changes: executable, CObjects cache and DLL.
Settings and jobs remain in place. Manager PID 6072 activated healthy and unbound,
with only the expected dispatch-permit revocation. Five shortcuts and startup
preflight passed.

Launch at **2026-10-05T00:34:41.1329652Z** verified the qualified DLL in PID 7516,
creation FILETIME `134356340764063745`, HWND `1115034`. Passive readiness was
**not ready** at login/loading; no gameplay action was issued. Subsequent in-world readiness passed for the same process creation and recreated
HWND `459704`, with a 1920x1080 client area at DPI 96. These process values are historical
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

The user removed potion-overlap testing as a requirement: potion and other buff
order are immaterial. The October 5 automatic run confirmed all five groups
PRESENT, including the concentration potion. Its NPC phase sent no attack: the
first candidate was NEVER_BOUND during preparation, and the bounded helper
refused a different candidate afterward. Parent cleanup was LOCAL_RELEASED.

The next run was rejected before actor ownership or any NPC action. Retained
native input evidence records a 313 ms update interval revoking movement
generation 5 to 6 with reason `stalled`, no keys, unchanged scene and window.
Fresh readiness afterward showed owner NONE, no cleanup pending and Umbra alive.
HISTORY_EXPIRED replies are not positive cleanup receipts.

The stationary startup repair is now merged and applied as recorded above;
activation and launch are verified; current live findings are recorded above.
Private original traces remain unchanged.
Automatic retaliation remains disabled pending authoritative character-session
provenance. The prior bounded NPC/buff acceptance remains historical .66 evidence.
