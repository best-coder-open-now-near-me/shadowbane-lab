# Official client 1.3.38.14 update — October 4, 2026

The original testing-VM client has received the official 1.3.38.14 patch. Vendor
Test still uses qualified host 0.3.66 / native 1.8.46 with prepared client .13.
Live buff/combat work is paused until the new exact client is qualified and
installed. Candidate host 0.3.67 / native 1.8.47 is being prepared on
`codex/client-update-20261004`, based on shared `main` at `a582368`.

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

The fresh deployment baseline has both games closed and the existing manager
healthy with no bound slots. The original client already matches official .14
and its new CObjects cache; Vendor Test still matches prepared .13 and the prior
cache. Both retain the unchanged official Config.wpak. Deployment must verify
these two different starting states rather than treating both as old clients.

The user resolved the cursor offset and corrected the original display settings
to 1920x1080, fullscreen, hardware cursor. Those three settings were carried into
the closed Vendor Test client, with all other preference bytes preserved. Their
live behavior on the updated Vendor Test client remains to be checked.

Follow the [deployment policy](deployment-policy.md): preserve settings, jobs and
historical diagnostics in place; create no rollback runtime or archive. The
October 4 capacity audit found C: full and retired obsolete deployment assets
from five older clients. Receipts record 798 removed files / 11,667,960,650 bytes,
with 180 settings/log files verified unchanged. Additional old Python-package
retirement remains in progress. These removals do not alter the active .66
installation. The separate non-test VM guest audit could not authenticate and
its existing VM snapshots were not changed.

Private official inputs, binary comparisons, deployment baseline and eventual
qualification receipts are under `artifacts/guard-deploy/client-update-20261004`.
No private binaries, captures or credentials belong in source delivery.

Next: complete exact-image admission review and both-profile package gates,
merge and install under standing bot approval, verify the fresh client/DLL,
then resume the pending potion-overlap and repeated buff-expiry/reuse checks.
Automatic retaliation remains disabled pending authoritative character-session
provenance. The prior bounded NPC/buff acceptance remains historical .66 evidence.
