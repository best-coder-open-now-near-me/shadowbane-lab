# Official client 1.3.38.14 update — October 4, 2026

## Host .75/native .52 installed and ready - October 7

PR #81 merged into main at `acb1ba7f41875a567654dbdcb5182857bba05679`.
Exact source `733b5fecb862c6d9421b8c2d20f8b8aee5c6db18` combines aggregate
cleanup ownership repair and optional item-response diagnostics. Package
`artifacts/b52/b9d92a76` passed 5,120 host tests (39 skips), 88 qualification
stages and independent verification of 116 artifacts. Each native profile passed
231 tests, 133 required gates and 74 movement/86 combat/146 actor IPC cases;
the item-trace reader passed 31 cases per profile with original/prepared decoder
probes. The diagnostic stream does not authorize actions or prove application.

The qualified DLL is
`6018a899c29a8057f93a6b4e2a677798a2a25200a91dbafeabe8aaa415ea4c90`;
wheel SHA-256 is
`32ac1e3a2ce4b9d72e2767c20e6195e674b925971e2b80968a59a322ec159a29`.
The .14 executable and October 7 official cache remain unchanged. Apply verified
467 modules, 9,607 preserved files and exactly one changed client inventory record
(the DLL). Manager 8100 activated healthy; all five shortcuts passed. Settings,
saved jobs and journals stayed in place without retained rollback runtimes.

The installer was independently reviewed with 53 offline tests. A planning
snapshot may be captured while the game is open; replacement separately requires
fresh closed-client/manager/worker proof. The two exact ArcanePref files may save
after planning, then their current closed-state bytes join strict pre/post-apply
preservation checks. Static executable, cache and native identities stay exact.

Fresh launch at `2026-10-07T13:07:38.7098114Z` verified PID 8436, creation
`134358520489522692`, HWND 2556262 and the qualified DLL. Passive in-world
readiness reported the player alive, native owner NONE, no pending cleanup,
scene 1 and capability flags 385. These are recorded observations; subsequent
actions require fresh lifetime/readiness validation. Initial passive preflight
`1b1e8b005391434d85bce9f68320a823` observed exact Umbra `4050960/53` alive
and idle, with no actions sent. Its census found zero eligible NPCs in the captured
population, not merely outside the camp radius. Later NPC availability permitted
the bounded runs recorded below.

Twelve compact exports, including independent installed hashes, are retained in
`artifacts/bot-deploy/20261007-b52/receipts`. Original guest receipt SHA-256 values
from `export-manifest.json` (distinct from normalized export hashes) are:

- Apply: `39e633779a769960d68ca709d636694d12978ee919e017e6e00c9b1ed8832f55`.
- Activation: `c8f3cd910f30486a582081426f31a46e593735ef98119b453e8783210fd3de48`.
- Launch: `4fc80c7ba828b947c89e1d10bb895613a369801faabb80d5cc8a81a079236239`.
- Obsolete runtime removal: `3e0419c45b066f85acdad823fdfd0cd4d42ba97bcc12f3b0383b0920ad3c2a62`.

Verified retirement removed 2,122 old host files and two obsolete payloads
(50,950,003 bytes). Five exact old host/share staging binaries were then removed
(7,352,316 bytes); that receipt is
`5993d1b90b8670e541d9473b03068e5351e0f6d204f57da858276f05941fca55`.
No settings, job records or original diagnostic evidence were retired.

The earlier .74/.51 Praeda run `7aae5857276148ebae0877ae58a352b3` passed one
native ATTACK queue/cancel against the exact player while UI selection differed:
child NATIVE_STOPPED, later SEEKING, parent LOCAL_RELEASED and empty owned list.
That result establishes bounded target/cleanup behavior, not server damage or
validation of .75 buff renewal. The previous failed NPC evidence below remains
failed and unchanged.

### B52 bounded buff and NPC results

Run `6a57949029b84f1ea6c6d078c6020e3b` remains **not passed**: the fixed
30-second session ended with NPC `23885/37` still at 400 health. The first context
was never bound and closed positively. Native initiation and local power
settlement occupied most of the session; the replacement context bound at
25.922 seconds, Shot queued at 26.203 and two positive ATTACK queues followed at
26.906/28.578. The moving NPC was about 150 units away when Shot queued and
129.6 units away at timeout. This run did not allow enough time to establish
combat completion; the evidence does not explain the short approach stopping.

All five native buff coverage groups were PRESENT by 28.406 seconds, including
concoction with observed item quantity 4 to 3. This establishes observed coverage
and quantity change, without server transaction/consumption attribution. Exact
child request 78 returned NATIVE_STOPPED and parent request 79 LOCAL_RELEASED;
no watchdog or unexpected interruption occurred. The acceptance summary's
`child_cleanup=not_started` is stale: its error path raised after recording the
positive cleanup event but before returning the tuple to its caller. The original
failed receipt remains unchanged; final membership was not captured in it.

