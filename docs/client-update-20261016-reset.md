# Official reset patch 1.3.38.23

The official feed changed after the earlier .22 check. The fresh manifest is
`e89417ae7dbc375dd7017493ffa554023880fa84b9669a9a308d258c5806664b` and
changes the executable plus 13 skin archives (80,736,874 bytes total). All changed
assets have been downloaded and hash-verified; no .23 installation is claimed yet.

Original executable SHA-256:
`7e497f9381bc35ca350dfb9ecc85ee6b1eaf9e1f1a7678724b9cb8c926be7636`.
Prepared executable SHA-256:
`4bf1a24a268d0ed13227d766105f3595cdc264e930436ca08748a10b04293ffa`.
The same seven reviewed bootstrap writes produce that exact prepared identity.
The source candidate is host .123/native .76, preserving strict original versus
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

Next: commit the reviewed source, compose the existing graphics release with the
six-worker launcher and combat-text compiler, run full package/IPC/startup gates,
update the separate official client and install the qualified Vendor Test runtime.
Maximum graphics, working Mesa text settings, the installed translation candidate,
saved settings and vendor journals must be preserved. The six-worker FPS and
combat numeric/newline acceptance remain pending. No retained rollback copies.
