# Wonderbane official client update — October 9, 2026

## Host .86 installed and activation verified

PR #131 merged the automatic-preparation recovery fix at `abc4f3d` after all
15 required checks passed. An internal exception no longer reserves the separate
finite-operation handoff indefinitely. The service retains its owner and original
fault, requests passive cleanup once, and waits for positive closure and disposal
before rechecking current intent and authority. Explicit operation handoff,
unresolved cleanup and Pause/Stop remain blocking. All 65 focused regression
tests passed independent review. This fixes a reproduced source defect; it does
not establish the initiating exception in the earlier live .85 observation.

Qualified release `47242467adab1ee36d882dfe3ba9367050db8c8b` is published on
`codex/preparation-fault-release-20261009`, owned by root in `bot-integration`.
It is host .86 with native .56 still from `df97e7b`. All 5,705 host tests passed, with 39 optional
skips. Both native profiles' 74 movement / 86 combat / 170 actor IPC cases, the
real worker handshake and six installed-wheel Windows desktop cases passed.
All 480 source, wheel and installed module files agree. Native runtime inputs,
assets and graphics remain unchanged; PR #125's test-only fixture correction
remains the sole reviewed native-tree exception.

| Host .86 artifact | SHA-256 |
| --- | --- |
| Qualification receipt | `f01d70fd1b3ea21697f5d9872315a432f8c675ed54895dafed7aa6f7e82d5826` |
| Wheel | `ed91e162c5653c487549bb39e20f8888fdbc85dafcd5ad7fdc73bac3641a5fd9` |
| Reviewed deployment plan | `4af580852ca66a8aac831c70bf670c998661ad012150a8cc0ee2d28f5887a40a` |

Before the update, normal Detach positively stopped the old .85 worker. The
configured manager automatically rebound Umbra; no manual Attach or client
restart was needed. Normal Resume restored upkeep on worker 5396, creation
FILETIME `134360353336218688`, native producer generation 8. A completed passive
capture has 79 valid native samples and four unavailable samples. Precision,
Beorc Rune and transform each progressed from queued pending to `OBSERVED` with
local settlement; submitted/observed revisions were 3652/3654, 3656/3658 and
3661/3665. Defensive stance also has queued, locally settled `OBSERVED` evidence
at 3668/3669. All five groups remained present in valid samples for the final
75.6 seconds. Conc-pot stayed present with quantity five and no new application;
this is restoration evidence, not proof of Conc-pot expiry renewal or continuous
coverage through unavailable samples. Capture SHA-256:
`5d4283d17e44d3c18ffc85187e5dc6dd8de5ea771835a30539a9e36c3bb5c625`;
compact recovery summary SHA-256:
`35c126696c9428c4dc33c7d558e32c42a0f015c688f888ccd4ee81ddb682a78e`.

Preparation, exact manager/worker shutdown, host apply and shortcut updates
succeeded. Apply preserved 9,494 retained records and game PID 8480, creation
FILETIME `134360273074287806`, HWND 197186 and native DLL `45d1a787...`.
Client files were not written and no rollback copies were created. Apply receipt
SHA-256 is `cde87c35cc2b460c5a7b5f753f087dc19d8cdc477cffa74bfe93a58f2f1979ec`.
Activation passed with healthy manager 1776, creation FILETIME
`134360368274685389`, parent 4520 and startup generation
`248bc890995a47bda8fcc428d4e464da`. Worker 2784, creation FILETIME
`134360368332945599`, is bound to the unchanged Umbra game lifetime. All 480
installed modules and 9,494 retained records passed verification, with zero
exclusions and ten expected generated-record changes. The exact synchronization
marker bytes were read and hashed; no data-preservation exception was introduced.
Activation receipt SHA-256:
`c8ca2f8d9e6bb3d1520ceedc80ba2fec792eb4de60ff31c5b843f7d8d589ca77`.
Normal Resume succeeded. The completed post-update passive capture has 101 valid
native samples and three unavailable publication reads on exact worker 2784,
producer generation 9. All five groups were present in every valid sample across
116.5 seconds. A queued, locally settled Beorc `OBSERVED` receipt at submitted/
observed revisions 4557/4559 was already terminal in the first sample; no new
application transition was seen within this capture. Conc-pot remained present
with quantity five and no application row. This confirms sampled maintenance,
not a live induced-fault recovery test, uninterrupted coverage, or Conc-pot renewal.
Capture SHA-256 is
`2233efd19d06d1d6827f3119344239e842b5f6016b69b08bbd37518f37e9238f`;
compact summary SHA-256 is
`cac32524269fa1794c112d319233c0b51322b53fdae6ddc50b1ed496b23e1232`.
Fresh dependency and ownership inspection then permitted exact obsolete-.85
retirement. The old host's 2,151 files occupied 48,683,791 bytes; ten superseded
wheel files occupied 9,090,275 bytes. All eleven target paths are now absent,
freeing 57,774,066 bytes. Settings, jobs, journals and diagnostic evidence remain;
no native DLL or client asset was removed and no rollback runtime was retained.
Retirement receipt SHA-256:
`61bbf874f41aa7666e79a26b5e944b8031b4cdc038e0307fee2e44905eb87fba`.
An independent post-check confirms the same game lifetime and DLL, healthy
worker 2784, current maintaining preparation with all five groups present, and
no active or queued operation. Post-check SHA-256:
`4fe1a2b28f59c7ad2d40f8a78eb9d16560f0e6b99247c76437c66fdd9ec7cbeb`.