The second run, `780510c5e3e54da3a4128a8828173f38`, **passed**. Exact NPC
`23886/37` went from native health 800 to zero at 9.016 seconds. Child request 25
confirmed NATIVE_STOPPED; parent request 27 confirmed LOCAL_RELEASED. Final
owned membership was zero, errors empty, and watchdog/unexpected-stop flags false.
Fresh passive readiness afterward showed owner NONE and no pending cleanup.
This proves the bounded encounter and ordinary cleanup path. It does not prove
server kill credit, sustained expiry/refresh, or a live recurrence of the specific
parent-local-action blockage repaired in this release.

Evidence remains private under `bot-actor-encounter-20261007-b52`:

- First acceptance: `dcf875f0fbe54fad8585cdb0c217dcb76cc93455a8ca80dd5197fe18eb5bdc31`;
  events: `e3353c903b622218b9d567798a0896e3adbbcc7791545276db5c9c32b3e24ed7`.
- Second acceptance: `e0191da251d5f176e022cf8372967f39497ec3b1504e76c425a49290b9076362`;
  events: `02aa20794e9e57d560dd3cb030f872f9f78aedd262ebc20837a1b66d47755026`.

**Current next todo:** bounded sustained buff renewal validation, with claims
limited to actual coverage transitions and native cleanup evidence. Automatic
retaliation remains disabled. PR #83 also incorporates reviewed PR #82's
client-evidence qualification plan without runtime changes.

## Official data-only patch verified and launched - October 7

The official manifest contains 211 files; its only change is
`cache/CObjects.cache`, from SHA-256
`5979b544426669e1ffd89fdf95a7a7800d1b42a6cfc7840c942efed1656ff2f7` to
`08c115baeef5da811f7ee2802ccdc1002cfeba29cf1818956c452e3e594efef6`
(5,433,065 bytes). Manifest SHA-256 is
`22e083d1ef09aa94ced7380cc7e2bf994e69b3a3d8450f319c8f19c4dabbb95c`.
The official/prepared .14 executables, host .74 and native .51 are unchanged.

With both games closed, preflight recorded 10,044 protected files. Apply wrote
both normal and bot caches and verified the resealed bot package, then failed
preservation checking on the manager's changing `dispatch.permit`. Independent
comparison found that sole difference: the exact slot was denied and unbound;
all 10,043 other protected files matched. The reviewed finalizer rechecked those
facts and completed at `2026-10-07T08:46:57.666772Z`, preserving the original
failure receipt. All 10,043 other protected files remained unchanged; the one
reconciled permit was explicitly denied/unbound. No rollback copies were created.

Finalization receipt SHA-256 is
`052a48aafe2480b0c2a5213f4e17674fcd19441f0d2fa2455f1fbf313f359628`;
resealed package SHA-256 is
`b3f8c213eafc7235d53a89cf06459dbd0ace16dcf2204742242e297c58fd3c57`.
The original failure receipt remains
`b865bd3e0b9e0fe89c7c0c3aca54061f41bb2d6dfb1b4a269dda8451b85dc35b`.

Fresh launch succeeded at `2026-10-07T08:47:19.0223372Z`: PID 1612, creation
`134358364309881895`, HWND 4063778, with the unchanged qualified native DLL.
Launch receipt SHA-256 is
`c3cba3c62bd44fc478f52121f7a508a58bbe7bb7083a3c77566fd6f3ba3a09a9`.
The compact receipts are retained privately under
`artifacts/guard-deploy/client-update-20261007/receipts`. Login and readiness were
pending at that checkpoint; later Praeda and B52 results are recorded above. This patch receipt itself makes no live-attack claim.

## Host .74 activated; bounded NPC cleanup unconfirmed - October 7

PR #78 merged after all 15 hosted checks passed, advancing main to
`f2ea8012876fd3624d813bd2b9c8cc80c5d6fdb8`. Exact installed host source is
`18769f1d8228c64503a773fc42e145ec6eca94b0` (0.3.74). It includes the worker
interpreter identity repair and bounded registry-read repair. Host .73 was not
installed separately. Native 1.8.51/source `2d1c928c5d9b3d130728dc936873df99de2edb51`,
the extension DLL and prepared client .14 remain unchanged.

Exact-source qualification passed 5,056 host tests (37 skips), all 13 stages,
466 installed-module checks and both native-profile IPC suites: 74 movement,
86 combat and 146 actor cases per profile. Qualification SHA-256 is
`59d687e3a85bad344e0527d68feaa543a2fdaecd4a3bff987c1b20e96c262ebd`;
wheel SHA-256 is
`e60eff219ee68b9fdbacccbb7d7eb558630afeee90194b773e1c1ef6057d353c`.

