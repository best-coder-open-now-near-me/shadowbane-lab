# Official client .18 alignment for vendor rolling - October 13

Branch: codex/vendor-rolling-20261013, based on refreshed main 420deb91.
Integration destination: reviewed main. Guard work is no longer active.
The current task resumes vendor rolling for Treehugger in Rooty on the test VM.

## Installed and launched

PR #172 merged as `ed138274d2ba4e4f515a10e92e64540a499eba72` after all 15
hosted checks passed at `f4913f22c2ec99073bc2bcb1de7b1c1258079999`.
The graphics-preserving release on `codex/vendor-release-20261013` is
`68163f32139cc1923a37a4763521d5c7990229e7`; its existing graphics composition
remains outside main. The normal checkout is clean on the merged main.

Host 0.3.105/native 1.8.67 and client 1.3.38.18 are installed in the existing
test VM runtime. The original Vendor Test shortcut launched client 1888 with
window 2359496 and the exact qualified DLL. The manager and bound worker are
healthy, with no active or queued operation. Login and vendor acceptance remain
pending; startup success does not qualify crafting or disposal.

The final package passed 6,408 host tests (45 optional skips), both required native
profiles and actual-image/IPC checks. Independent verification checked 144
artifacts and 116 stages. Seven supplemental desktop/worker startup cases passed
without skips. The installation helpers passed 119 focused regressions; the
final preservation guard change passed all 10 affected installer cases.

Installation verified all 491 host modules, eight changed client inventory rows
(seven official assets plus the extension), and 9,718 retained records with zero
exclusions. The original 9,666-record baseline was rechecked before replacement;
the expanded snapshot also covers settings and historical launch receipts.
Only typed launch provenance, manager startup and dispatch-permit changes were
accepted. Existing settings, recipes and journals remain in place; no historical
Create or Keep was replayed. No deployment rollback copies were created.

| Private receipt | SHA-256 |
| --- | --- |
| Package archive | 86dc5befdc05e5219f471aecd014b479887ac6ed53cc71bd8e7654f778f976a0 |
| Independent package verification | 65eb63d4190b48ffdca49707d29289e174d36d3faf6bfca4e3f42b6e632849ef |
| Installed DLL | eaaec4f6d80ce1ec8c7e0195466a3e0095708985a8cfe95cd84c3e2262eedcb7 |
| Apply | 92a4b558c2645419f187e5f13e7744dee4be8dc235d9a63fa23fd5b58d5f8d3f |
| Activation | 17a291c0c287e12a1c209e37a62f6a29b3369c23fec4b005d7db7ca3be0e0670 |
| Launch/status | ff2139cdc1f536dd8a0315fc7d92ea70c1c454fcc813d0aa802254cb891e3296 |

Next: log Treehugger into Rooty, qualify saved recipe selection and one batch
using the currently observed free slots, then continue durable town scheduling.
The user policy remains exclude confirmed Tier 1/2 and keep unknowns; destructive
affix qualification remains a separate gate.

The investigation notes below record earlier states and are historical.

## Startup failure and exact identities

The Modded Client, Inspector/TextFix and Vendor Test shortcuts all use the same
reviewed launcher. Installed host 0.3.104, native 1.8.66 and prepared client .17
still match their recorded identities. The official client has updated to .18;
the launcher correctly stops before starting the game because its official
baseline no longer matches. No game, manager or worker was active at inspection.
No client files, settings, saved recipes or job journals have been replaced yet.

| Image/evidence | SHA-256 |
| --- | --- |
| Official .18 | 28a745925fceb4e3f08537504a7192782afe2227758e34febdd95cc4539f8db0 |
| Prepared .18, independently reconstructed | 366ea471a47bf6f6cdc1da91ea415f5b202d307e4ec6e8272b349f39e63d142a |
| Official patch manifest | 73edc233c7a24f70bc968f106d5711788128884d30f7af49eb64c79705c4ad9a |

The executable remains 21,143,613 bytes. Comparison with reviewed .17 found 1,434
changed bytes in five ranges: a redirected code branch, a removed conditional
branch, new code and constants in previously unused text space, and the version
string. The redirect returns to the original continuation; new code handles
position/vector state and its retained timing records. Static control-flow review
found no overlap with the seven bootstrap writes or reviewed extension spans.
This is not evidence that all gameplay behavior is unchanged.

All 16 production profiles / 51 calibrated anchors, 149 literal hashed native spans
and 3,115 native address-literal windows remain unchanged at current main.
PE headers and section layouts match. The seven independent bootstrap writes
reproduce the exact prepared image. Exact original/prepared guards are extended
for this pair only; strict mutation readers still reject original and unknown
images. No offsets, signature checks or uncertain-request barriers are relaxed.

The manifest changes seven official assets: sb.exe, Config/Config.wpak and
cache/{Mesh,Textures,Visual,Render,CObjects}. An actual official/runtime census
must verify their identities and distinguish user/runtime-written drift before
installation. The no-retained-rollback deployment policy applies; rebuild from
committed source and official assets, preserving non-reproducible data in place.

## Validation and next steps

Host0.3.105/native 1.8.67 are the matching source candidate. The focused host suite
passed 329 tests with one optional skip; Ruff passed. Full Release Win32 compilation and nine focused native cases passed, including
prepared.18 admission, original.18 rejection and vendor menus. Actual-image
probes, full package qualification and installation remain pending.
The first test run hit an inaccessible sandbox temporary directory; rerunning
with the task's own temporary directory passed. No product behavior changed
in response to that environment failure.

Next: finish native checks and commit this source checkpoint; compose the package
with the already-installed graphics source, run required package gates and apply
the exact update against a fresh idle baseline. Verify the original Modded Client
shortcut launches and loads the expected extension. Then qualify saved recipe
selection and one available-capacity vendor batch before town scheduling.

The vendor policy remains exclude confirmed Tier 1/2, keep unknowns. A newly
reviewed executable does not inherit destructive affix qualification. Preserve
all unresolved historical Create/Keep records and perform no automatic replay.
Private executables, disassembly, manifests and startup logs stay under the local
artifacts/vendor-resume/20261013 evidence directory; no fallback runtime is created.


## Validation follow-up

The graphics-preserving composition passed 6,407 host tests with 45 optional
skips. Its real Track binding probe then rejected the new image at a test-only
identity list. That list is now extended for the exact pair; both original and
prepared real-image probes pass all four binding cases, without executing client
code. Fresh package qualification is required for the corrected source.

One hosted Python 3.13 run exposed an existing timing-sensitive renewal assertion.
It incorrectly required a replacement permit to be issued after the original
permit's expiry. A permit issued at 101.5 and expiring at 103.5 is valid at 102.35,
even though the original expired at 102. The regression now proves that current
time exceeds the original expiry, a fresh permit was actually observed and that
permit remains unexpired. A deterministic boundary test also verifies rejection
at the replacement's exact expiry. No production renewal code or TTL changed.

The official patch is now complete. Its existing 1,773,064,878-byte texture part
matched the current manifest and was atomically committed in place, freeing its
old destination's space. Four smaller official assets were downloaded and hash
verified. Runtime-written DoubleFusion files were preserved. The modded runtime
still awaits the matching qualified software and resource update.