Source, qualification, installation and obsolete-runtime cleanup are complete.
Natural Conc-pot renewal and deliberate movement-interruption recovery remain
separate live acceptance work. The .86 automatic internal-fault recovery path is
covered by deterministic regressions; these healthy live samples do not claim
that an internal fault was induced or observed and recovered in the installed run.

## Host .85 installed and activation verified

PR #129 merged reviewed desktop startup source
`23d1a11e4d640329e49bb63b9240364d8727c77a` into main at
`b5ebb51657351aac017fe2e70f6a34fc0bacc2ba` after required review and checks.
Desktop shortcuts now delegate startup behavior to the packaged manager entrypoint.
Its authenticated, immutable listener identity avoids slow full-status inspection;
one exact durable process generation is reused after timeout or concurrent clicks.
Worker attachment, native readiness and dispatch checks remain separate. Definite
pre-creation failures permit a corrected retry; ambiguous process ownership never
authorizes another launch. The source's 64 focused tests passed independent review.

The qualified release composition is
`7720bc544a842b24c555b97836d7a2d5008c3226`, published on
`codex/manager-desktop-release-20261009`. It passed 5,693 host tests with 39
optional skips, both profiles' 74 movement / 86 combat / 170 actor IPC cases,
the real Windows worker-startup handshake and all six installed-wheel desktop
startup cases. These exercise delayed readiness and concurrent reuse, actual
process-creation rejection, and failures after a child has already been created.
The handshake substitutes only an inactive gameplay application; it does not
launch a client or claim live gameplay acceptance. All 480 source, wheel and
installed module files agree. Native .56 remains from `df97e7b`; native runtime,
assets and installed graphics are unchanged. The sole native-tree difference
remains PR #125's reviewed test-fixture correction, not a DLL input change.

| Host .85 artifact | SHA-256 |
| --- | --- |
| Qualification receipt | `c6c8cb77b826ba8b027e85fc72b218f06a70b14a1eb631da39b1ccfdaeac0464` |
| Wheel | `849c16bdd7c7141cda1e2bb6a94638902c74ed1ce019e1517ec15facc2bbcb64` |
| Source archive | `55076e5f34d90742c8d6a1e36aed4949a9c194967c8ab14a3cf5e327b261c284` |

Preparation, exact manager/worker shutdown, host switch and shortcut updates
passed. The switch preserved 9,488 retained records and the same Umbra PID 8480,
creation FILETIME `134360273074287806`. Client files were not written; the current
prepared executable, native DLL and per-lifetime receipt remain exact. The manager
launcher is now a configuration-only delegate to the packaged entrypoint.
Apply receipt SHA-256:
`d7504cad804cf33eaee8b13ff84338a96ffe6357b94b1c8ad6c12d395a14cd98`.
The reviewed plan SHA-256 is
`d10e8fcfd1604402f4919346199d2b35f336da440f7d8bd3f7d03b9eab2fae7f`.
No rollback copies were created.

The packaged entrypoint started manager 3872, creation FILETIME
`134360335439531729`, with exact parent 8472. A subsequent real desktop entrypoint
call returned in 2.422 seconds and reused generation
`1b1a8d6433a84eeeb35721fd4cd9ade3` without another spawn. The manager attached
worker 3828, creation FILETIME `134360335482772418`, to the unchanged game lifetime.

