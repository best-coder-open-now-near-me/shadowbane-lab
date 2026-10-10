# Group receive and Track presentation delivery - October 10, 2026

## Source and integration

PR #157 merged as `30f7b87a878cfbee1ef5b746182174e9e3df02cd` after all
15 hosted checks passed at `52349b2bdcbe09fb8a446c9101d097ea001868b1`.
It contains the reviewed GroupChannelMessage receiver and automatic Hunt Foe
panel lifecycle. Development starts from refreshed main.

The exact host 0.3.98/native 1.8.63 release is
`a6a217fb315cd6c7005d84539715467818564503`, pushed on
`codex/native-group-command-release-20261010` in `bot-integration`. It preserves
the previously installed graphics source outside main. The source branches
`codex/group-chat-receive-20261010` and `codex/track-window-lifecycle-20261010`
are included in main. Follow-up work uses the focused repair branches described
below; use refreshed main for unrelated development.

## Qualification

The local package is `artifacts/b63/bfe2b99f`. All required package stages passed:
6,213 host tests (43 optional skips), both native profiles, required IPC and exact
client-image probes, and installed-wheel checks. Independent verification checked
140 artifacts, 491 module identities and 112 recorded stages. All 158 qualifier
tests and seven supplemental desktop/worker handshake cases passed with no skips.
The existing transparency stretch diagnostics remain explicitly non-gating.

| Identity | SHA-256 |
| --- | --- |
| Acceptance archive | `5335c1abe2e1257b7b9257bc58759d523649a519eb48bb1b9e1d2c3b48a182f5` |
| Builder receipt | `8777e74af6d2b0a5666a090ecff44f2c0af80350d32b62ea45754b29e273be94` |
| Independent verification | `17d26487adf68782a43004430abc74ec31b940df35267ee5456a5683b117ebfb` |
| Supplemental verification | `bc4045e3134b9cc226776e8100cac514503f53a1d73eb5ce77422069a0046a42` |
| Native DLL | `bcb59311d0dc98ba52b3686ac04e77b2a19f4ccf206fea559ba14a56c0be44ca` |
| Host wheel | `f7a9b140592bedd7dd7809c36efd4707104043062778a05de53d50221c17ab04` |

The first package attempt caught one stale public API version constant. It was
corrected before this release and all six version surfaces agree. The failed
attempt's reproducible source snapshot/archive were removed; its failure log and
compact retirement receipt remain under `artifacts/b63/758003cd`.

## Deployment record

Private evidence is under `artifacts/bot-deploy/20261010-group63`.
The reviewed 26-member payload plan is
`ae0ab19e4bdcde1f7edf18b3fa9a6eb61fad2461e6143132adb8903cf80c52ba`.
Preparation succeeded with receipt
`79d61678ea72268fd2ced5c77c4edb24f99c31737dae35c818c5685741b7d7ad`.
The user closed Vendor Test and the fresh closed baseline
`91ce10e74638bde48354ad2e2e4426676ea41215d07fd0d925ab5ed15bb93d94`
confirms no game, no bound manager client, and the original 491 installed modules.
The 9,573 user records remain present. The stopped capture, not allowances from
live-generated rows, is the preservation authority for replacement.

Installation, activation and reviewed launch passed independent verification.
The new game is PID 3176, creation 134361470067943785, window 2294660, with the
qualified DLL loaded. Manager 5012 and worker 2276 were healthy at that launch
boundary; later automatic upkeep required attention as recorded below. The stopped
preservation capture accounts for 9,617 retained files with zero exclusions;
activation changed only the two typed startup/permit records. The client
executable and resources were not changed. Preservation validation here is
receipt-level; no ancillary retained-file metadata export was performed.