Apply and activation succeeded with 466 modules, 9,588 retained files, eight
validated generated worker records and zero client inventory changes. Manager
7548 (creation `134358189279629173`, parent 8780 creation
`134358189279033602`) is healthy with one paused worker and dispatch disabled.
The original game stayed open: PID 4128, creation `134358106481261509`, HWND
197180. These are receipt identities; actions still require fresh validation.

The installer now distinguishes pause from worker shutdown. After proving idle
operations and denied dispatch, it stopped the exact old manager handles before
publishing the production stop request to actual worker PID 5588/creation
`134358147964338484`. The worker and launch parent exited before apply. A narrowly
reviewed repair changed only two shutdown helpers and the plan, preserving the
prepared venv and original preparation receipt; 107 offline tests passed. No
worker kill, game stop, replayed job or rollback runtime was introduced. The old
.72 launcher wrapper's historical completion error is closed, with no pending
process or new mutation from it.

Twelve compact receipts were exported to the private diagnostic share
`host-update-20261007-0.3.74/receipts`. Activation receipt SHA-256 is
`2b735ff71be49119bf43bd0233e8148fb08733f7a29dabe54b2444023ab0034b`;
apply receipt SHA-256 is
`cffcb8d10be8444f9a52284d7dbdd442c79748043d577808de185c8b9e8e0e06`.
Verified retirement removed the obsolete .72 host (2,122 files) and its wheel,
totaling 49,799,696 bytes. Removal receipt SHA-256 is
`e5304c21e1ff26615bbadf307dbacb86caca9d8273265de6b484ecb5ecb7795b`.
A receipt-copy path typo was corrected without repeating retirement. User data
remained in place and no rollback runtime was retained.

Bounded run `1760e2eb1aa14762938a138ea3aec4c9` is **not passed**. Exact NPC
`23888/37` reached native health zero in trace sequences 88/89 after one positive
ATTACK queue. Shot to the Leg was queued; a later Beorc request entered with an
UNCERTAIN/PENDING result. Child STOP request 21 still reported PENDING/STOPPING
with closure NONE at sequence 91. Parent cleanup at sequence 92 remained
unconfirmed without a receipt. The helper reported `native actor cleanup remains
unconfirmed`; final list membership is unavailable. No watchdog or unexpected
interruption was reported. Native health zero does not establish kill credit,
completed cleanup, potion consumption or a complete buff-suite pass.

Private acceptance SHA-256 is
`245dcb935ace1465a7afbcdfb4514d449e19e76c7ae57aec580236a3b568b44c`;
events SHA-256 is
`ee9b74c0d616c25eb3befc494041397bcc71cd9d40f1490771505e8676fb4e27`.
The original evidence remains unchanged.

The next step at that historical checkpoint was the cleanup repair and fresh
readiness. The repair and optional potion diagnostics are now installed in B52
as recorded above; they do not change this failed run's result.

## Historical host .72 delivery - October 7

PRs #74 and #75 are merged; subsequent PR #76 also passed all 15 checks and
merged, advancing main to `1ee3d6b`. The installed host remains the exact .72
source below; newer source is not installed by this receipt.
Exact source `6d5abe5f74fd057fcf08c844027b6f58be9c5967` combines passive
PvE/buff dashboard status and exact native client admission. Native PvE and
travel no longer depend on screen calibration; process creation, executable,
window, foreground and native ownership checks remain required.

Host-only package `artifacts/host72/6d5abe5` passed 5,022 host tests (39 skips,
790 subtests), six required movement/combat/actor IPC validators across both B51
native profiles, and 466 installed-module checks. Independent review verified
the exact Git archive, wheel RECORD/source hashes and all 13 qualification steps.
Native source `2d1c928c5d9b3d130728dc936873df99de2edb51`, extension .51 and
prepared client .14 are unchanged; no native rebuild or game restart is needed.

Qualified SHA-256 identities:

- Host wheel: `027c50a8fe5c9db7127b0461907ca01d360e06888cf4c7338ca356232a93d730`.
- Source archive: `d3016ac7678387b42081c2d08224dd4d1224599d5a1c813f432267a1575090b9`.
- Qualification: `c7042663c3a92f62515555fe3d1140f75d076582e5142baed0426692e90f06b5`.
- Unchanged native DLL: `ce2f598e05bc696f3d9b3a4922f8a16ec2d6fba13dc7e62695026f0fa8edba0a`.

The corrected installer passed independent review and 59 offline tests.
Baseline validation required an explicit 32-bit module census and omission of
exactly two recognized running-engine outputs (`DoubleFusion/Engine.Log` and
`DoubleFusion/dfts.dat`) from byte equality. Native/static inventory, settings
and lifetime checks remain; failed diagnostics are preserved. No reinstall or
runtime rollback was performed.

