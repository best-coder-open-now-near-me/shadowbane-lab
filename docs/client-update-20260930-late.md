# Late client update - September 30, 2026

Installed host **0.3.58** / native **1.8.38** use exact qualified source
`05c888a4ff1e1443163ef3cb2ea6e2432672c372` with official client **1.3.38.13**.
[PR #51](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/51)
merged at `214bcdede95b8ef4f51cb1b13bdd64a31378dcb1` on October 1,
04:14:59 UTC after all 15 hosted checks passed. Qualification, installation,
manager activation and loaded-DLL identity passed. The bounded .58 basic NPC
attack/cleanup gate passed after login. The skill-opener attempt did not pass:
SELF_POWER remained UNCERTAIN without queue evidence or a followup attack, while
terminal native cleanup was confirmed. The earlier .57 manual-player recovery
pass and unconfirmed NPC cleanup attempts remain separate historical evidence.
See the [deployment record](queued-skills-20261001.md) for evidence and limits.

Current package and installation details are in the
[queued-skill deployment record](queued-skills-20261001.md). The unchanged client
binary/data proof and the older .56/.36 and .57/.37 receipts below are historical.
PR #50's .57 receipt facts are incorporated here without merging its Git commit;
that documentation PR remains open pending replacement-receipt review.

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

## Historical official-data and deployment boundary

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

## Historical .56/.36 qualification

Host focused validation passes 113 tests, including original/unknown-image
rejection before memory access, all crafting signatures, recipe ownership and
permanent native-character-session revocation on identity change. Ruff and diff
checks pass. Full host validation passes **4,059 tests**, with 33 explicit skips
and 801 passing subtests. Independent host/native review found no actionable
issues. Sixteen focused native tests and ten actual-image probes pass, including
registry, melee, power and scene checks against both images, original tree
behavior and paired original/prepared image authentication. Exact-source
packaging is qualified as recorded below; all 15 hosted checks passed at the
approved PR head before merge.

Qualification, approved merge and installation are complete. Supervised
object-based attack/cancel has initial live evidence below; PvE recovery and
NPC/cast acceptance remain incomplete. UI selection,
hotkeys and system-message text are not combat authority. Automatic retaliation
remains disabled pending an authoritative server character-session fence.

## Historical .56/.36 exact-source qualification

Package `artifacts/b36/d86bc533` is acceptance eligible at source
`e6c7a28f229043540d3f93181900072ded58752c`. All 78 recorded file hashes and
archive members match. Both full and diagnostics-only profiles passed 202 required
native tests and all 83 host/native combat IPC cases without skips. Three
image-dependent tests skipped by generic CTest were qualified separately, along
with the actual original/prepared registry, melee and power probes. Installed-wheel
entry points and source identity passed. Archived-source host tests passed 4,058
cases, with 34 explicit skips and 801 subtests (the normal checkout passed 4,059).
Two existing optional renderer-transparency diagnostics per profile still fail
and are recorded separately; no required gate failed or rendering fix is claimed.

| Artifact | SHA-256 |
| --- | --- |
| Acceptance archive | `b6dc81f9f538a920161fabcf1567e48cfd6e4b5024f8794d03940bc11553e4cc` |
| Receipt | `2f55952646890bf8beb4ca285e97487d1147a438135bbd06a49fc9b527aae2e6` |
| Full DLL | `df3f177b517c3b59ae117edf32a8928045fd0ce1f25a5e69c38d5c528b3cdd13` |
| Host wheel | `e514db4fa968de179a5833d5c7ad056b1534a93fc6a31b6d125171d5806889c0` |

Private deployment helpers passed independent review and ten offline tests; all
Python and PowerShell helpers parsed. Qualified release pins were finalized before staging. The October 1 01:27 UTC
read-only inspection found the old game running; the later closed-client snapshot
was required before preparation. The user confirmed closure and approved the merge.
Installation is verified below; full live combat acceptance remains incomplete.

## Historical .56/.36 installation and first live attempt

All 15 hosted checks passed at approved head `f73f7d53557721f449e7547de85e5b6f26a7f8e4`.
PR #48 merged at `35fce4ba273a399b31e577d6d487a68b08dc34e3` on October 1,
01:50:01 UTC. The normal project checkout was fast-forwarded to that merge.
The obsolete late-update and PR #47 documentation branches were retired only
after their exact tips were verified in `origin/main`. The bot-runtime worktree
now holds the deployment handoff on `codex/client-deployment-20261001`.

Both client copies contain official 1.3.38.13 data. The normal executable matches
the official hash and Vendor Test matches the prepared hash above. Host 0.3.56 /
native 1.8.36 use exact package source `e6c7a28`. Installation verified 450 module
files, 9,559 preserved settings/record files, five shortcuts and non-launching
preflight. Manager activation was healthy and unbound at observed PID 1816; the
only expected retained-file transition was the revoked/unbound dispatch permit.

The old host 0.3.55 contained 2,090 verified generated/distribution files,
47,546,902 bytes and no unknown data or active references. Its inventory SHA-256
was `bfb3c5ae8674deec416de60f8df76baa8ad004c49f9e473c63379e6e0a153b3f`.
After activation verification it and the exact two obsolete b35 guest payload
binaries were removed: 50,214,524 bytes total. No rollback copies were retained.
Eleven compact deployment receipts and their hash inventory remain under the
private late-patch artifact directory.

Launch at 01:58:35 UTC verified the new DLL in game PID 460, creation time
`134352935067334669`, window `7406358`. These are recorded process observations,
not enduring authorization. After the user reported readiness, native objects
identified Umbra and `day` on Wonderbane about 23.5 world units apart, with full
resources. Native capability `0x10` and movement readiness were present.

The first bounded attempt (`4c73d85b6723485bbd998e5d53054bcf`) queued the manual
attack against Day while the selected object remained Umbra. Its test-owned list
entry was removed and the final list was empty. Terminal cleanup confirmed
`NATIVE_STOPPED` for that engagement, with no ordinary NPC proposals. However,
the runner reported `emergency_stop` at 907 ms before cleanup and never reached a
strictly later SEEKING frame; the 12-second watchdog did not fire. This is a
partial result, not completed attack/cancel/recovery acceptance or proof of a
server-accepted hit. The second attempt below captures the interruption cause; bounded recovery and
NPC/cast acceptance remain open.

## Historical .56/.36 recovery diagnosis and .57 correction

The diagnostic repeat (`e3d20050df4d458a9d2ffd6bbc746b2d`) again queued the
manual attack and confirmed terminal native cleanup with an empty final list.
Before cleanup, it recorded `native_movement_unavailable`, no explicit/hotkey
stop, status flags `21`, and the exact original movement Grant still present.
In the installed implementation the camera bit proves `available_` was true,
while absence of READY proves `pending_stop_` was true. Native list revocation
had begun cancellation without retiring that owner; the host incorrectly treated
this temporary cleanup state as lifetime loss, including in lease renewal.

Candidate host **0.3.57** / native **1.8.37** makes cleanup-pending an explicit
status under the same exact automation owner. It must permit status, heartbeat
and cleanup completion while continuing to block new movement/combat actions.
Actual owner/scene changes, terminal status, focus/UI invalidation and other
safety failures still terminate the operation. No startup wait, input fallback
or arbitrary latency relaxation is introduced. Independent review and focused validation passed: 146 host tests and 15
subtests without skips, 40 native tests, 185 package-gate tests and Ruff. The real
host/native process regression holds the unchanged owner through 1.2 seconds of
unacknowledged cleanup, blocks MOVE and restores READY after the native callback
acknowledges completion. That test is mandatory in exact-source packaging.
Both-profile package qualification is next on `codex/client-deployment-20261001`;
the installed package remains
0.3.56 / 1.8.36. Next: qualify the complete fix, publish it for review/approval,
then repeat bounded recovery acceptance before NPC/cast work.

## Historical .57/.37 qualification and verified deployment

Package `artifacts/b37/3f2832bd` is acceptance eligible at exact source
`1d107a25c1356d20a0b633cc411d6b5efdc47a9b`; all 78 recorded artifact hashes
were verified. Archived-source host validation passed 4,086 tests, with 34
explicit skips and 801 passing subtests. Each native profile (full and diagnostics-only) records 202 passing
native tests, three image-dependent generic CTest skips, 83 passing combat IPC
tests and 64 passing movement IPC tests, including the mandatory cleanup-pending
cross-process regression. The official/prepared client hashes and seven loader
writes remain unchanged from the reviewed 1.3.38.13 update. The two optional
renderer-transparency diagnostics per profile remain separately recorded failures;
all required package gates passed.

| Artifact | SHA-256 |
| --- | --- |
| Acceptance archive | `10e2f3aa5605b0ccb08a6acb811668a98df03873dc0443bda780b376699c6af5` |
| Receipt | `a3aecd6a67b4c9269764eada98c40aaa82ee17c800abf0408ef68c2b84b6cb24` |
| Full DLL | `9da29afdd6dc94a23c03f7a563876bc7f5b6b29ecae8194b11f18ca620805b1e` |
| Host wheel | `9ca3db24c305762be042e15707861b855e3a969e45e2dd51527c14071aa03b16` |

Installation verified 450 module files, 9,566 retained user/settings/record files,
one client DLL change, all five shortcuts and launch preflight. Manager activation
was healthy and unbound at observed PID 6868. User data remains in place.

The obsolete host .56 contained 2,090 verified files and 47,550,096 bytes, with
inventory SHA-256 `a27cd66f724ee33be2dd04991ca7d44c31fce554322a5df56fb3088c83053250`.
It and the exact two old guest payload binaries were removed after verification:
50,218,181 bytes total. No runtime rollback copies were retained.

Launch at October 1 03:09:12.9305389 UTC verified the new DLL in game PID 3024,
creation time `134352977426142998`, HWND `8258364`. These recorded process values
are evidence, not enduring authorization for another action.

## Historical .57 passed manual-player cancellation and recovery

After fresh user readiness, the reviewed harness ran against the exact current
native objects with 98.7% player health, full mana/stamina and about 30 world
units between actor and target. Private evidence is retained under
`artifacts/bot-deploy/20261001-b37/2ed3fb4cadc744fbb9845a19f6e40de0`.

The intended manual-player attack queued, the test-owned list entry was removed,
and the harness verified correlated `NATIVE_STOPPED` cleanup followed by a strictly
later unlisted PvE SEEKING frame. Final list membership was zero; ordinary NPC
proposals were zero and the watchdog did not fire. The dispatcher interruption
reason remained null. The terminal `emergency_stop` was the harness's deliberate
explicit stop after recovery, not the earlier readiness-loss failure.

Trace loop timestamps place cleanup at 985 ms, later SEEKING at 1,344 ms and the
explicit stop at 1,485 ms; these are loop timestamps, not exact native latencies.
The reviewed synchronous harness and correlated receipts establish removal and
cleanup ordering; no separate removal timestamp is claimed. The harness checked
the typed native-stop proof even though the trace serialization omits that field.
Independent review confirmed the pass. A separate passive post-test observation
found the same process READY with no owner, no cleanup pending and no terminal
status.

This completes the bounded manual-player attack/cancel/recovery gate. It does not
prove a server-accepted hit, NPC combat or learned-power casting. At that checkpoint, NPC/cast acceptance remained next; the .58 status is recorded
in the current deployment section above. Automatic retaliation
remains disabled pending the authoritative server character-session fence.