| Receipt | SHA-256 |
| --- | --- |
| manager-stopped.json | `b612446863c4b30ed56b236d04f3dc970bd48c8b428381f0f8999cfc87999cd3` |
| apply.json | `16231de7085697c29bf926303cd00249d7fe3cb71436c3e6bf97e711ae921d15` |
| shortcuts.json | `cc64a69d3d64069fd9d44e6351aaf1af7922947a03a9b8d4014a461f0125d17e` |
| activation.json | `7bc9beabe8c1c300bdbbd03e21da5810cf2ea92e91af854f95acb748c42aacee` |
| launch-receipt-3176.json | `c9d5053e4cda59aa82b52b778db3dbf3b47c2bf0c49e9f24c679610afa36601f` |
| post-launch-status.json | `941a5b1bfd905bcbd46f8f376ca95365269b1f8d0fab63100db593f055d0c0df` |
| delivery-index.json | `9d6edddbbb4c81a74cda346927846b910307193dba16932658d0f4951aa0067e` |

Existing character settings,
including enabled group commands, remain in place. No deployment rollback copies
or archives are created; superseded reproducible runtime output is retired only
after the replacement is verified, preserving diagnostic evidence and user data.

## Verified retirement

The guest's obsolete .97 host, ten package wheels and staged .62 DLL were
removed: 12 exact paths, 59,436,000 bytes. The postcheck retained game 3176,
manager 5012 and the new DLL identity. User data and diagnostic evidence remain.
Local .62 build retirement removed exactly 2,891 listed files (208,615,502 bytes)
under `artifacts/b62/d2ac79a9`; all 6,570 nonlisted files were verified unchanged.
Source archives, extracted source, logs, XML and receipts remain. The active .63
package was untouched. Rerunning the historical baseline wheel test now requires
rebuilding published source `182077fd`; no fallback wheel was retained.

| Receipt | SHA-256 |
| --- | --- |
| retirement.json | `2430e373ed0facfdc75e586b1035061fc0583b8f59e7e0e5dda3a05f20398ccd` |
| post-retirement.json | `6fc56e6e40a950a804e4f63e20a62f80626d2c576e298af8c0574e6461514a46` |
| superseded-b62-local-retirement.json | `1eb6f2c8c0e7f69ad262dd02e0047e8a985e7dc2955d52776d841c59932dcbb0` |

## Live results and remaining repairs

The .97/.62 attempt was a confirmed receive failure: Pro's `/come` appeared in
Umbra's group chat while the legacy observer recorded no messages. After the
.98/.63 installation, Umbra logged in and grouped. A fresh Pro `/come` produced
native Decode/Process-entry/Process-return sequences 1/2/3 with current-group
sender attribution and no gap, rejection or drop. Native reception is proven.
The host withheld it because group evidence expired before admission. No
operation, movement grant or movement followed, and the consumed command was not
replayed. `listener-ready/come-attempt-index.json` has SHA-256
`5b8fff6e652704ebde0a7fef4669c5dd59def0aaa94e27db289f954f3a69549a`.
The separately captured timing sample is diagnostic evidence, not proof that a
particular scan delay caused that command's expiry.

Automatic upkeep separately reported `NativeActionChannelUnavailable: native
tracking query is unavailable` and `needs_attention`. No Track HUD was present;
that is not successful scan or hide acceptance. Exact-image reproduction found
that the new presentation guard expected a direct close-function pointer, but
native slot `116fb58+10c` contains thunk `17440`, which jumps to `5f4e70`.
This mismatch prevented tracking publication startup. Reviewed fix `e8e3c042`
on `codex/track-close-binding-20261010` checks the actual slot/thunk/body and
retains the existing lifecycle policy. Both profiles pass actual original and
prepared .17 binding tests, and those four package stages are now mandatory.
The fix is published source, not part of the installed .98/.63 runtime.

The companion host admission repair is on
`codex/group-command-admission-20261010`. The planned combined .99/.64 release
must be reviewed, qualified and installed before a fresh `/come` can demonstrate
admission and travel. Automatic Hunt Foe contact capture/panel closure, manual
Track preservation, and the pending camp/PvE acceptance remain unverified live.
Do not replay prior consumed commands or claim movement from receive evidence.