Activation verification passed for all 480 modules and 9,488 retained records,
with zero exclusions and ten expected generated changes. The private verifier
initially compared the canonical lower-case Windows manifest path case-sensitively.
A separate, reviewed verification-only correction normalized those path operands;
sealed payload/runtime bytes stayed unchanged and no manager was relaunched.
Future deployment verifiers must retain Windows path identity semantics instead
of copying the obsolete case-sensitive manifest comparison.
The receipt records original/corrected verifier and runner hashes. Activation
receipt SHA-256:
`f8d30e8f3c506560ae6bcd6f72e8c8b314c53f5913bab764f07d8b6702cc1db5`.
Normal Resume succeeded. At that verification boundary, fresh status reported the same healthy worker,
current maintaining preparation and all five groups present, with no active or
queued operation. This confirmed .85 upkeep at that boundary, not new expiry-renewal or
movement-interruption acceptance. The compact status receipt SHA-256 is
`dbd18c7a88ad64d35a7a2ce508f0ed7332a52d5e435c594387e04c73f9235036`.
The completed post-Resume native capture contains 80 valid and six unavailable
samples on exact worker 3828, producer generation 7. Precision, Beorc Rune and
transform each moved from missing/queued application to `OBSERVED` with local
settlement true: submitted/observed revisions were 3293/3295, 3297/3299 and
3302/3306 respectively. This proves restoration after Resume; the capture did not
observe their earlier expiry edges. Conc-pot stayed present with item quantity
five and no new application row. The capture SHA-256 is
`56e98edc6a63f725e43e883382f1cd8229a9e378a0e9f007f3604d6979214ace`;
compact summary SHA-256 is
`98466dcd18b8cb684c940582607c6230af7fc9096a14aa76aafa9e1d14d8cf4f`.

Fresh ownership and dependency inspection verified the obsolete .84 host safe to
retire. Its 2,146 files occupied 48,524,864 bytes; ten pinned superseded wheel files
occupied 9,083,149 bytes. Retirement removed 57,608,013 bytes, and a separate check
confirmed all eleven target paths absent. The exact .56 DLL and game lifetime
remained unchanged. At that post-retirement boundary, the same .85 worker was healthy, with all five
groups current and maintaining and no active or queued operation. Settings, jobs, historical
journals and diagnostic evidence remain in place; no rollback runtime is retained.
Retirement receipt SHA-256:
`c56ce3dedbaa99be4a4ad8cc54cffa057045e4e851228afdcb3bab4d3bde756a`;
post-retirement check SHA-256:
`d15d632e93dd5ff0f3cc287d0c63619ad01de2b221c67125f3f1415b89637aa6`.

The merged desktop source topic and superseded .84 release branches were retired
locally and remotely after checkout-ownership and ancestry verification. The exact
current .85 release branch remains published for reproducibility.

The .85 installation and obsolete-runtime cleanup are complete. Those receipts
are time-specific; they do not prove that upkeep stayed active indefinitely.

## Later upkeep stop observed

The subsequent ten-minute passive capture contains 282 valid native samples and
143 unavailable samples. Its last valid native sample reported Beorc Rune,
transform and defensive stance missing, followed by unavailable producer evidence.
A later manager read still found exact worker 3828 healthy, but its buff-service
state was `disabled`, current preparation was false and no operation was active
or queued. This supersedes the earlier all-five-present check as the latest
upkeep observation without invalidating the installation or retirement proofs.

Saved buff intent remained enabled at settings revision 2. Its exact file SHA-256
`5994464d87b6628dda9c7a2704a67036ca3811f57c0efd7c32236a7733787379`
matches the pre-update retained-file inventory. The observed service stop therefore
is not evidence that saved user intent was switched off. The late status receipt
SHA-256 is `95bcafb48c0d956be9cf8acb195caf81959fd316e4dc5ebd81f8922bd8056062`;
the saved-settings inspection receipt is
`030683a6a75e5b5d13fa223e257e599fd77045ffd7613728dc2ad5c52d056467`.
Long-capture SHA-256 is
`0cc7ced85a4e21acbc82c866f3e71d15b61adc76ec135e8433a5304f1808801d`;
compact summary SHA-256 is
`7451761e9a5d69147e132f83f2353e0f78d603341549785e22f60274d2487a96`.