The existing new .72 host then validated all 466 module files and produced
`host_prepared_not_switched` under final plan SHA-256
`5256906f229b6ee0ccbd1a9de00a33f9cd12e5addc9d6cb4f47707ac667bf44a`.
Apply and shortcuts then passed, verifying 466 modules and 9,586 retained files.
Manager .72 is running (PID 2740); the original game remains open. Manager
reconciliation keeps the exact client attached, so the reviewed installer now
pauses that binding and verifies idle operations/worker ownership instead of
requiring an empty slot list. An early activation postcheck saw an older heartbeat
than the new launch reservation; fresh settled status confirms their matching
worker UUID. A separately reviewed finalizer rechecks the existing manager
without restarting it. **Activation is now verified**: the finalizer wrote
`activation.json` (SHA-256
`347b395ef9a81c680b3a8da6381afca5640029bf93f1ae992ff07eaf5bc4d628`),
verifying 466 modules, 9,586 retained files and eight exact generated worker
records. Manager 2740 and one paused worker are healthy; game PID 4128 is
unchanged. The launcher misreported process completion after the Python verifier
succeeded; saved JSON matched its stdout and stderr was empty. The finalizer was
not rerun. Twelve compact receipts are retained locally under
`artifacts/bot-deploy/20261007-host72/receipts`. Verified retirement removed the
obsolete .71 host (2,116 files) and its old wheel, totaling 49,711,497 bytes;
removal receipt SHA-256 is
`053acac21d451db96a00169b5d2c52fa901c9ab69603a02d0d1c9de7100fcf46`.
Settings and jobs remain in place; no rollback runtime was retained.

Bounded player run `manual-pvp-a02f9c1042904e58bf44a8c225978ece` passed after
fresh native identity/readiness checks: one ATTACK, same-child NATIVE_STOPPED,
later SEEKING and parent LOCAL_RELEASED, with no errors, watchdog, unexpected
stop or residual list membership. The native path did not require selected-target
or screen-calibration authority. This establishes bounded action/cleanup behavior,
not damage, kill credit or automatic retaliation. Manual overlap testing remains
canceled.

The first NPC/buff attempt (`4fff8a61820046a38c0a0d6bb5deca95`) found no
eligible NPC and ended at its 30-second bound without a child context. Four buff
groups became PRESENT. Concoction request 4 was positively queued and locally
settled, but its native application journal remained pending, coverage MISSING
and the observed stack quantity five. These facts do not prove consumption or
remote application. Pending history prevented a duplicate potion request.

A later radius-200 run (`64a84fa23c01494395c0db6a18eb61ad`) observed exact NPC
`23884/37` health zero in trace sequence 114, followed by the recorded child
NATIVE_STOPPED receipt at sequence 116. A subsequent registry read raised
`NativeCharacterPopulationReadError: registry membership changed during read`;
the complete acceptance result is **not passed**, despite the earlier combat
and cleanup evidence. Parent LOCAL_RELEASED was confirmed at sequence 204;
there was no watchdog or unexpected interruption. The failed post-read leaves
final membership unavailable. Concoction application remains unresolved; neither
kill credit nor a complete buff-suite pass is claimed.

The subsequent combined .74 installation is recorded above. Potion response and
application remain a distinct unresolved investigation; no blind replay or
manual-overlap requirement is introduced.


## Installed .71/.51 shared ownership repair - October 7

PR #73 merged at `b17b003649fb927c5e5ef4ba0dec28d0a4968ff6` after all 15
hosted checks passed. Qualified source is
`2d1c928c5d9b3d130728dc936873df99de2edb51`. The production shared coordinator
now routes a prior buff's settlement to that exact policy proposal and preserves
any newer attack's ownership. A correlated pending reply remains progress while
another proposal waits; lost or unavailable replies still require bounded cleanup.

Package `artifacts/b51/a83dc62b` passed 4,943 host tests (37 skips), both native
profiles with 224 passed tests / 126 required gates each, and 73 movement / 86
combat / 146 actor IPC cases per profile. Independent qualification checked all
110 artifacts and 82 stages. Qualified SHA-256 identities:

- Full DLL: `ce2f598e05bc696f3d9b3a4922f8a16ec2d6fba13dc7e62695026f0fa8edba0a`.
- Wheel: `b0d0bf32e6d7b06909557830d07d32fe6b5089edc2acd3916eceb1bb164c86e6`.
- Archive: `c6c62f0a726cbd87ab1c320ea8b8a265081bdd69b718b35058e3809dc0e68a6a`.
- Receipt: `613e875a58d34fac2d2524a475c92ccbb3855cfa4ad63ef1bde4cab38c4d6a8c`.

