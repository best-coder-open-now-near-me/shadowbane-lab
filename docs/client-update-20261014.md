# Official client alignment for vendor rolling - October 14

## Qualified and installed

Host .112/native .70/client .19 is installed from graphics-preserving release
`a7f0b65d8b9d9930a505face3b45ac660a4fcc53`, pushed on
`codex/vendor-release-20261013`. Implementation is pushed through
`1d8a539b0526db0e9d3950fb625db426e8f549b3` on
`codex/vendor-rolling-20261013`, targeting main in draft PR #174. Main remains
clean; neither current vendor lane is merged there yet.

Full qualification passes 6,760 host tests (45 optional skips), 289 full-profile
and 285 diagnostics native tests, both sets of movement/combat/actor IPC
(107/86/249 cases), exact original/prepared image probes and all seven real
Windows startup/stop cases. Independent verification seals 144 artifacts,
116 steps and 499 wheel modules. The adapted full-client updater passes 153
preservation/refusal checks. The prior two stretch-only transparency findings
remain recorded per profile; no required gate was waived.

A fresh closed baseline captured 9,836 retained records. Apply replaced exactly
the four reviewed official files plus the DLL. Activation verified all 499
installed modules and 9,893 retained records with zero exclusions; only typed
manager startup/dispatch changes were accepted. Settings, mutable DoubleFusion
files and historical roll journals remain in place. No funds, Create, Keep or
disposal were sent during installation. Unused installed host .111 was retired:
2,189 reproducible files / 49,479,921 bytes, with no retained rollback copy.

The unchanged Vendor Test shortcut launched PID 2664 / creation
134364516441118144 with the exact .70 DLL. Its V2 production mapping is available,
sequence zero with no rejection or loss, and its exact worker is healthy with
an empty operation queue. Treehugger subsequently logged in and moved. Fresh
discovery `operation-daf94aea982743ed9f75e29de1eca6b8` failed during its three
read-only city inspections, before any OPEN, funding or crafting request.
Its review record is preserved. Late-reply inspection proves the IPC worker
processed all three requests and returned expired client inspections; there is
no unconsumed OPEN to replay. The command worker itself is running. The lifetime
initializer passes former SizeOfImage `0x1766000` to an import reader requiring
exact header equality. That fails initialization, retires the movement runtime
and leaves vendor requests without their game-side update callback. Separately,
`IsReviewedWorldMapClient` still requires six sections and disables map capture.
Passing image/hash probes and a readable V2 mapping did not cover these startup
consumers.

Source .113/.71 now publishes the authenticated file's image size and section
count only after matching the loaded PE header and all existing code proofs.
Lifetime import binding uses that size. The world-map gate accepts the exact
seven-section shape only with that authenticated proof and the exact read-only
`.wbfp` header. Legacy layouts retain their earlier admission. Unknown images,
altered headers and other section shapes remain rejected. Forty-four native
layout/lifetime cases and the actual original/prepared movement probe pass. The
real-image probe exercises both startup-layout admission and the free import
binding, proves the former constant fails on .19 and rejects loaded-header drift
with all proof outputs cleared. The new layout test is a mandatory package gate.
Active next: qualify/install .113/.71, then resume fresh discovery and the complete
quantity-ten inventory chain. Installed software remains .112/.70 for now.

Exact SHA-256 receipts:

- DLL: `5d67b58f47030012aa04264765ac6306a03f9758688c698f0204061052f85af3`.
- Wheel: `903e2567bafe94a1c69ad8ff6ff2172f430f7083e47885680ee229d620382b52`.
- Package: `81e14987193f27b15755fa3d0da6f1d72e1d83fa2cba7fb141b09c4a328ed9bc`.
- Package verification: `44c12a14cf7a484ce9023c76fd5c56c04bd936f3702515331bfb7fc26372bc60`.
- Startup qualification: `8b8200c1c5f005268e18505ee2b6b3e6a71562e9748729172e52a2c1f6d03f4c`.
- Update plan: `b3962a6757be527f85dfba5385d7975859a62789cf2899d934e8d0ac2b1d8010`.
- Apply: `8b9e4a55fe27ebfe31d70d759803fc76d3ac0702afc601659a9c01e3fa8a303b`.
- Activation: `a99203f1590ce5029eb8ff4e81d3c9bdcd1510f30cf2dc21a1c980fe729abeab`.

## Alignment review and earlier state

The user patched the official client and requested alignment before continuing
quantity-ten rolling. The official patch manifest reports gameVersion `1.0.25`;
the exact executable contains version string `1.3.38.19`. Treat the hashes as the
authority rather than equating those independently maintained version labels.

| Image | SHA-256 |
| --- | --- |
| Official, 21,315,584 bytes | `2cc8f6cfc157b4b2c0f2abbc30d1b5df81daaee24363a8da884cb8a45dc3489a` |
| Prepared, same length | `6bd0e391edc1c773b4c96d8a9801db45f96db9e34202afcfc8d383d4971fe5ad` |

The image adds a seventh read-only `.wbfp` section at RVA `0x1766000` and grows
SizeOfImage to `0x178f000`. The six existing section layouts, image base, entry
point and import layout remain unchanged. Compared with official .18, 174,197
bytes differ in 88 ranges, predominantly the added data section. Existing text
changes redirect three sites at RVAs `0x4c678c`, `0x4c698b`, `0x55c09e` into
new position/attachment handling in the existing text area; another redirect
and nearby code update retain the ordinary continuation. The new routines read
the added section as a bounded sorted table. This is a structural update, not a
version-string-only change or a claim of equivalent gameplay behavior.

Static comparison against the vendor source finds all 149 pinned native spans,
51 calibrated anchors and seven explicitly reviewed tracking/group boundaries
unchanged. Of 3,190 conservative native literal windows, the six changed entries
all name the former image-size boundary `0x1766000`, now the new section start;
they are bounds/constants, not relocated hook addresses. Their existing bounded
import reads remain within the unchanged original sections. No reviewed vendor,
production reply, inventory or funding hook moved. The seven loader writes
resolve exactly in unchanged header/text/import locations, reproduce the prepared
hash above and preserve every other byte, including `.wbfp`.

Host .112/native .70 extends exact original/prepared identities and the bootstrap
source length. Native mutation paths continue to reject original and unknown
images; observation-family membership does not grant command authority. Cost
reading explicitly admits the new prepared image so whole-batch funding can
continue. The V2 production recorder uses the same verified spans and message
layout. Client .19 does not inherit disposal qualification; unknown affixes and
the earlier interrupted one-item job remain preserved.

Focused validation passes 358 host checks (one optional skip), ten native
allow/deny, scene and production cases, Ruff and whitespace checks. One initial
host test hit the sandbox temporary-directory restriction and passed with the
task-owned temp directory. An initial native invocation named a nonexistent
scene target; the correct target was built and all requested cases then passed.
Private images, comparison reports, disassembly and captures remain local.

A read-only 211-file asset census verifies all four changed official files:
`sb.exe`, `Config/Config.wpak`, `cache/Visual.cache`, `cache/CObjects.cache`.
The runtime's three resource files still match .18. The two DoubleFusion user
files are runtime-written and remain in place. The qualified .112/.70/client .19
installation is recorded above. No vendor action was dispatched during alignment.

The [no-retained-rollback policy](deployment-policy.md) applies. Next: finish
fresh discovery and one whole funded quantity-ten batch. Draft PR #174 targets
main; this alignment stays on the active vendor lane.
