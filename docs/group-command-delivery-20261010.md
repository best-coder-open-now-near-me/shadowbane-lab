# Native group command delivery - October 10, 2026

## Current state

PR #155 merged as `b24e8d13be9b1acc33f33e361e5c85024e6555e5` after
all 15 hosted checks passed at reviewed source
`dba01f1ff89d829dda28d120e5f297654a047f90`. The qualified host
0.3.97/native 1.8.62 release is pushed on
`codex/native-group-command-release-20261010`, commit
`182077fd9f358ee26a94aeaf0aae84d643acd4ea`.

The release combines the group-command feature with installed graphics and
PR #154's native text-input correction. PR #154 merged as
`4713727333d1cd09bb73c44c850c7b3108a3484d` after all 15 hosted checks passed.
Official client 1.3.38.17 and its prepared executable remain unchanged.

The user closed Vendor Test, and host .97/native .62 is now installed. The manager
activated successfully with all 491 installed modules verified and 9,607 retained
records preserved without exclusions. Client executables and resources are
unchanged; the sole client binary replacement is the qualified native DLL.
Desktop shortcuts target the new host. The earlier .96/.61 candidate was never
applied and is retired. Fresh client startup is verified; login and live command acceptance
remain to be checked. The normal checkout is clean on main at the PR #155 merge.

Installation receipts: apply `f658824b286054c1f8b9d164f05bed586588d79033e31ed77391e22284183116`,
shortcuts `60eb62d37a078ead1b81f7b0d7d190514bf879a46fc141e2ee64289f43ca76c6`,
activation `470bc2622f9b58283eb3de0bbe11f556bd41de7052487229f5d975345a7d32cd`.

## Behavior

Any current group member may send literal `/come` or `/attack first_name`.
The former cancels the current task through its owner, confirms cleanup, travels
to the sender's native position with ordinary obstacle handling, and stays there
with maintenance. It does not resume the previous camp. The latter resolves one
native player identity and attacks that exact target until death, cancellation,
target loss or native failure, without editing saved attack lists.

Listening has its own per-character setting and starts disabled on migration.
Umbra's authorized listener will be enabled through the installed settings CLI
once the new runtime and current character are verified. Hunt Foe and buff
preferences remain unchanged. Disabled or ungrouped listeners avoid population
scans while consuming receive history. Detect Hidden and Reveal are learned
abilities; these commands do not automatically cast them or claim live effects.
See [the implementation boundaries](native-group-commands.md).

## Qualification

Independent reviews approved native receive, host command ownership, the player
executor, the merged source and release composition. The exact release archive
passed 6,213 host tests with 43 optional skips, both native profiles and all
required gates across 112 recorded stages. Both profiles passed movement/combat/actor interoperability
counts 76/86/245, including both new group-frame cases exactly once without skips.
The existing two graphics transparency stretch findings per profile remain
explicitly diagnostic; no new required-gate failure was accepted.

The independent verifier rehashed all 140 artifacts and all 491 source, wheel and
installed modules. All 158 qualification cases passed without skips. Six installed
desktop cases and one real worker startup handshake also passed without skips;
their gameplay dependencies were substituted. An independent final artifact audit
reproduced all qualification receipts and checked their logs and fixture bytes.

| Receipt or artifact | SHA-256 |
| --- | --- |
| Acceptance archive | `3b7061e46e64ca368851ca669e809f8b16fefbbf8ed941abcb23d992e47bbd32` |
| Builder receipt | `6614ee8a77634439919f65d4e58abb61c05570d7673818953ca1ec072cd7e238` |
| Native full DLL | `9e39aebc287f277a33bb90ee655f4df0bc777d9e57f7938deb78f7d63e018cc9` |
| Host wheel | `278489c7cba1e842699075cc48a4c1ad9b14873f5baa5450448a2f67bebcdc50` |
| Independent verification | `ea8333fae6653273545618fbfc288fed22149f3c49b6ed7febbafd106018130c` |
| Supplemental verification | `d4a580a98c088a76e7b644db288f1d9d6ac90d7ccaaa47e7e174cf06d031c480` |
| Successful preparation | `09ea88f95a46434cbe9de161ca6f48005961f25c3a1ed0bab98092a1cbe8231b` |
| Reviewed update plan | `c765c4e99e071f4b9e86dd5d680554866d2528222437915bf1e3e0e99cb6e406` |

The deployment baseline verified all 486 then-installed .95 modules and
9,564 retained records. Compared with the earlier preparation baseline, only the
three expected live status records changed; no records were missing or added.
The approved payload contains 26 members and the 491-module candidate manifest.
No rollback copies or fallback runtimes are authorized; preserve settings, jobs,
journals and diagnostic evidence under [the deployment policy](deployment-policy.md).

The superseded VM candidate is retired: unused host .96 and the eleven staged
.61 wheel/DLL files are absent, freeing 59,250,267 bytes. Fresh checks confirm
the then-active .95/.60 and game were unchanged. The retirement receipt
is `db3dca7069ac92ae2b8aadcfb50c26643e89515ac7e67cf9997918e808eb8a07`;
its postcheck is `1784ee7ddeae2197ef5d8b1fa9f2249c3ef8b7cfe9cac84c07adc24000ba4d7e`.
User data, metadata and diagnostic receipts remain preserved. The separately
reviewed local .61 inventory is also retired: 2,862 exact generated files and
reproducible archives totaling 214,561,063 bytes. Every unlisted file, extracted
source, log, XML result and diagnostic receipt remains. The cleanup receipt is
`1030b4c4a882ce5fd82aa4f71e66c4469d1b9f3eac4096bac2d29a309f824151`.

Vendor Test reopened as PID 8068 with creation identity 134361421939134903,
window 2884278 and the exact .62 DLL. Launch receipt
`00634919c10f7962f7829dbf68c3ec0f5200a8a81e538aa7616188f2d64d47fc`
and post-launch status
`801ec9261f6f65b71caed4b7d08007bb05f40af2ca9d1cc283d28ecc2062dcca`
confirm a healthy manager and no bound worker or queued operation before login.
The user has been asked to log Umbra in. No listener setting or live combat was
changed before current character verification.

## Remaining work

1. Installation, manager activation and fresh client startup are complete.
2. Verify native startup, installation preservation and Umbra's identity, then
   enable her requested listener through the normal settings path.
3. Check a real group `/come` and an explicitly supplied player `/attack`/cancel;
   complete the pending same-camp return check. No live result is assumed.
4. Retire inspected obsolete software, preserve compact receipts, and update this
   delivery record and the branch map with actual results.
