# Wonderbane official client update — October 9, 2026

## Current status

Official client 1.3.38.16 is installed with qualified host 0.3.81/native 1.8.56
on the testing VM. PR #121 merged the reviewed compatibility head `b5b6a6a`
into main at `6c3cd6d65db88f0c213df0fadd583cc53cad7485` after all 15 hosted
checks passed. Start new bot work from refreshed main.

The exact deployment source is `df97e7b328626f74efe6a1fb5e17e926942e37b4`,
published on `codex/client-release-20261009`. It combines the merged bot update
with the previously installed graphics composition from `3e4d801`; all 33
graphics-only paths are unchanged. Graphics PRs #106/#113 remain separately
owned drafts, outside main. Retain the release branch for reproducibility until
those lanes are integrated; it is not a separate shared development base.

## Exact client identities

| Artifact | SHA-256 |
| --- | --- |
| Official manifest | `5233f7f19883d8b1935e10b64e264020ac5996178b170a44b793de796cea3535` |
| Official executable | `a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a` |
| Derived prepared executable | `1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c` |
| `Config/Config.wpak` | `8bbb2e579a365f93123451967b8d6bf236f3d718121cda12803f22f6152cf788` |
| `cache/CObjects.cache` | `1cec608d64ce5bb9b62d7d46bf72f0bd157a0f4d02a23d731b5db24162ed8c04` |

The previous and current official executables are both 21,143,613 bytes. Exactly
one byte differs, at file offset/RVA `0x12dc18c` in `.data`: the embedded version's
last digit changes from ASCII `5` to `6`. All code and PE layout bytes are
unchanged. All seven bootstrap writes are byte-identical to the previous client's
writes; the derived prepared executable likewise differs only at that version byte.
These facts establish structural continuity, not package qualification or live
gameplay acceptance.

Independent production comparison checked 16 applicable profiles and 51
calibrated anchors with no changed intersections. All 128 literal hashed native
RVA spans from the qualified .55 source match both official images, also with no
changed intersections. Original-client action denial, prepared-only admission,
loaded-code checks and character-session revocation remain in force.

Of the 211 official manifest entries, only the executable and the two data files
listed above changed from the previous release. Installation must still compare
the actual guest files, preserve user settings/jobs/journals in place, and follow
the [no-retained-rollback deployment policy](deployment-policy.md).

## Qualification and installation

The exact-source package passed 5,614 host tests (40 skips), 249 full-profile and
245 diagnostic-profile native tests, and both profiles' cross-process checks:
74 movement, 86 combat and 170 actor cases without skips. The newly skipped
display-dependent host case passed separately against the packaged source.
Dedicated IPC and original/prepared-image runs covered the corresponding generic
fixture/image-wrapper skips. Independent verification reproduced all 136 artifact
and 108 stage checks. Two pre-existing, non-required graphics transparency
diagnostics remain recorded; this update does not claim to fix them.

| Qualified artifact | SHA-256 |
| --- | --- |
| Package archive | `800641e9cc636839218f9a7d891540e69408931f6325178032c4fd0103d19574` |
| Package receipt | `33e7738647f2ba3584d893fc8d72e6eb55f19d30b8b1cd41a83c936bfac54842` |
| Full extension DLL | `45d1a787c317e9a812ae0829e53288404cac0a4cdfa488068888ad517ae6690c` |
| Host wheel | `5366c1183ae9b8e971fc82411aae9030c5ee1327be7972bd35224280a86beec8` |
| Reviewed installation plan | `a82811c3cc9f77a8fb63e9a9bcc5d7a859fc56f0e0472fabfd141cf8a96c76c5` |

Installation verified all 477 host module files and preserved 9,621 settings and
history records. Exactly four client inventory entries changed: the three
official assets listed above and the extension DLL. Both clients' mutable
DoubleFusion files and user data were preserved. The normal client supplied the
official assets and was not modified. Two manager shortcuts now reference .81;
the client launcher is unchanged. No rollback copies were created.

After activation, a fresh ownership and dependency inspection verified the old
.80 host contained only reproducible build files and had no active references.
The old host's 2,144 files and 11 pinned .55 payload files were removed, freeing
58,787,243 bytes; absence was verified afterward. User data, journals and compact
diagnostic receipts remain in place. The retirement receipt SHA-256 is
`ec9baefa481237fd027c870b7dec7b94036ab9ee584fe3fd0b2e750e67956e6a`.

The merged, unattached host topic branch was retired. The release composition
remains published for graphics integration; the integrated native checkout is
retained as the existing investigation workspace. Private qualification and
deployment evidence remains under local `artifacts/client-update-20261009`,
`artifacts/b56/02c9d75a` and `artifacts/bot-deploy/20261009-b56`; binaries and
captures are not part of the source delivery.

The new manager finalized healthy and unbound. Vendor Test reopened through the
reviewed per-lifetime launcher at 10:34 UTC with the exact .56 DLL. Passive
inspection before login reported no observable local player and no ready actor
service; this is not in-world gameplay acceptance. Next: log Umbra in, then
validate persistent buff renewal and movement-interruption recovery.