**Installation and activation passed.** Apply verified 463 host modules,
9,587 preserved files and exactly one client DLL inventory change. Manager 5868
is healthy; all five shortcuts and startup preflight passed. Prepared client .14,
corrected display preferences, settings and jobs remain in place.

Launch at `2026-10-07T01:37:36.2173995Z` verified the qualified DLL in PID 4128,
creation FILETIME `134358106481261509`, HWND `197180`. Passive readiness was at
login/loading, so no .51 live gameplay acceptance is claimed. Process identities
are receipts; a fresh session check is required before action.

The obsolete .70 host (2,116 files / 48,021,726 bytes) and two .50 guest payloads
were removed after exact ownership checks, totaling 50,839,643 bytes. No rollback
copies were retained. Four old .50 host/share staging binaries were also removed,
totaling 5,635,834 bytes. Twelve compact receipts and seven independently verified
installed-file hashes are retained under `artifacts/bot-deploy/20261006-b51/receipts`.

Open PR #74 publishes passive production PvE/buff status at
`5da11d111cdbca81cc65ed25147ee75ed09a67d3`. Independent review and 335 affected
tests passed, including exact-operation storage, stale capture/worker handling,
missing-status presentation and dashboard rendering. Hosted CI found an outdated
test call missing the required operation argument; a fixture-only correction is
in progress. Hosted checks are not yet reported passing, and this status feature
is not part of the installed package. Next: fresh exact-identity preflight and
bounded authorized player attack/cancel validation while `DayOwl` is available,
followed by shared buff/combat handoff validation. Sustained renewal and alternate-form reuse remain unproved;
manual overlap testing is canceled and automatic retaliation remains disabled.

## Installed .70/.50 renewal repair - October 6

PR #71 merged at `578f5f933cf5770764c79c5c5dc0ceea19e786ec` after all 15
hosted checks passed for exact source
`a99dc978a1a083881348ba55ae36974f4442d20e`. A reproduced ordering defect could
recreate application suppression when local settlement arrived after PRESENT
coverage had already been observed, preventing renewal after coverage became
MISSING. The policy now remembers validated application evidence for the exact
proposal while retaining local ownership until its typed settlement receipt.
The regression suite covers disappearance before settlement and later renewal.

Package `artifacts/b50/f4d9e515` passed 4,928 host tests with 38 skips, both
native profiles (224 passed / 126 required gates each), and 73 movement / 86
combat / 146 actor IPC cases per profile. Independent review verified all 110
artifacts, 82 stages, exact Git source, wheel RECORD/source stamp, both DLL
versions, original/prepared .14 client bindings and seven bootstrap writes.
The extra host skip versus .69 was the byte-identical
`test_replay_does_not_publish_and_return_live_rebinds_controls`, whose Tk fixture
reported the display unavailable; all other skips match. Known optional
transparency findings remain unchanged and separate from required gates.

Qualified SHA-256 identities:

- Full DLL: `d102f6b45f784accdcd1839443c9fe51d5761cdb50015899c14f1a7e26b24717`.
- Wheel: `7024d623532905f98d9693fad9c7dd62bb8302ce7ccecf4045d76785dda21dc4`.
- Archive: `f02e9e907e2d2bfe2d330c84228293b985a86d89b1d0b0fda7366d58695ebdbf`.
- Receipt: `81c67fa4264e580ee951df22398628039804a49bc8577808c7d3dd93070df6df`.

The installer passed 20 offline tests, PowerShell parsing and independent final
pin review. Compact private evidence is under `artifacts/bot-deploy/20261006-b50`.
After user-confirmed closure, **installation and activation passed**. Apply
verified 463 host modules, 9,585 preserved files and exactly one client DLL
inventory change. Manager 6076 activated healthy; all five shortcuts and startup
preflight passed. Official/prepared .14 assets, settings and jobs were preserved.

Launch at `2026-10-06T20:48:39.2159949Z` verified the qualified DLL in PID 8616,
creation FILETIME `134357933071546966`, HWND `1770578`. Passive readiness reported
login/loading, so no gameplay action or in-world acceptance is claimed. These
identities are receipts, not continuing session authority.

The exact obsolete .69 host (2,116 files / 48,019,845 bytes) and two .49 guest
payloads were removed after ownership and activation checks, totaling 50,837,562
bytes. Four old host/share staging binaries totaled another 5,635,434 bytes.
No fallback copies were retained; settings, jobs and diagnostic evidence remain.
Twelve compact receipts and seven installed-file hashes are in B50 `receipts`.

