# Wonderbane official client update — October 9, 2026

## Current status

PR #124 merged the protected-process recovery fix into main at
`99b770742b4ceb6eccde1de95103ddb40db736c0` after all 15 hosted checks passed.
Host .83 handles denied process handles through a bounded kernel process census,
retaining exact creation FILETIME and parent identity. A validated complete census
can prove that a historical worker lifetime is gone; access denial alone cannot.
The real protected service that reused a historical worker PID and Umbra's exact
live process both matched the read-only kernel probe.

The qualified host-only composition is
`0e0c6b9d3459f4b026598f8fdbe1855b2f2fc29c`, published on
`codex/protected-process-release-20261009`. It preserves installed graphics,
assets and native .56 from `df97e7b`; graphics PRs #106/#113 remain separate drafts.
Qualification passed 5,665 host tests (39 optional skips), both profiles' real
IPC checks (74 movement, 86 combat and 170 actor cases each), and the separate
Windows worker-startup test. All 478 source, wheel and installed module files
agree, and all 14 package stages passed. Independent review verified the package
closure and the unchanged native artifacts.

| Host .83 artifact | SHA-256 |
| --- | --- |
| Qualification receipt | `3d768a6c86d4465303897dca8a71787e9fa733f028f63c71c981b021cf21bd2f` |
| Wheel | `19f457772369029867701b2011b0862506962ca2714992f91ce79a10b3147652` |
| Source archive | `3cd6bc8a7b438885d1cde7643a2b4ef0f09c60d5f0ff5e6358c43edc3a2a8083` |
| Reviewed installation plan | `84deafce11517eaeed257a97328c134e3843ed88701de89686b88db680f5ade1` |

Preparation, exact old-manager shutdown, host switch and shortcut checks passed.
The apply step preserved 9,550 settings/history records captured after manager
shutdown. Umbra's original game lifetime stayed running, and no client files
were written. Both manager shortcuts now use .83; all three game shortcuts are
unchanged. The manager automatically attached one healthy worker to the existing
Umbra process. All five automatic buff groups report present and maintaining.
Final activation verified all 478 installed modules and all 9,550 retained records.
The two active one-byte synchronization markers were read with bounded retries;
their original hashes matched. The original verifier remained unchanged and
zero records were excluded. Only the expected generated dispatch record changed.
The activation receipt SHA-256 is
`2f140610fdd5d926c6dc44d58123f103f458f9b935102f542225607f1a5c70c4`.

Passive native captures confirmed all five groups present and a defensive-stance
application queued, locally settled and observed (submitted revision 16, observed
revision 17). A later capture proved Beorc coverage changed from present to missing,
a new application was submitted at revision 22, and it settled observed at 24 with
coverage restored. Rat Shape then expired while still on reuse. The alternate
Skree'ekt Shape was queued at revision 28 and settled observed at 31, restoring
transform coverage. These are actual native state/application transitions, not
system-message or selected-target inference. Conc-pot and Precision coverage are
confirmed; their expiry renewal and movement-interruption recovery remain next.

Private observations remain under local `artifacts/bot-deploy/20261009-host83`
and the testing VM diagnostic share `host-update-20261009-0.3.83`. The bounded
reader retains native applications and coverage transitions; failed or incoherent
samples are recorded as unavailable rather than credited as completion.

PR #125 separately fixed the hosted test fixture that assumed address `0x10000`
was unreadable. It now owns a `PAGE_NOACCESS` allocation. The exact final head
`5d72644` passed all 15 hosted checks before merge `c8d79ba`; this test-only change
does not change the qualified or installed runtime.

## Obsolete runtime retirement

After successful activation, fresh ownership/dependency inventories proved the
old .81 and .82 hosts contained only reproducible files and had no active users.
The .81 host and ten superseded wheel files were removed earlier in this update,
freeing 57,588,774 bytes (receipt SHA-256
`7115b3cd138cea94b7d4a93c115173c1e2d1e538ef3d4a6f431cff8c940fcf55`).
The .82 host's 2,144 files and ten superseded wheels were then removed, freeing
57,595,245 bytes. All eleven .82 targets were absent afterward and the current
native DLL hash was unchanged. Its retirement receipt SHA-256 is
`2a5cb5b47e6f1d4db62fd1037c0276c524f5581d863173cb8256fb866272875d`.
Settings, jobs, journals and diagnostic evidence remain in place. No deployment
rollback copies were created or retained.

## Historical host .82 installation

Host .82 recovery source is merged through PR #123 at
`417b8e2c4dd24c198d721a441f52cb4b9f30642f`. It recovers an unverified worker
reservation after manager restart only when matching historical worker identity
and repeated OS observations prove that interpreter lifetime has exited. Live
workers are never adopted through this path; historical records remain intact.

The qualified host-only composition is
`db8fd5c23b417d215f918064aa1d20e2ed9f3ba7` on published
`codex/worker-restart-release-20261009`. It preserves the installed graphics,
native and asset trees. Native .56 continues to identify source `df97e7b`; its
per-client launch receipts are not rewritten to pretend it was rebuilt with .82.
Qualification passed 5,632 host tests (39 optional skips), both profiles' real
IPC checks (74 movement, 86 combat and 170 actor cases each), and the separate
Windows worker-startup test. All 477 source, wheel and installed module files
agree. Host qualification receipt SHA-256:
`ec981249b76aea27ff13dafaf6819d390b883a3ce0c3fe23c74e320fbebe55f8`.

Host .82 is installed and its manager is verified healthy. All 477 installed
modules and 9,557 retained settings/history records passed verification. The
same Umbra process remained open; the client executable, native DLL and launch
receipts were not replaced. Both manager shortcuts now reference .82. The old
unverified reservation was removed by production recovery, with its historical
heartbeat preserved. The verifier separately proved that exact permitted
removal before recording activation; no installed plan or helper was rewritten.

Live attachment then exposed a second issue: a historical worker PID had been
reused by a protected Windows service. Both ordinary and query-only process
handles were denied, causing the old-worker stop check to reject attachment
before binding Umbra. A read-only kernel process census established the
different creation FILETIME and matched Umbra's existing exact lifetime. The
focused .83 fix is under review; automatic buffs remain inactive pending it.

The following .81 installation record is historical.

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
