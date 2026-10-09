# Wonderbane official client update — October 9, 2026

## Current status

The user completed the official patcher. The official installation matches the
new executable in the updater's 1.0.7 manifest; its embedded client version is
1.3.38.16. The testing runtime still contains the previously qualified .15
client with host 0.3.80/native 1.8.55. This new compatibility update is being
prepared as host 0.3.81/native 1.8.56; it is not yet release-qualified or installed.

Main includes the persistent-buff implementation through PR #119 and its installed
delivery record through PR #120 (`32651c4`). The host compatibility branch is
`codex/client-host-20261009`; the native lane is `codex/client-native-20261009`.
The final deployment composition must retain the installed graphics source from
qualified release `3e4d801`, without merging the separately owned graphics drafts.

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

## Qualification remaining

Finish independent compatibility/source review, combine the bot update with the
installed graphics source, and run the required package checks against the exact
original/prepared client pair. Then update the three changed official assets and
the qualified runtime, verify the client launch, and resume the pending in-world
persistent-buff renewal and movement-interruption checks.
