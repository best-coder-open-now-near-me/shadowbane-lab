# Client update - September 24, 2026

The official client is 1.3.38.11. Native 1.8.27 and host 0.3.47 admit only
its reviewed exact identities. The integration destination is `main`; source
work is on `codex/client-update-20260924`, delivered through
[PR #34](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/34).
The exact-source package is installed and its launch preflight passes.
The game remains closed; live login and gameplay qualification are pending.

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

## Installed package and preservation

The installed package uses source `d74d3c38d6131fea8399dd3d0ac825e166b0034f`.
All 15 hosted checks passed on that source head. The later handoff-only commit
uses the same package; PR #34 records checks and integration of the final head.
Full local validation passed 3,386 host tests (18 skipped), Ruff, 169 required
native tests per profile (three private-image tests separately exercised by
actual-file gates), 63 movement IPC tests per profile, actual executable binding
and rendering checks, and installed-wheel checks. The two documented ideal
transparency counterexamples remain recorded per profile; required production
checks pass. This does not claim corrected transparency.

| Artifact | SHA-256 |
| --- | --- |
| Full-profile DLL 1.8.27 | `0c90bbd8a76eece3be88e97d253f9a80c42a99fb859d3e65f35c7519d8853f18` |
| Host 0.3.47 wheel | `4ca89cd05ddde0099a6a92f0adcc41bc24269ad7a55dca73cb8a58ad896c443d` |
| Acceptance-candidate archive | `068490dad1d02a5ebc39e1484a6c299c3c1eb1979ff3b3cffb498d75a9aaa007` |

Both VM client copies now contain all five updated official files, with only
the prepared copy using the reviewed loader transform and extension. Rollback
backs up ten official/prepared files plus the DLL, package metadata, launcher,
dashboard launcher, and prepared-status record. The five desktop shortcuts also
have rollback copies. The game launcher derives its host from verified prepared
status; both dashboard shortcuts now use host 0.3.47.

The manager is healthy and unbound; its exact process tree uses host 0.3.47.
Across 9,441 retained worker, qualification, and configuration files, all 9,440
non-permit files are unchanged. Only the expected idle dispatch permit refreshed,
strictly parsed as revoked/unbound. No historical request was replayed. Launch
preflight verified package, source-client guard, settings receipt, and launcher
syntax without starting the game.

Rollback and deployment receipts are in the VM runtime's
`upgrades/1.8.27-d74d3c3`; the ten original file backups are in the private
`client-update-20260924/preparation-backup` diagnostics share. The package and
validation logs remain at local `artifacts/c27/34568833`. The clean update
worktree is retained for follow-up; it is not an alternate development base.

Next: the user launches **WonderBane Modded Client** and logs in. Resume the
serialized Irekei Barracks and vendor recipe/Inventory observations afterward;
carpenter discovery waits on building readiness. Guard upgrade, Condemn, vendor
live qualification and carpenter discovery remain on the
[catch-up plan](catch-up-plan-20260923.md).

Private executables, assets, alignment reports, and rollback payloads remain
under ignored local artifacts or the VM diagnostics share, never in Git.
