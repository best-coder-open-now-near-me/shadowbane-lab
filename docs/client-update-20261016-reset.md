# Official reset patch 1.3.38.23

The official feed changed after the earlier .22 check. The fresh manifest is
`e89417ae7dbc375dd7017493ffa554023880fa84b9669a9a308d258c5806664b` and
changes the executable plus 13 skin archives (80,736,874 bytes total). All changed
assets have been downloaded, hash-verified and installed in the separate official
client. Its 230 other files were preserved. Vendor Test is also aligned to .23
with qualified host .123/native .76 and has relaunched through its original shortcut.

Original executable SHA-256:
`7e497f9381bc35ca350dfb9ecc85ee6b1eaf9e1f1a7678724b9cb8c926be7636`.
Prepared executable SHA-256:
`4bf1a24a268d0ed13227d766105f3595cdc264e930436ca08748a10b04293ffa`.
The same seven reviewed bootstrap writes produce that exact prepared identity.
The installed release is host .123/native .76, preserving strict original versus
prepared admission and denial of unknown images.

The .22/.23 comparison changes 652 bytes across 48 ranges in .text, .data and
.wbtm. PE layout and all 149 audited native hash spans are unchanged. The new
shared-dispatch wrapper handles title actions 0x12f2 through 0x1311 and forwards
ordinary actions to the prior .wbtm dispatcher. The actual owned-image fixture
executes that ordinary branch, including both title-range neighbors, without
calling real UI/network handlers.

The .23 title menu writes a four-byte row counter at .wbtm offset 0xc20. The
loaded-image verifier permits those four bytes only when the whole original or
exactly reconstructed prepared file has the reviewed .23 hash. Older images keep
that counter sealed. Counter neighbors, dispatcher code and the remaining added
sections still have to match the exact authenticated file.

Focused host checks pass 1,166 tests with one optional skip. The native image
fixture compiles and passes against both actual .22 and .23 original/prepared
pairs, including counter-profile selection, loaded-code mutation rejection,
owned terrain normalization and the real shared-dispatch default branch.

The final source includes the exact .23 recycling fixture and registers the
required .23 actor-effects case. The complete source/gate inventory was checked
before the final rebuild. Graphics-preserving release
`7dc7678f64cf0b0fa2e6c83c23df475859a8c7da` on
`codex/vendor-release-20261013` composes the six-worker launcher and combat-text
compiler with the reviewed vendor changes. It is pushed, remains outside main,
and is the exact installed source; focused vendor delivery remains draft PR #174.

Full qualification passed 7,052 host tests with 46 environment skips, 303 full
native cases and 299 diagnostic-profile native cases. Each profile also passed
107 movement, 86 combat and 253 actor IPC cases and its actual-client probes.
Independent verification checks 151 artifacts and 121 stages; all 212 bound
verifier regressions, seven startup cases and 135 installer regressions pass.
The two historical transparency diagnostics remain recorded per profile.

| Artifact | SHA-256 |
| --- | --- |
| Full extension | `ce14779d42880dc2e4b0c6c7efc38744613de467b7111a4215dbb9b2fe0466cd` |
| Host wheel | `614e63b9428f8ac624dc5736af5f8d6b81be15c579bc21f47ade4184cdfd022d` |
| Qualified package | `7548ae04e303cbcdd8e998c96f3699db0884bab4614ec87f2904449d52894546` |

All 508 installed modules and 10,207 retained records verify with zero exclusions.
The new client lifetime loads the exact extension and has a healthy worker with
no active or queued operation. The update changes only the executable, extension
and 13 official skin archives in the immutable client inventory. Maximum graphics,
Mesa text settings, the installed nine-value translation candidate, saved settings
and vendor journals are preserved. No historical vendor action was replayed and
no deployment rollback copy was made.

The fresh process verifies `LP_NUM_THREADS=6` with the working Mesa software-text
environment. Obsolete .122 guest/local software was retired after the verified
new launch. Failed candidate builds were also removed; source, settings, logs and
compact version/hash receipts remain. All 15 hosted checks passed at focused code head
`cd9b7c2d` before this installation-documentation checkpoint.

Next: the in-world six-worker FPS sample and combat numeric/newline acceptance.
Then resume a fresh quantity-ten vendor batch, live eligible recycling acceptance
and town scheduling. Guards remain outside scope.
