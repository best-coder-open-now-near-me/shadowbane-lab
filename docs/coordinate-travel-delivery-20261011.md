# Coordinate travel qualification and pending installation

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

## Current runtime and installation boundary

The testing VM remains on host .102/native .65. Fresh read-only baseline
`76ffb19604dc715c258703ea483b62de86ad7407d702096c222c02f45325cdeb`
verifies the installed .102 source and 491 modules, unchanged .17 client/resources,
and 9,636 retained records. Four live writers were recorded as unstable without
preservation exemptions; a fresh stopped capture still governs installation.
Umbra's worker is healthy with no active or queued operation. Both the visible
client and an older windowless copy map the exact DLL to replace. The user has
been asked whether to close both or have this task close them. That response is
pending; no guest staging, process control, or runtime replacement has occurred.

The local concrete payload is prepared under
`artifacts/bot-deploy/20261011-host103/payload` with plan SHA-256
`ab7c2ee9c762cbd3349577f171cdeec1973d71a3958cde6b1887eae650cd5e3f`.
Independent package/payload member review passed. This candidate plan is bound
to the active baseline; after client closure, capture a fresh closed baseline and
reseal the plan and wrappers before preparation. The activation validator compares
exact client bindings and must not be weakened to reuse an active-world baseline.
Its procedure preserves settings, jobs, history
and typed stop-control records, uses the corrected filtered-slot activation
validator, and replaces exactly one DLL with associated provenance. It follows
[the no-retained-rollback policy](deployment-policy.md); runtime recovery uses
committed source and official client assets.

## Remaining work

- Complete: source reviews, exact package qualification and source integration.
- Active: after actual DLL users close, capture the closed baseline, reseal and
  review the concrete plan, then install.
- Next: start the verified runtime and request one fresh grouped `/come` to check
  sustained movement, endpoint pacing and the existing obstacle recovery.
- Next: record live outcome and retire verified obsolete reproducible software;
  preserve all user data and diagnostic evidence.

The prior retained trace proves a parent interruption and slow endpoint pacing.
The reported building obstruction remains a live acceptance question; successful
obstacle avoidance is not inferred from source or package tests.
