# Coordinate travel qualification and installation

## Source and behavior

PR [#167](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/167)
merged at `a7247a364a81ddab45006ae40cd37d33dac5ddff` after all 15 hosted checks
passed at `011c3b8dbc56fcfb3e7db3bbccd6a235e3d75292`. Its included follower
PR #166 is also merged. The shared checkout is clean on `main`.

The update keeps the accepted `/go lat long` planner and learned obstacle
recovery. It replenishes short destinations from observed progress and preserves
a coordinate travel operation across a verified parent-only native transition.
Native cleanup and a correlated successor receipt precede more movement.
Cancellation dominates continuation. Unsubmitted waypoint proposals do not consume
attempts or teach false obstacles; actual observed passage remains recorded.
Host .103 requires native .66 for this coordinate capability. Combat/PvE mixed
ownership retains its existing policy. See [implementation boundaries](continuous-group-travel.md).

Exact release `dc6cbbb4c00f001744c16de8936095b313bf46ad`, pushed on
`codex/native-group-command-release-20261010`, combines the reviewed source with
the installed graphics composition from `c89941f2`. Independent composition
review verified unchanged graphics/assets and all six .103/.66 version markers.

## Qualification

The private package is `artifacts/b66/8779eef5`. Qualification passed the full
host suite (6,387 passed, 44 optional skips), all required gates across 116
package stages, 194 verifier contract tests without skips, and seven supplemental
startup handshakes.
The full and diagnostics profiles passed 275 and 271 native cases respectively;
their required native sets contain 161 and 157 cases. Both profiles passed 107
movement, 86 combat and 245 actor IPC cases without skips, including the new
real coordinate-parent transaction. The three generic native image cases are
superseded by the exact original/prepared client binding stages. All four Track
image proofs and the group-frame readers were checked. The two previously
recorded graphics transparency diagnostics remain deferred in each profile;
no new waiver was introduced.

Independent review verified all 144 receipt artifacts, 148 archive members,
1,563 archived source files, and all 491 source/wheel/installed module bytes.
The startup checks use test-owned processes and do not establish live gameplay
acceptance.

| Receipt | SHA-256 |
| --- | --- |
| Acceptance archive | `4cf7f2cbdd3257099fbcdf7c6d52bc0e457fdbf20935be907a725c4b6f1385dc` |
| Package receipt | `2a494a767333a2756b957da124dd1cf70742f678bdbd525376dd45670d534541` |
| Full native DLL | `9451ea36b4069dec028f1469ea5084aa1a0b9a443b3e72c10dce06020c533d01` |
| Host wheel | `5efbff97659a03c527f0216abd39e6d643410f37295495c3fc31ae24e7f57406` |
| Independent package verification | `d8038a50a870d9d658659bdb71ca7bfbd7bbce8cc52e329024524c89f0684efa` |
| Supplemental startup verification | `abae552b834b7bc7590c086820a7c7d75d1bc48d365eb59a7f63427cf784d869` |

## Installed runtime

The user closed the clients and restarted the VM. A fresh closed baseline
`5ff920963b0fbf2ca85c760634ad7ac923071e623cf0c7ac82308a684944a8f8`
verified no client, manager or worker. The reviewed already-absent manager path
performed fresh dependency checks without restarting or killing old software.
The resealed plan is
`54550753d77f5b13bf4e868e244b75265cb87f61871452e14c95a5090a808b56`.

Host .103/native .66 is installed from exact release `dc6cbbb4`.
Independent phase review verified 491 modules, 9,686 retained records, zero
exclusions, exactly one DLL replacement and two typed startup/permit changes.
The official client executable and resources are unchanged. No rollback copies
were created. Private receipts remain under
`artifacts/bot-deploy/20261011-host103`:

| Phase | SHA-256 |
| --- | --- |
| Manager stopped/verified absent | `bbb0165c7ea6d1889d505dbb65f3d25cc4bbd5e4f31abb77a36dffbb2689b204` |
| Apply | `3f08bf7db0d3e40f27bc0c9543d11714dc2b26c22fc544fb1fe66066b2c88927` |
| Shortcuts | `b7606ddbf29a0545baf675010b8fac6d2083ec872875c95590747356ffe0f8e9` |
| Activation | `fbd9adfca6253fbd91008d0d55bb8b3c83a2bf9fb85bd007e650d8aa4847561b` |
| Client launch | `a8bdfefb729fb4344f5b3c93e828d211412dc4b40937b15d156a96dfd33dee5c` |

The reviewed launcher opened client 5640, lifetime 134362122977715513,
window 196970, with the exact .66 DLL. Manager 4756 and worker 5544 are healthy.
At the post-launch check, character identity is unavailable at login; the worker
is healthy with no active or queued operation, and automatic buffs are paused. This verifies launch, not live
movement acceptance. No previous command was replayed.

## Obsolete software retirement

After verified activation and launch, exact reviewed inventories were retired.
Local receipt `807ca134e14ef108ff876782e4fe92944baf3652c794752cff008401f73a6331`
records 4,753 obsolete files removed (244,995,781 bytes), with all 9,220 nonlisted
files unchanged. The current B66 package and VM were outside that local scope.
Guest receipt `689e3c7df96ea6f04f19236edc6fffc3900a1d649183dec08ab25274632fcbe0`
records 22 obsolete .102/.65 targets removed (68,620,488 bytes). Final postcheck
`aadf389b207d7728c69a48285be5add04f208ff32645a0ec96b420c286cdaf70`
verifies the same current manager, client lifetime/window and exact .66 DLL.
User data, source and diagnostic evidence were preserved; no rollback copies
were retained. At that check the worker is healthy with no active/queued action;
character identity remains unavailable at login and upkeep is `needs_attention`.
Fresh in-world readiness is still required before claiming automatic upkeep.

## Remaining work

- Complete: source integration, package qualification, installation, verified launch
  and obsolete software retirement.
- Active: request fresh login/group readiness, then one new grouped `/come` to
  check sustained movement, endpoint pacing and existing obstacle recovery.
- Next: record the live outcome; preserve all user data and diagnostic evidence.

The prior retained trace proves a parent interruption and slow endpoint pacing.
The reported building obstruction remains a live acceptance question; successful
obstacle avoidance is not inferred from source or package tests.
