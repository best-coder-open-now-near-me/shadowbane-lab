# Client update: September 19, 2026

The user reported the login screen requires a newer client. Both the normal
Downloads client and the isolated Vendor Test copy still used 1.3.38.7.
The official patcher manifest currently supplies 1.3.38.9. Its generic manifest
metadata still says gameVersion 1.0.5; the embedded executable version and
whole-file hashes establish the actual build.

## Exact compatibility review

- Original: `a32275aabab8d5955f4d45adde6e84a666f44be54c951ccf8dc2d538237e8be4`.
- Prepared: `e277e5a4e1e4e1df048a32c07bdbac6fec0591c7d01588b984577251cf475891`.
- Reviewed reference: `ac9ca46467997667d49b85cd6076954813a72b56f71e2ad85a4085f3a9f391ca`.

All complete executables are 21,143,613 bytes. PE headers and section layouts
match. Exactly 111 bytes differ across six ranges: .text RVAs 0x6c981 (4),
0x70340 (90), 0x75674 (5), 0x9b460 (5), 0x37c8d8 (6), and .data RVA
0x12dc18b (1). The .rdata, .idata, .rsrc and .reloc sections are unchanged.
Alignment finds zero intersections with 50 anchors across 16 native profiles.

Disassembly shows the call at 0x6c980 restored to 0x25efa; two prior jumps
are replaced by native instructions at 0x75674 and 0x9b460. The player-pointer
assignment at 0x37c8d8 branches to the new 90-byte routine at 0x70340.
That routine retains the assignment to 0x1aa2d98, preserves registers, walks
the existing player collection at offsets 0x670/0x674, calls existing methods,
then returns to 0x37c8de. The version byte changes 7 to 9.
None of these spans intersects our loader, scene/update hook, guard/vendor
controls, funding, item-production serialization, character config routines,
or targeted-action trace bindings. This is offline compatibility evidence,
not proof of successful login or unchanged server behavior.

The unchanged seven-span loader transformation resolves exactly. Whole-file
authentication accepts the new original or its complete reviewed prepared
transformation; unknown, partial and mutated images remain rejected.
Vendor admission adds only the exact prepared identity. Generic layout family
membership still cannot admit vendor work. Affix qualification remains separate:
unqualified tokens on the new client stay unknown and are kept.

Native 1.8.21 / host 0.3.31 carry these identities. Focused host tests passed
(71), including unprepared-image rejection, exact process lifetime, character
identity, and conservative affix disposition. Ruff passed. Actual new-file native
tests passed original/prepared authentication, relocated loaded-text checks,
terrain startup ownership/restoration, mutation rejection, scene relocation and
every-byte drift rejection, 64,256 collection sequences and 144 continuation cases.
Exact committed full-package validation follows this checkpoint.

## Game assets and installation boundary

The official manifest was obtained from the server embedded in the installed
official WonderBanePatcher, using its request identity. Each download was checked
against the manifest SHA-256 and length. Comparing all 211 listed files in the
normal client identifies five game updates plus two client-written DoubleFusion
files. Retain those runtime files and all settings and custom renderer DLLs.

| Game file | New SHA-256 |
| --- | --- |
| Config/Config.wpak | `03400c4d3cc533ae931e00ba37be4deefd08ed7ee9f028408c28fdcadbaf9338` |
| cache/Textures.cache | `1a142d73f8e1ef9bed8b56ef3a238203bc16a1da6df9c69b5ca625652d0d968a` |
| cache/Render.cache | `5dd78baa0c5ae867e720ec05ba184624ad6dff363a576f48f941100d2e7d3667` |
| cache/CObjects.cache | `e8b63e7080dec6738e6d23f1dd5b00787567d24505298b290a74f0ffda0c4512` |

Private downloads, alignment, disassembly and rollback evidence remain in local
artifact/diagnostic storage; no game binaries or captures enter Git. The VM has
insufficient free space for a second complete texture file. Prepare verified
rollback copies on the host share and fail closed before replacement if the
backup, new payload, client identities or available storage changes.
Update both the normal official files and the prepared Vendor Test client,
then update the launcher's exact original/prepared/DLL hashes and package
inventory together. Preserve all settings and guard journals. Do not replay
unresolved requests, restart a guard job automatically, or launch the game.
The same Vendor Test desktop shortcut remains the entry point.

Delivery branch: `codex/guard-upgrades`; integration destination:
`codex/vendor-rolling`, then `codex/native-lifecycle-hardening`, then reviewed
`main`. This is not merged. Active todo: finish exact-source packaging and
rollback preparation, apply after confirmed game closure, then verify user login.
Carried-gold guard qualification follows; no Ulmer dependency is reintroduced.