Separate source work is investigating recovery from internal preparation-service
faults. These live receipts do not identify the exact exception or establish its
cause, and unavailable reads are not credited as successful maintenance. Next:
resolve the unexpected upkeep stop, then validate Conc-pot expiry renewal and
movement-interruption recovery. Conc-pot stayed present with unchanged quantity
and no new application in this longer capture; elapsed time alone proves neither
renewal nor remaining duration.

## Precision renewal observed before the .85 switch

A passive native capture on the unchanged .84 manager's exact worker 5960,
generation 6, recorded Precision present at revision 2961, then missing at
revision 3036. Automatic upkeep queued command
`bffbb190d3486b0643be2b6b8c696a0962ec278d7f8e0adbc498ab0f9f5f3fa5`
with application pending and local settlement false. The next valid observation
reported coverage present, application `OBSERVED`, local settlement true,
submitted revision 3036 and observed revision 3038. This is a complete native
missing-to-queued-to-restored renewal cycle during undisturbed upkeep, without
inferring completion from a timer. The capture contains 96 valid samples and five
explicitly unavailable samples; unavailable reads are not credited as progress.

Capture `native-buffs-4f4728135c984fdc99714d3d8a31eaaf.jsonl` SHA-256 is
`e461d687664750293fa9f536f3bb97753c5f8e69a31e71c853eef6198f7ba8e6`.
The compact two-capture summary SHA-256 is
`00512faa9d753dcf48659d174796e02477fb755862647f4ff605df24bd8486c9`.
Conc-pot remained present with the same observed item quantity and no application
row in this capture. Conc-pot expiry renewal and movement-interruption recovery
remain unproven; neither is inferred from Precision's successful cycle.
Private capture and summary files remain outside Git.

## Historical host .84 recovery and verification

PR #127 merged the reviewed status snapshot fix `cc7ebfb` into main at
`cc3474d98979134d8cdb0d963fc82188ce683f17`. The manager now reads the
asynchronous preparation record before the corresponding worker health snapshot.
A deterministic interleaving test reproduces the old false-unavailable result;
a replacement-worker test prevents old coverage from appearing current. All
existing identity, sequence and freshness checks remain in force. The 25 focused
tests passed independently. This proves the source race, not that every live
status gap had that cause. Separately observed passive native reads reported
`native publication freshness unavailable`; that does not justify relaxing the
native freshness limit or changing gameplay admission.

The qualified host-only composition is
`b74a97f10fb6496091df529f2484e314c4323c37`, published on
`codex/preparation-status-release-20261009`. Qualification passed 5,667 host
tests (39 optional skips), all six full/diagnostic-profile IPC suites, the real
Windows worker-startup test and all 14 package stages. All 478 wheel modules match
the exact source. Native .56 remains from `df97e7b` with the existing DLL; runtime
native build inputs and installed graphics are unchanged. The native source tree
is not entirely identical: it includes PR #125's explicitly reviewed test-only
`PAGE_NOACCESS` fixture correction, which does not alter DLL inputs.

| Host .84 artifact | SHA-256 |
| --- | --- |
| Qualification receipt | `cc28072871e41c413dd9fe769600deee61d9d97d0ebe1b5a5e62e9fd44bcc9cd` |
| Wheel | `bb4d0b039adb0302beddb82bda249cce1df51b72848d96c48e7c720271406ea1` |
| Source archive | `f3f9e878a3fd443e13fdb38c029c4d6406b064a2dbc7ac9a4895d064a756c461` |
| Reviewed installation plan | `978578636a3c7916fbc55bfd57656b1e37d7d59a35831a81d1e2ce49679bcc2b` |

Preparation, exact manager/worker shutdown, host switch and shortcut verification
passed. At that boundary, the switch preserved 9,561 records and kept the original
Umbra game lifetime open. Client files and the client launcher were unchanged;
the manager launcher was updated. Both manager shortcuts now reference .84; the
three client shortcuts remain unchanged. The apply receipt SHA-256 is
`0a3c106fa14ce087b140d5599ad842e950f6160e0991e0bc7eb1812f96fdd39e`.
No rollback copies were created. The baseline helper hashes both known one-byte
synchronization markers, retrying only permission failures for up to three
seconds; it excludes no retained records.

