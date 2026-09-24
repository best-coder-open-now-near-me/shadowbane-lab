# Client update - September 24, 2026

The official client is 1.3.38.11. Native 1.8.27 and host 0.3.47 admit only
its reviewed exact identities. The integration destination is `main`; source
work is on `codex/client-update-20260924`. Packaging, VM installation, and
live gameplay qualification are pending at this source checkpoint.

## Binary review

The existing `shadowbane_lab.client_alignment compare` tool compared the
fresh official executable against reviewed 1.3.38.10. Both are 21,143,613 bytes.
Exactly one byte differs: file offset `0x12dc18c`, ASCII `0` to `1` in the
embedded version string. PE headers, imports, relocations, section layouts,
and every other byte are unchanged. The `.text` SHA-256 remains
`5cab14307005f6ebdfa268107aa2a1aeba35cb071b17cdf3d01665a3f3294607`.
None of the 50 reviewed anchors across 16 profiles intersects the change.
The existing bootstrap aligner independently resolves all seven patch sites
exactly, with no relocation or ambiguous match.

| Executable | SHA-256 |
| --- | --- |
| Official original | `6347b420c6c151995f168f16fd1624408dd8911698d11a4a74b26d211fb49f19` |
| Prepared loader copy | `7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f` |

These findings justify reusing the reviewed addresses with exact identity
checks. They do not authorize future executable variants or qualify gameplay.
Prepared-only vendor, crest, crafting, character-config and response-hook
boundaries remain prepared-only. Unknown affixes remain unqualified.

## Official data changes

The fresh official manifest has 211 files. Compared with September 22, exactly
five entries change: `sb.exe`, `Config/Config.wpak`, `Config/Environment.wpak`,
`cache/CZone.cache`, and `cache/CObjects.cache`; there are no removed files.
All five downloads match the manifest sizes and SHA-256 values. Both official
and prepared VM copies require all five files, with the reviewed loader patch
applied only to the prepared executable.

## Validation and delivery

Focused host validation passed 127 tests plus Ruff. Actual original/prepared
movement-image checks passed in both native profiles, including mutation
rejection; scene, selected-cue and sky bindings passed against both files.
The original-only movement probe passed 64,256 sequences and rejected the
prepared image. Five focused native tests passed. Actual host authoring
reconstructed all seven loader spans and rejected malformed or prepared inputs.

Next: commit this coherent source slice, build the exact committed package,
run required CI, install with rollback backups and verify retained settings
and journals. The game remains closed for the user's next login. Guard upgrade,
Condemn, vendor live qualification and carpenter discovery remain on the
[catch-up plan](catch-up-plan-20260923.md).

Private executables, assets, alignment reports, and rollback payloads remain
under ignored local artifacts or the VM diagnostics share, never in Git.
