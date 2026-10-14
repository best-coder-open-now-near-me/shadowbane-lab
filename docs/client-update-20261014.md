# Official client alignment for vendor rolling - October 14

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
files are runtime-written and must remain in place. Installed software remains
host .111/native .69/client .18 until full graphics-preserving .112/.70 package
qualification and installation finish. No vendor action was dispatched.

Next: qualify and install the exact release under the
[no-retained-rollback policy](deployment-policy.md), verify launch, then resume
Treehugger in Rooty with movement, discovery and one whole funded quantity-ten
batch. Draft PR #174 targets main; this alignment stays on the active vendor lane.