The buff-only cycle helper passed 42 tests and independent final hash review;
its eight qualified dependencies are staged. Fresh in-world readiness passed,
and run `3438e509d24a4bb89ebf557ba9e1403b` ended at the bounded observation ceiling
without errors, interruption or watchdog. Independent review correlated 629 native
command/receipt pairs and 597 complete canonical frames under one parent/Grant.
Exactly four SELF_POWER requests were sent: Precision, Beorc, Rat Shape and
defensive stance. Concoction coverage was already present; no USE_ITEM, Skree,
Shot, ATTACK or target context was sent. All five groups remained PRESENT through
the last capture. STOP_OWNER confirmed CLOSED / LOCAL_RELEASED. No group became
MISSING after PRESENT, so renewal and alternate-form reuse remain inconclusive.
Evidence is under the B50 buff-cycle shared directory; the compact local summary
records original hashes.

The user then reenabled controlled PvP: read-only native census uniquely observed
`DayOwl` on Wonderbane, key `5845459/53`, approximately 8.55 units away. Census
identity must be refreshed before action. At that checkpoint, ownership repair
PR #73 and passive dashboard status were still in progress. PR #73 is now merged
and installed as .71/.51 above; dashboard status is published separately in open
PR #74. The historical B50 observation does not prove a renewal cycle.

## Installed .69/.49 buff scheduling repair - October 6

PR #69 merged at `490af652eaee83dd1914869ce99da9c908049f37` after all 15
hosted checks passed; exact qualified source is
`439d074051edc627ad8ba81a84113a345d2fd42c`. The .68 live run below exposed a
scheduler stall: after Beorc settled, fresh observations kept semantic revision
17 because the facts were unchanged. The policy incorrectly required that
revision to increase before submitting another buff. It now requires a later
validated native capture sequence, preserving semantic equality, lifetime,
immutable pending action, duplicate application and admission-refusal guards.

Package `artifacts/b49/4f564b4d` supplies host **0.3.69** / native **1.8.49**.
It passed 4,909 host tests with 37 skips; each profile passed 224 native tests,
126 required gates and 73 movement / 86 combat / 146 actor IPC cases. Independent
review verified 110 artifacts and 82 stages, both .14 client images, wheel source
and DLL identity. Known optional rendering findings are unchanged. Full DLL
SHA-256: `d4961bf0d50613d9d9e339691a4ef8ae0c29316c57c5842ed7f4e62cf7c36fae`.
The installer passed 20 offline tests and independent final pin review; the
bounded encounter helper passed 138 tests against the exact package. Private
receipts are under `artifacts/bot-deploy/20261006-b49`.

**Installation and activation are verified.** After fresh closed-client
verification, apply reported `updated_verified_not_launched`: 463 host modules,
9,584 preserved files and exactly one client DLL inventory change. Prepared
client .14, corrected display preferences, settings and jobs remain in place;
no rollback copies were created. Manager PID 9512 activated healthy with all
9,584 retained files verified. All five shortcuts and startup preflight passed
while the game was closed.

Launch at 2026-10-06T20:00:57.2271144Z verified the qualified DLL in PID 3456,
creation FILETIME `134357904517155349`, HWND `2163786`. Fresh in-world passive
readiness reported ready, owner NONE, scene 1 and no cleanup pending. These are
receipt identities, not continuing session authority.

The obsolete .68 host (2,116 files / 48,016,130 bytes) and two .48 guest payloads
were removed after verified activation, totaling 50,833,456 bytes. Four exact
old .48 host/share staging DLL/wheel files were then removed, totaling 5,634,652
bytes. Settings, jobs and diagnostic evidence remain preserved; no rollback
copies were retained. The B49 `receipts` directory contains 12 compact receipts
and seven independently verified installed-file hashes.

Two bounded .69/.49 runs **passed** after the initial resource-gated preflight.
Run `d6b24f1051214adfa054979c2d4b1b10` observed exact NPC `23887/37` native
health zero at sequence 110 after two positively queued ATTACKs. Precision,
Beorc, defensive stance and Rat Shape were submitted, alongside Shot and the
attacks; all five coverage groups were PRESENT. Concentration coverage was
preexisting: this run sent no USE_ITEM or Skree request. Independent review
correlated all 134 wire command/receipt pairs and the exact death/cleanup proof.

Run `d073ec9e5a58464b982990d21d161a67` then observed exact NPC `23886/37`
native health zero at sequence 69 after one positively queued ATTACK. Its only
action submissions were Shot and ATTACK: all five buff groups were already
PRESENT, and no duplicate buff was submitted. Both runs confirmed child
NATIVE_STOPPED and parent LOCAL_RELEASED, with zero list membership and no
errors, watchdog or interruption. Fresh readiness afterward was alive, unowned
and clean. These bounded results validate the scheduling repair and subsequent
run's suppression of duplicate buffs; they do not establish new potion use,
Skree application, expiry/reuse cycles, server kill credit or skill consumption.
Private evidence is retained on the `bot-actor-provisional-encounter-20261006-b49`
diagnostic share under the exact run IDs above.

