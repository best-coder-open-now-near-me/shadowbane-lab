# Official client .18 alignment for vendor rolling - October 13

Branch: codex/vendor-rolling-20261013, based on refreshed main420deb91.
Integration destination: reviewed main. Guard work is no longer active.
The current task resumes vendor rolling for Treehugger in Rooty on the test VM.

## Startup failure and exact identities

The Modded Client, Inspector/TextFix and Vendor Test shortcuts all use the same
reviewed launcher. Installed host0.3.104, native1.8.66 and prepared client.17
still match their recorded identities. The official client has updated to.18;
the launcher correctly stops before starting the game because its official
baseline no longer matches. No game, manager or worker was active at inspection.
No client files, settings, saved recipes or job journals have been replaced yet.

| Image/evidence | SHA-256 |
| --- | --- |
| Official .18 | 28a745925fceb4e3f08537504a7192782afe2227758e34febdd95cc4539f8db0 |
| Prepared .18, independently reconstructed | 366ea471a47bf6f6cdc1da91ea415f5b202d307e4ec6e8272b349f39e63d142a |
| Official patch manifest | 73edc233c7a24f70bc968f106d5711788128884d30f7af49eb64c79705c4ad9a |

The executable remains21,143,613 bytes. Comparison with reviewed.17 found1,434
changed bytes in five ranges: a redirected code branch, a removed conditional
branch, new code and constants in previously unused text space, and the version
string. The redirect returns to the original continuation; new code handles
position/vector state and its retained timing records. Static control-flow review
found no overlap with the seven bootstrap writes or reviewed extension spans.
This is not evidence that all gameplay behavior is unchanged.

All16 production profiles/51 calibrated anchors,149 literal hashed native spans
and3,115 native address-literal windows remain unchanged at current main.
PE headers and section layouts match. The seven independent bootstrap writes
reproduce the exact prepared image. Exact original/prepared guards are extended
for this pair only; strict mutation readers still reject original and unknown
images. No offsets, signature checks or uncertain-request barriers are relaxed.

The manifest changes seven official assets: sb.exe,Config/Config.wpak and
cache/{Mesh,Textures,Visual,Render,CObjects}. An actual official/runtime census
must verify their identities and distinguish user/runtime-written drift before
installation. The no-retained-rollback deployment policy applies; rebuild from
committed source and official assets, preserving non-reproducible data in place.

## Validation and next steps

Host0.3.105/native1.8.67 are the matching source candidate. The focused host suite
passed329 tests with one optional skip; Ruff passed. Full Release Win32 compilation and nine focused native cases passed, including
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

The vendor policy remains exclude confirmed Tier1/2, keep unknowns. A newly
reviewed executable does not inherit destructive affix qualification. Preserve
all unresolved historical Create/Keep records and perform no automatic replay.
Private executables, disassembly, manifests and startup logs stay under the local
artifacts/vendor-resume/20261013 evidence directory; no fallback runtime is created.