The launcher's two-second readiness request timed out even though a subsequent
status read found the .84 manager and its paused worker healthy. Verify-only
finalization then rejected a changed `desktop-start.stderr.log`. Guest-control
access temporarily failed, and the user restarted the game after a freeze.
The game now has a newly verified lifetime, PID 8480 with creation FILETIME
`134360273074287806`, and still loads the exact .56 DLL. Its per-lifetime launch
receipt SHA-256 is
`3e746b31e5199d7b414ab61cf16ae660392f749e9ec4dc588be708b5f443c61e`.

The .84 manager was restarted once and attached worker 5960, creation FILETIME
`134360275808487413`, to that new lifetime. Normal Resume succeeded. Eight of
eight subsequent status samples reported current, maintaining preparation with
all five buff groups present. These samples establish current coverage, not a
new expiry-renewal pass. The compact post-restart summary SHA-256 is
`169f74316eebe55bdd6e9c4d0ef8a9f256e36263ed4e0f98a21c9e7b76eeba35`.

Recovery verification passed separately for manager 8724, creation FILETIME
`134360275743172986`, and its exact worker/game binding. It verified all 478
modules and 9,561 retained records with zero exclusions. Eleven expected generated
record changes were reconciled, including the preserved startup-log prefix and
six capability records written by the earlier, now-stopped .84 worker at the
previous game-instance path. Original deployment receipts and failed-attempt logs
remain unchanged. Recovery receipt SHA-256:
`3d2f8dfa0c0fb867df6c70c26f8cbcd9e3a0d87af8c02cb0346db415b972ed8e`.

Fresh dependency inspection and retirement of the obsolete .83 host completed.
Its 2,146 files occupied 48,524,452 bytes; ten superseded wheel files occupied
9,083,061 bytes. The verified total removed is 57,607,513 bytes. A separate
post-read confirmed all eleven target paths absent, the current .56 DLL unchanged,
the same new game lifetime and a healthy worker, all five buff groups current and
maintaining, and no active or queued operation. User data and diagnostic evidence
remain in place. Retirement receipt SHA-256:
`d97a889a29a940fc196f97d4b9a8bbf23d488ccae24c5516a59b93e1bbe98df7`;
post-retirement check SHA-256:
`7fd3a923c3bfb7d60a675c38f891035a01fbe42eb9abf38c09335aa0832325ce`.

At this historical checkpoint, launcher readiness, Precision/Conc-pot expiry
renewal and movement-interruption recovery remained next. The .85 and Precision
sections above record subsequent progress; Conc-pot renewal and movement recovery
remain outstanding.

## Brief production PvE and preparation handoff

After the user moved near NPCs, the existing exact-worker operation ingress ran
saved basic PvE with Shot to the Leg (`563795161`), without hotkeys, UI target
selection or Shadow Touch. The 62-step native journal records the opener queued
at 4.969 seconds and ordinary attack at 5.391 seconds. Initial target `[23887,37]`
fell from 800 to 442.897 health before an `engagement_stalled` transition and
confirmed exact-target cleanup. On the next target, the opener was rejected as
`power_reuse_blocked`; ordinary attack followed without replaying the opener.
Target `[23885,37]` reached 0/400 health at 20.704 seconds with
`native_health_zero` confirmation. The final native kill count is one.

Explicit cancellation ended the continuous run. The original PvE operation
`operation-c0b57b1cc14f46d99b4b179165187390` became `cancelled`, the cancellation
receipt succeeded, and the manager showed no active or queued operation. The
journal confirms exact child cleanup; it does not independently claim aggregate
parent closure. A later passive census found no player action target despite a
different UI selection. Normal Resume succeeded and fresh status again reported
all five groups present and maintaining. This verifies the controlled
preparation-to-PvE-to-cancel/Resume workflow, not an indefinite farming run or
additional buff expiry/interruption acceptance.

The final evidence SHA-256 is
`ba38403caa7fe98fc9e764cbab148914e459e035630f117ea223613510f812ba`;
the append-only journal SHA-256 is
`7f9639b003c8921026eab81a46e30c12f48f30924e518851ade349428b306b0e`.
Both remain private under the diagnostic share's
`pve-chat-20261009-101838-1791555518959991400` filenames. No further PvE run was
needed to establish this bounded observation.

## Host .83 delivery history

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