Next: sustained expiry/reuse validation, then controlled PvP with an available,
agreed player. Manual potion-overlap testing is not required; automatic
retaliation remains disabled pending authoritative session provenance.

## Historical .68/.48 startup repair deployment - October 6

PR #67 merged into `main` at
`9cf9f20a322f4ce0b199c7806f509c1aa2c991cb` after all 15 hosted checks passed.
Exact package source `7aca53e3e6a66bbcddebdc6349ef96f86bbfdfaf` supplies host
**0.3.68** / native **1.8.48**. The stationary startup repair is merged and
**applied and verified**: 463 host modules, 9,583 preserved files and exactly one
DLL inventory change. Both client .14 executables, official data, corrected
1920x1080 preferences, settings and jobs remain in place. No rollback copies
were created. Manager PID 9108 activated healthy; all five shortcuts and startup
preflight passed. Launch at 2026-10-06T19:13:40.6492763Z verified the qualified
DLL in PID 8832, creation FILETIME `134357876109226569`, HWND `2687194`. Fresh
passive readiness reported ready with no actions sent. These are historical
receipt identities, not continuing session authority. The bounded live run below
completed NPC combat and cleanup but remains partial for buff preparation.

Package `artifacts/b48/64bc2349` passed 4,893 host tests with 37 skips. Each native
profile passed 224 native tests, all 126 required gates, 73 movement IPC,
86 combat IPC and 146 actor IPC cases. Independent verification checked all
110 indexed artifacts and 82 stages. The known image-wrapper skips remain
separately covered by actual-image probes, with only the recorded optional
rendering findings. The full DLL SHA-256 is
`d0fad978a7813f75eac3e0c2a0f90f483d35874b215c062a7885e658767e582e`.
Private qualification and deployment receipts are under
`artifacts/bot-deploy/20261005-b48`. Its `receipts` directory contains 12 compact
receipts and seven independently verified installed-file hashes. The obsolete
.67 host (2,116 files) and two .47 guest payload binaries were retired after
verified activation, totaling 50,832,946 bytes. Four exact old .47 host/share
staging DLL/wheel files were then removed, totaling 5,633,626 bytes. Settings,
jobs and diagnostic evidence remain in place; no fallback builds were kept.

The earlier .67 run observed all five buff groups PRESENT; its NPC acceptance
remained incomplete. Manual potion-overlap testing was canceled by the user.
The .68 run `actor-full-encounter-provisional-f6b83d15cdee407d9962c5a2b87e95f0`
remains **partial**. Shot queued, followed by one positively queued ATTACK; the
exact NPC `23886/37` reached observed native health zero at sequence 168. Child
cleanup confirmed NATIVE_STOPPED and parent cleanup LOCAL_RELEASED, with no
interruption or watchdog and zero retained list membership. Fresh readiness
afterward showed an idle, unowned client with no cleanup pending.

Concentration potion, Precision and Beorc coverage were PRESENT. Transform and
defensive stance remained READY/MISSING near 44 seconds. The capture-freshness
repair above addresses the identified scheduler stall and passed the two bounded
live runs recorded above. These observations do not establish server kill credit or skill
consumption. The prior evidence remains unchanged.

## Historical .67/.47 client update and live attempts

PR #65 merged into shared `main` at
`03375a9b989aa4c01735ce70d91a4b8218744e18` after all 15 hosted checks passed.
Host **0.3.67** / native **1.8.47** are qualified from exact source
`a34a57ff9037018765a9ce6e3614b5792c5e6e43`, including the two reviewed client
1.3.38.14 hashes while retaining signature checks and unknown-image rejection.
Installation and launch were **verified**: host .67 / native .47 ran with
prepared client .14. Installation verified 463 host modules, 9,578 retained files
and exactly three client inventory changes: executable, CObjects cache and DLL.
Settings and jobs remain in place. Manager PID 6072 activated healthy and unbound,
with only the expected dispatch-permit revocation. Five shortcuts and startup
preflight passed.

Launch at **2026-10-05T00:34:41.1329652Z** verified the qualified DLL in PID 7516,
creation FILETIME `134356340764063745`, HWND `1115034`. Passive readiness was
**not ready** at login/loading; no gameplay action was issued. Subsequent in-world readiness passed for the same process creation and recreated
HWND `459704`, with a 1920x1080 client area at DPI 96. These process values are historical
receipt identity, not continuing session authority.

