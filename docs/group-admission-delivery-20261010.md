# Group admission and Track binding delivery - October 10, 2026

Host 0.3.99/native 1.8.64 is qualified, installed and activated. PR #158 merged as
`221d25ffa50a165a620d6e5382c89d22eb5e3345` after all 15 hosted checks passed
at source `72b1f15e4523e3752a4053231253214289cf5cc4`. Fresh client launch
is verified. User login/group readiness and live command/Track acceptance remain
pending; this checkpoint does not claim successful `/come` movement or Track hiding.

The exact release is `03923b56923ca2d36089ac8b53df12afe91a953c` on
`codex/native-group-command-release-20261010`. It preserves the installed
graphics composition. The package is private `artifacts/b64/aef70ab3`;
qualification evidence is under
`artifacts/bot-deploy/20261010-group64/qualification-source`.

## What changed

The native Track close guard now verifies the actual vtable slot, its exact
jump thunk and the close-body prologue. It still invokes the native slot and
preserves the existing automatic/manual presentation policy. The previous
synthetic fixture incorrectly represented the real slot as a direct body
pointer. Mandatory original/prepared image checks in both profiles now cover
this boundary without executing third-party code.

The host admission correction retains an unsubmitted group command when its
observation temporarily ages while waiting for admission. Ordinary fresh native
observation can then admit it within the unchanged five-second receive deadline.
Blocking control work precedes observation. Changed authority, disabled commands
and expired commands remain refusals; submission remains one-shot. No native
lease or timeout was extended.

The preceding .98/.63 live test proved current-group Pro `/come` reception, but
no operation or movement followed. Its error did not distinguish command expiry
from observation expiry; the new source regression proves an admission race,
not the exact elapsed cause of that historical refusal. Track startup separately
failed its direct-pointer guard. See [admission semantics](group-command-admission.md),
[Track lifecycle](track-window-lifecycle.md) and
[the preceding delivery evidence](group-track-delivery-20261010.md).

Delivery documentation is published through [PR #159](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/159)
on `codex/group-admission-delivery-20261010`; documentation merge is pending.

## Exact qualification

| Artifact | SHA-256 |
| --- | --- |
| Acceptance archive | `87af19c949d6cf08317a052803c00791cd6e37bd6c5df443b69cb5244979ec98` |
| Source archive | `01241e6191f0a8d85a3b094b61a04ca1987137e8d0580e72195128111eead1d6` |
| Builder receipt | `4e1e1dca81f2f136f31fc9dfc377a3406bb24de8560826772049a770dafe8c60` |
| Full native DLL | `cdde4e4f88d960f4c125ac42b4078a5db5f1985bd49f9724fe089ef5e933eb59` |
| Host wheel | `45d0662faa9c970a35bda133f876614607802af56944ae69291477884f0ea1d8` |
| Independent verification | `42e3ddc75e443c158e3cb9e129c637812f626e3829d26f4c53f76f783febc2d7` |
| Supplemental verification | `105df082790fa0ce9a40b800c29b5248e3aa6b316fdc8edbc6fea6fbf4aad932` |

All 144 artifact identities, all required gates across 116 recorded stages,
and 491 installed module identities passed verification. The full host suite passed 6,247 tests with 44 optional
skips; the bound qualification suite passed 193 tests with no skips. Full and
diagnostics native profiles passed 261 and 257 tests respectively. Each profile
passed 76 movement, 86 combat and 245 actor IPC cases, including actual group
message/update frames and Track publication. The three standalone native image
cases skipped in each profile have explicit exact-image probe stages.

All four new Track close-binding image stages passed: original and prepared
.17 in each profile, including rejection of altered slot, thunk and body bytes.
Six installed desktop cases and one real worker handshake passed without skips,
with the installed-module/source gates intact. The handshake substitutes gameplay;
it is not live gameplay acceptance. Existing transparency diagnostics remain
explicitly non-gating. Local queue acceptance and copied native observations do
not establish server delivery or successful movement.

## Verified installation and launch

The plan is `927d0e582813a59d07371abce1684982c58b94cdcd4b3f66dc5613119a276e9e`.
Actual receipts are private under `artifacts/bot-deploy/20261010-group64`:

| Receipt | SHA-256 |
| --- | --- |
| Apply | `b2bad609757ad32ed699c91b2fd47607bd536ba3d87a5c3a7375181499b924a8` |
| Activation | `ca17d50f5d83e5d9d64e53c71a0bb1422df1ee392540dd5a8d5dfd4169a4cbe6` |
| Fresh launch | `bedccc008b7e93de368dcf8aa9fd5af3dff52d7ce181439059c99a68955c76cd` |

Activation verified 491 installed modules and 9,627 retained records from the
stopped capture, with zero exclusions and two typed startup/dispatch-permit
changes. The native DLL is the one changed client inventory record; the client
executable and resources were not written. This is receipt-level preservation
verification, without an ancillary retained-manifest export. No fallback copies
were created.

The healthy manager is PID 8352, creation `134361488404740026`, parent 1976,
creation `134361488404456621`; startup generation is
`69928fc1a9324c0994450859d05c71ff`. Activation had no games or workers. The
subsequent reviewed launch created game PID 1868, creation
`134361489104192381`, HWND 8061748, with the exact qualified `cdde4e4f` prefix
DLL loaded. A worker was subsequently observed as healthy PID 3476. These are
startup observations, not proof of in-world command execution or buff completion.

## Superseded local software and remaining work

The reviewed local .63 inventory is
`superseded-b63-local-binaries.json`, SHA
`807c201930d24a65a12a7f3b9337271d1f77b04511085a4616f1001ba17e5a70`.
After independently approved replacement activation and explicit execution
approval, exact retirement removed 2,893 reproducible files totaling 208,857,922
bytes from `artifacts/b63/bfe2b99f`. All 6,575 nonlisted files retained their exact
hashes and sizes. No directories, VM files or replacement package files were
touched. Source archives, source, logs, XML, receipts and diagnostic evidence remain.

The local retirement receipt `superseded-b63-local-retirement.json` is
`ba44ab49376deefa0d8bcda07141d6dfafd08f0e865428a6ca71e452cdd2f296`.
Its preserved-file identity manifest is
`bae84a13a97cd8d7b93b6e71f08ca040159b58a1ab198d58abb8b989280a5154`.
A historical baseline test depended on the removed wheel; a later rerun must
rebuild published `a6a217fb315cd6c7005d84539715467818564503`.
Guest retirement is separately complete. Receipt `retirement.json`, SHA
`d0ab516377332cea1f2b1ffdf5d840922c9715b1cf98f4758b3ad8c63d777369`,
records removal of the obsolete .98 host, its ten payload wheels and staged .63
DLL: 12 exact paths totaling 59,442,143 bytes. User data and diagnostic evidence
were preserved. Postcheck `post-retirement.json`, SHA
`d70e5f4fe57a92320d3638a9ef3ee3b0f3528a62cd7bf3da38f736c312fc2d67`,
confirmed all targets absent with the same manager 8352, game 1868 creation/window
and qualified .64 DLL. There was one healthy worker and no active/queued operation.
The character was unavailable at that read and buff state was `needs_attention`;
this does not establish login, successful Track startup or current buff upkeep.

Next: confirm login/group readiness and record fresh user-authorized command
and Track presentation results.
The old `/come` must not replay. Successful movement, automatic hiding/manual
preservation, and all-buffs-present remain unverified in this delivery record.
