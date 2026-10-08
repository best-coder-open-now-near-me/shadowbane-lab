# Wonderbane official client update — October 8, 2026

## Delivery status

`codex/wonderbane-client-update-20261008` starts from refreshed `origin/main`
`cdaafb234cfe324cc1c750c77102cfcc76552f50` and targets `main`. The candidate is
host 0.3.78 / native 1.8.54. Source review, exact-source package qualification,
hosted checks and installation must finish before this candidate is usable.
Pending recovery PRs #92 and #94 remain separate; this update does not claim to
resolve their startup or worker-attachment defects. Own-server work is parked
at the user's request; this delivery serves the Wonderbane bot.

## Official update and exact identities

The user completed the official patcher in `shadowbane-testing`. The patcher
reports release 1.0.6; the executable's embedded client version is 1.3.38.15.
Actual executable and object-cache hashes match the fetched official manifest.
The local patcher metadata file stayed unchanged, so it is not used as proof
that the patch completed.

| Artifact | SHA-256 |
| --- | --- |
| Official manifest | `a6b33e082a99f5578af1f94ce7f1d585ec2f2c2246af8f06e389aa3eacb5fd8f` |
| Official `sb.exe` | `381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5` |
| Derived prepared executable | `e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437` |
| Official `cache/CObjects.cache` | `4df20426f0809779b28a4a9769ebf94fc1a02d6598e216f3a1b199ffb08b4804` |

## Binary review

Compared with official 1.3.38.14 (`e703e7cf…`), both executables are 21,143,613
bytes and retain identical PE headers and section layouts. There are 735 changed
bytes: 734 in `.text` and one embedded version byte in `.data` at RVA `0x12dc18c`.
`.rdata`, `.idata`, `.rsrc` and `.reloc` are unchanged.

The executable changes instructions at RVAs `0x4c5d1c`, `0x4c5d6c`, `0x4c6547`
and `0x4c69e7`, redirecting to previously unused space at `0x8f8000..0x8f8378`.
Disassembly shows object timing and attachment/vector handling, including calls
to `Math.dll` quaternion rotation and the system timer. This is a real code
change, not a version-only patch. These observations describe client code;
they do not establish server behavior or a new authority to issue actions.

Independent production alignment covers 16 profiles and 51 calibrated anchors,
with zero changed intersections. All 119 SHA-qualified native probe spans remain
byte-exact and have zero changed intersections. All seven loader writes align at
their original locations, with no relocated, missing or ambiguous sites. Exact
original/prepared hashes are added to the existing guards; signature, loaded-image,
character-session, ownership and unknown-image rejection checks remain in force.
Executable probes on both candidate images are still required for qualification.

## Validation and next steps

The initial host compatibility regression run passed 231 tests with one skip.
It covers exact bootstrap admission, prepared-only publication/readers, native
character-session revocation, object registry, ability/target readers, unknown
image denial and unchanged conservative item-disposal policy.

Independent host/native source review passed. The production DLL compiles, 29
focused native cases pass, and 510 package-gate/version tests pass.

Next: commit/push the coherent source checkpoint,
qualify that exact revision, then merge and install the qualified runtime under
the standing bot approval. Verify the current deployment baseline and retain
settings, jobs and journals in place. Keep compact source/hash receipts, not
rollback runtimes; see [deployment policy](deployment-policy.md).

Private binary/disassembly evidence is under the local task artifact directory
`artifacts/client-update-20261008`; client binaries and captures are not published.