The exact-source package `artifacts/b47/d2707a93` passed 4,893 host tests with
37 skips. Each native profile passed 224 native tests, all 126 required native
gates, 73 movement IPC, 86 combat IPC and 146 actor IPC tests. The three skipped
CTest wrappers (movement image, cue binding and sky binding) each have separately
executed actual-image probes. The two known optional transparency findings per
profile are separate from those wrapper skips. Independent package
verification checked all 110 indexed artifacts and 82 stages.

| Qualified artifact | SHA-256 |
| --- | --- |
| Package archive | `9509c04d7f74d02a1ae238a8371dc8fa798375c6e784898915ee1ece72d74820` |
| Full-profile DLL | `2190c30b754f392021dd460b7b1d0e20e6d0cbf5eb14d58c06b0e95684586f88` |
| Host wheel | `5c972e988cc802e18c11f0fe6fdf83e463ac0dd95e95c4ccbb1bc6a25959026e` |

The official manifest fetched at 2026-10-04T23:57:17Z contains 211 files and has
SHA-256 `fa73867708fef4e53acbbdb173897d5eacc3d31f10cf66c43e96896025d56eee`.
Compared with the reviewed .13 manifest, exactly two files change and none are
removed. Metadata version strings remain insufficient to identify the client;
the file hashes and embedded executable version establish this patch.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| Official `sb.exe` | 21,143,613 | `e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e` |
| Prepared `sb.exe` | 21,143,613 | `78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903` |
| `cache/CObjects.cache` | 5,432,558 | `5979b544426669e1ffd89fdf95a7a7800d1b42a6cfc7840c942efed1656ff2f7` |

The official executable differs from reviewed .13 by one byte at file offset/RVA
`0x12dc18c`: ASCII `3` becomes `4` in the embedded version. Every other byte,
including executable code, headers, imports and relocations, is identical.
The `.text` SHA-256 remains
`5cab14307005f6ebdfa268107aa2a1aeba35cb071b17cdf3d01665a3f3294607`.
No inventoried calibration anchor intersects the changed byte. All seven loader
writes resolve at their reviewed locations, without relocation or ambiguity.
The derived prepared .14 image likewise differs from prepared .13 only at that
version byte. This proof does not authorize unknown future images.

The pre-deployment baseline had both games closed and the existing manager
healthy with no bound slots. The original client already matched official .14
and its new CObjects cache; Vendor Test matched prepared .13 and the prior cache.
Deployment verified those different starting states. Both clients retain the
unchanged official Config.wpak; Vendor Test now has prepared .14 and the new cache.

The user resolved the cursor offset and corrected the original display settings
to 1920x1080, fullscreen, hardware cursor. Those three settings were carried into
the closed Vendor Test client, with all other preference bytes preserved. Their
live behavior on the updated Vendor Test client remains to be checked.

Follow the [deployment policy](deployment-policy.md): preserve settings, jobs and
historical diagnostics in place; create no rollback runtime or archive. The
October 4 capacity audit found C: full and retired obsolete deployment assets
from five older clients. Receipts record 798 removed files / 11,667,960,650 bytes,
with 180 settings/log files verified unchanged. Those capacity removals did not
alter the then-active .66 installation. After .67 activation, exact ownership
checks retired the obsolete .66 host (2,116 files) and two .46 guest payloads,
totaling 50,827,934 bytes. Four obsolete host/share staging files totaled
5,631,830 bytes. No rollback copies were retained.

Retirement of 21 additional old Python environments remains blocked by automatic
approval review pending explicit user approval; none is recorded as removed. The separate non-test VM guest audit could not
authenticate and
its existing VM snapshots were not changed.

Private official inputs, binary comparisons, deployment baseline and completed
qualification receipts are under `artifacts/guard-deploy/client-update-20261004`.
Its `receipts` directory contains 12 compact deployment receipts and seven
verified installed-file hashes.
No private binaries, captures or credentials belong in source delivery.

The user removed potion-overlap testing as a requirement: potion and other buff
order are immaterial. The October 5 automatic run confirmed all five groups
PRESENT, including the concentration potion. Its NPC phase sent no attack: the
first candidate was NEVER_BOUND during preparation, and the bounded helper
refused a different candidate afterward. Parent cleanup was LOCAL_RELEASED.

The next run was rejected before actor ownership or any NPC action. Retained
native input evidence records a 313 ms update interval revoking movement
generation 5 to 6 with reason `stalled`, no keys, unchanged scene and window.
Fresh readiness afterward showed owner NONE, no cleanup pending and Umbra alive.
HISTORY_EXPIRED replies are not positive cleanup receipts.

The stationary startup repair is now merged and applied as recorded above;
activation and launch are verified; current live findings are recorded above.
Private original traces remain unchanged.
Automatic retaliation remains disabled pending authoritative character-session
provenance. The prior bounded NPC/buff acceptance remains historical .66 evidence.
