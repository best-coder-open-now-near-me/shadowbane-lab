# Late client update - September 30, 2026

Official client **1.3.38.13** changes the executable and two data files. Candidate
host **0.3.56** / native **1.8.36** is on `codex/client-update-20260930-late`,
targeting `main`. It includes merged object combat PR #46 and the deployment
receipt commits through `cab8b029` from draft PR #47. The normal checkout remains
on `main@7f250c6`. This candidate is not installed or merge-approved yet.

## Binary proof and admission scope

The original executable is 21,143,613 bytes. Comparison with reviewed 1.3.38.12
finds exactly one changed byte at file offset/RVA `0x12dc18c`: ASCII `2` becomes
`3` in the embedded version. All other bytes are identical, including PE headers,
section layout, imports, relocations and executable code. The `.text` SHA-256 is
`5cab14307005f6ebdfa268107aa2a1aeba35cb071b17cdf3d01665a3f3294607`.
None of the 50 anchors across 16 applicable calibrations intersects that byte.
All seven existing loader writes align exactly, without relocation or ambiguity.

| Executable | SHA-256 |
| --- | --- |
| Official original | `e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8` |
| Prepared loader image | `0ba5805e912b0665d2e236f15867047a0ed810c2e310599030df929a42b7493d` |

Only these reviewed hashes are added to existing admission boundaries. Original
images can be inspected and prepared; hooks and prepared-only readers continue
to reject original and unknown images. Runtime signatures, exact object/session
identity, capability gates and action acknowledgement requirements are unchanged.
No future-version admission or crafting affix-discard qualification is implied.

## Official data and deployment boundary

The official manifest still lists 211 files and stale metadata version
`20260518-185052` / gameVersion `1.0.5`; file hashes and embedded executable
version establish this update. Compared with the earlier September 30 patch,
only the following files change; no manifest paths are removed. All downloaded
sizes and hashes match the official manifest.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `sb.exe` | 21,143,613 | `e5bb74e159a9acd8529652eb5b0c07766ced7ffd70c03c960ccdbcefca83c6e8` |
| `Config/Config.wpak` | 2,954,695 | `4afb2ca2c9532f23739a2d809f9e22033cd986c3dff6ca05758edc8377dc9d1f` |
| `cache/CObjects.cache` | 5,432,563 | `4244a14735281d05a59d638b9106694693c79ee4b6f6d10d723fe3809ff758db` |

Read-only inspection at October 1 01:14:15 UTC found both installed clients still
on 1.3.38.12, with host 0.3.55 / native 1.8.35 and the earlier data patch. The game
was running, so this observation does not authorize replacing its files. Deployment
must recheck process closure, qualify an exact committed-source package, update
both client copies and verify manager activation, installed modules and shortcuts.
Only Vendor Test receives the prepared executable and extension DLL.

Preserve actual settings, saves, jobs and diagnostic records in place. Follow
[the deployment policy](deployment-policy.md): retain no rollback copies or old
runtime for fallback; recover code from committed Git and official client assets.
Retire the obsolete host only after successful activation and inspection of its
contents and references. Private downloads, comparison reports and receipts live
under `artifacts/guard-deploy/client-update-20260930-late`, outside source delivery.

## Qualification and remaining work

Host focused validation passes 113 tests, including original/unknown-image
rejection before memory access, all crafting signatures, recipe ownership and
permanent native-character-session revocation on identity change. Ruff and diff
checks pass. Full host validation passes **4,059 tests**, with 33 explicit skips
and 801 passing subtests. Independent host/native review found no actionable
issues. Sixteen focused native tests and ten actual-image probes pass, including
registry, melee, power and scene checks against both images, original tree
behavior and paired original/prepared image authentication. Exact-source
packaging and hosted checks remain pending.

Next: complete qualification, publish the combined PR and obtain merge approval,
then install and verify the update with the game closed. Supervised object-based
attack/cast/cancel/PvE recovery remains pending fresh user readiness. UI selection,
hotkeys and system-message text are not combat authority. Automatic retaliation
remains disabled pending an authoritative server character-session fence.
