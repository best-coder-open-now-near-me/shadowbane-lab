# Queued native skills and delayed-stop settlement

Installed host **0.3.60** / native **1.8.40** use exact qualified package source
`f0263c38ef36874da0e68e0aa5e0c8775550e618` with official client **1.3.38.13**.
[PR #54](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/54)
merged at `89f58cdbb50c2ef8bc8d80f0583897ac982f80f4` on October 1,
17:41:37 UTC after all 15 hosted checks passed at approved head `3b5e628`.
Installation, manager activation, five shortcuts and startup preflight passed.
The exact loaded-DLL launch check passed. After Umbra login, bounded follow-through
queued the skill and attack, observed the exact NPC at zero health, and confirmed
native cleanup. The original partial harness result and supplementary review are
kept separately below. Recovery across encounters remains open.

The normal checkout is on that main merge. The reused bot-integration worktree is
on `codex/native-initiation-deployment-20261001` for this installation receipt;
[draft PR #55](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/55)
targets main and remains unmerged. PR #53's complete tip
is included in #54, and GitHub marked #53 merged at 17:41:38 UTC. PR #50 remains
closed as superseded; its relevant historical facts are incorporated while its
branch is retained because its exact tip is not an ancestor of main. The completed
registry-backed-population and native-stance-deployment branches were retired
locally and remotely after tip ancestry checks. The bot-runtime worktree is clean
and detached at `origin/main@89f58cd`, available for reuse.

The earlier .59 bounded gate passed one Shot to the Leg SELF_POWER request,
one same-engagement NPC ATTACK and confirmed NATIVE_STOPPED cleanup. It proves
local queue admission and cleanup, not server consumption, snare or damage
attribution. Umbra/Wonderbane retains basic policy with opener 563795161 at
revision 1. The .60 follow-through used fresh login and identity checks;
earlier .59, .58 and .57 observations are historical evidence.

## Ownership and behavior

Skills are resolved from the exact character session's learned entries and native
definitions. Name lookup requires a unique exact display/internal name; a numeric
ID also requires positive learned rank. Reviewed image identities and stable
bounded memory reads are mandatory. Native callbacks revalidate action admission.
UI selection, hotkeys, hotbar/CFG and system messages are not combat authority.

An actor-directed skill keeps the NPC engagement binding while using the actor as
its actual skill recipient. Positive native queue acknowledgement advances to the
attack against the same bound NPC; there is no fixed opener delay. A queue receipt
does not prove server consumption, impact or snare application. Cancellation stops
owned automation and does not purport to remove a server-applied effect.

Character settings are separate durable user data keyed by native server and
character name. Missing settings use basic combat without an opener. The manager
and chat listener read the current character's choice instead of assuming an
assassin. `client pve-settings --process-id PID --opening-skill "Shot to the Leg"`
validates and saves the native skill ID; no input or lease is acquired. An explicit
`--policy proc-assassin` remains available for characters configured for it.
`client run-pve --opening-skill NAME` overrides the saved opener for a run;
`--no-opening-skill` suppresses it. Settings changes do not alter an active run.

The delayed-stop correction preserves only cleanup under the same exact owner.
Terminal cancellation blocks new work immediately and initiates native stop while
maintaining the existing lease for a bounded settlement. Normal engagement cleanup
can release its obligation and allow another encounter on the same owner. An
absolute three-second combat settlement budget covers STOP_ENGAGEMENT, PAUSE
and fence revocation/closure; expiration never means cleanup succeeded. The
subsequent terminal movement-owner STOP is separately bounded by the session
transport timeout and may retry once with the same request identity. Existing
focus, lifetime, scene and owner guards remain.

## Historical .58/.38 qualification and deployment

Package `artifacts/b38/ab7c1a59` is acceptance eligible at source `05c888a4`.
Independent verification checked 78 artifact hashes, all 52 build steps, exact
Git source, wheel contents/source stamp, both DLL versions and all seven unchanged
prepared-client writes. Archived host tests passed **4,203 cases**, with 35 explicit
skips and 801 passing subtests. Each native profile passed **202 native cases**,
**85 combat IPC cases** and **72 movement IPC cases**, including the mandatory
parent-cancellation test that retains the exact owner through delayed cleanup.
Three generic CTest image skips were covered by explicit original/prepared image
gates. Required gates passed; the two known optional renderer-transparency
failures per profile remain recorded separately.

| Artifact | SHA-256 |
| --- | --- |
| Acceptance archive | `a05d6c37e5fd73c0bd39587cb7980a138aa215a34708022c324489f417fe6b78` |
| Receipt | `3147b87d86986bc42a0b089c9d581eb8e159495d34da493a108da36e10a5a930` |
| Full DLL | `b139b5ce17584e65cda1acd82bb58d65a7004f785fea5d69a6d45ba19a5a3e17` |
| Host wheel | `2aab077414fbf99368c2a5b58ec5bff239e6bc0ca7641410841374d57b6a3d40` |

Installation verified 454 module files, 9,567 retained settings/record files,
one client DLL inventory change, five shortcuts and launch preflight. Manager
activation was healthy and unbound at observed PID 2908. Launch at
04:17:51.4923419 UTC verified the qualified DLL in PID 460, creation FILETIME
`134353018625847816`, HWND `5243554`. These are recorded observations, not
continuing authorization. Initial passive readiness awaited login; the later
bounded results below were collected after fresh readiness.

The inspected obsolete .57 host contained 2,090 files and 47,557,363 bytes;
inventory SHA-256 was
`7fb2c3caddce9084623d7c3f8fc2dd7aa249bf7d2a6883e5f794db45494e9508`.
It and two exact old guest payload binaries were removed, totaling 50,226,673
bytes. No rollback runtime or payload copies were retained. User settings, jobs
and diagnostic evidence remain in place. Twelve compact receipts and seven
installed-file hashes were verified under private
`artifacts/bot-deploy/20261001-b38/receipts`; private captures are not published.

## Historical .58 NPC results and combat-mode prerequisite

The bounded basic NPC gate passed on exact installed source `05c888a4`. The
production-selected NPC was validated by native key/token within the unchanged
120-unit camp boundary. One ATTACK had a correlated CLIENT_OUTBOUND_QUEUED receipt,
then terminal cleanup returned CLOSED with NATIVE_STOPPED, mode 1, action state 1
and no combat target. No combat owner remained, final manual-list membership was
zero and the watchdog did not fire. The explicit harness stop followed the queued
attack. This proves local queue admission and cleanup, not a server hit or later
PvE recovery. The compact private result is
`artifacts/bot-deploy/20261001-b38/npc-basic-result.json`.

The queued-skill gate did **not pass**. Shot to the Leg resolved from Umbra's
current learned definition as power 563795161, rank 40, actor recipient. Its
SELF_POWER submission reported native entry but UNCERTAIN outcome and no outbound
queue evidence. Subsequent updates queried the same action; no followup ATTACK
was submitted. Cleanup ultimately returned NATIVE_STOPPED and retained no owner;
list membership was zero and the watchdog did not fire. The diagnostic also
recorded native owner revocation: expected Grant generation 7, sampled generation
8 with no owner. Private `npc-skill-result.json` is retained beside the basic
result. No skill consumption, snare application or server acceptance is claimed.

The user clarified that weapon skills require combat mode before activation.
Source review confirmed the .58 attack entry entered combat mode, while its
power entry did not establish that prerequisite. A later exact-session passive
read at 15:28:51 UTC confirmed Shot's native definition field `+0x1F0 = 1`, with
actor mode 1 and action state 1. The reviewed classifier requires combat mode for
requirement 1. The read invoked no native function or input and acquired no lease;
its private receipt is `skill-stance-result.json`, definition SHA-256
`7c70f270975fd819291090f887e8e9487c20156f1c0539525e8f507b5b161f1f`.
This confirms the definition/prerequisite mismatch at that observation; it does
not retrospectively establish the sole cause of the earlier failed attempt.
Host **0.3.59** / native **1.8.39** introduced the merged combat-mode
correction, with its historical qualification and live results below.
Owner revocation was a distinct later
event; the sampled generation/no-owner state does not identify its trigger.
Existing fail-closed handling stays in place, with no automatic restart.

Combat-mode preparation belongs inside the native power invocation under the
same actor, Grant, engagement and fence. Host policy continues to propose the
configured numeric skill; only its correlated queue acknowledgement can advance
the attack. UNCERTAIN retains the exact command for status/cleanup. Native
callbacks must revalidate ownership after any mode transition and preserve entry
history. No new hotkey, configuration flag or arbitrary host delay is required.

## Historical .59/.39 qualification and installation

Exact package source `e90d2f64ea49df5af94365012548266e6829e3a1` is retained
in the PR #52 main merge. Subsequent qualification and deployment documentation
do not change that package source identity.
Package `artifacts/b39/e2bdddda` passed 4,203 host tests with 35 explicit environment
skips and 801 subtests. Both native profiles passed 202 native tests, 72 movement
IPC tests and 85 combat IPC tests, including delayed parent-cancel cleanup.
The three generic image skips were covered by explicit private image gates.

The new required-mode probe executes the native predicate in 48 cases against
both original and prepared client 13 for each profile. It proves signed mode
eligibility, not native synchronization or all power admission. Existing power
entry probes and 2,048-case melee control-flow probes also passed both images.
Independent review accepted the native change, probes and deployment procedure.
All 56 package steps and 82 indexed artifact hashes were verified. The two known
optional renderer transparency diagnostics remain recorded separately.

- Archive SHA-256: `776822bd98f7a4da2afaab90e7726a8e90610732881cc57e51460efb075df3fe`.
- Receipt SHA-256: `cbc3b1850d3e0493e8075799ab2d041e28b1be0c5cd74fe4beefc64c27406c05`.
- Full DLL SHA-256: `a53afdffb2e756f349ae065c03c000563eb765632f4a0e88db2b970163f860c2`.
- Wheel SHA-256: `479f0510919181f2bc776529d955ade9cd4972d2cb910145ba0937688c302812`.

Installation verified 454 module files, 9,568 preserved files and exactly one
client DLL inventory change. Manager activation was healthy and unbound at
observed PID 4988; all five shortcuts and launch preflight passed. Launch at
15:58:05.8330686 UTC verified DLL `a53afdff...f860c2` in PID 10164, creation
FILETIME `134353438781499398`, HWND `3015398`. Initial passive readiness showed
login/loading; the later bounded test used a fresh Umbra session. These recorded
process identities are evidence, not continuing authorization.

The inspected obsolete .58 host contained 2,098 files and 47,646,848 bytes,
with inventory SHA-256
`41a0beb2bafde8bf2a4cd4821a63097ae9f7c9eb1dc886fd52cf26e90bd7270d`.
It and the exact old .38 DLL and .58 wheel were removed, totaling 50,327,078 bytes.
Settings, jobs, diagnostic evidence and compact receipts remain in place; no
runtime rollback copies were retained. Twelve compact deployment receipts and
seven installed-file hashes are retained under private
`artifacts/bot-deploy/20261001-b39/receipts`.

## Live .59 skill/attack/cleanup pass and saved opener

The bounded gate passed on the exact installed package. An earlier preflight
below the 75% health threshold sent no action; fresh checks passed after natural
recovery. In the successful run, Umbra's native key was `[4050960,53]` and the
production-selected NPC key was `[23885,37]`, within the unchanged 120-unit camp.
SELF_POWER request 1 for learned Shot to the Leg (563795161, rank 40) returned
CLIENT_OUTBOUND_QUEUED in mode 2/action state 1. ATTACK request 2 then queued in
mode 2/action state 2 against the same engagement, binding and Grant generation
3/scene 1. Terminal STOP request 3 returned NATIVE_STOPPED, mode 1/action state 1
and no combat target. The owner was released, final manual-list membership was
zero, and no error or watchdog firing occurred. The parent cancellation was the
intentional harness stop after the attack queued; the native dispatcher reported
no interruption.

Private `artifacts/bot-deploy/20261001-b39/npc-skill-result.json` records this
sequence. It proves skill-request and attack queue admission plus native cleanup,
not skill consumption, snare application, server-accepted damage, a kill or later
PvE recovery. No UI selection, hotkey or combat-log authority was used.

The production settings service then saved Umbra/Wonderbane's basic policy with
opening skill `563795161`, changing revision 0 to 1 after fresh native learned-rank
validation and exact-session checks. Readback matched; saving sent no gameplay
action. Private `opener-settings-result.json` records the change. Subsequent PvE
runs load this generic opener and recheck current native eligibility; no Shadow
Touch or assassin policy is implied.

## Follow-through blocked before gameplay

The user reports that the previously attacked NPC died and that no manual input
was occurring. This is a user observation, separate from the bounded gate's queue
and cleanup receipts. The planned follow-through itself has **not run** and sent
no gameplay action: its read-only preflight observed native action state 2.
Subsequent passive samples under the same exact Umbra process lifetime confirmed
mode 1/action state 2, a zero in the field then labeled pending, no AF8 combat
target and no automation owner. Those fields do not identify a cast, prove idle,
or attribute a later action.

The production heap-scanned population reader also rejected duplicate native
object identities on two reads. Private `population-duplicates-result.json`
records the prior NPC key `[23885,37]` with the original token and health zero,
plus a different-token object with that same key and health 400. A separate,
complete passive world-registry census in `duplicate-registry-result.json`
contained only the new live object; the old dead heap object was absent. Both
receipts are under `artifacts/bot-deploy/20261001-b39`. This establishes stale
heap-scan membership alongside a registered replacement consistent with respawn;
it does not show two currently registered targets. A matching key cannot transfer the old engagement to a replacement token.
The passive census does not retain a native reference or authorize any action.

Registry-backed population is implemented at `6eecda8` on
`codex/registry-backed-population` in the reused bot-integration checkout. Its
schema-4 profile admits only explicitly qualified images; complete bounded
registry rereads replace heap membership, and registered actor/key/address
checks surround field reads. Dispatch still reacquires a retained native
reference on the owner thread. Duplicate registry identities, observed churn,
and budget expiry reject the observation. Same-key respawn cannot transfer an
old engagement or manufacture death/kill credit. Independent review, 87 focused
and 79 consumer/health tests, repository Ruff, and the full host suite passed:
4,251 tests, 801 subtests, and 36 skips. PR #54 subsequently merged this
correction and the full PR #53 documentation tip. The correction is installed
in .60/.40 after the combined qualification below.

The subsequent persistent-action audit established the following correction.
Exact client code identifies
`actor+0x9BC` as an animation-event index rather than the boolean pending-action
field previously used by the reader. Native state updates can set mode and action
independently; action state 2 alone is not proof of casting. The actor's `AE4`
task pointer can survive task destruction and is not ownership evidence. Native
power recovery uses `actor+0x67C` and the client's own clock, but elapsed recovery
alone is not yet qualified as permission to interrupt an existing cast. These
findings led to the coherent observation/admission correction below. No
follow-through action ran on .59/.39 after the blocked passive preflight.

## Merged native initiation correction

The native update guard is committed at `8090c176fd33a027c503afaabc50bb0112b0a2a7`
and included in merged PR #54. Native service runs only at the outermost update;
nested
callbacks still forward to the client. The boundary spans the original callback
and restores thread-local state on SEH and C++ unwinds. Independent review and
six focused native tests passed.

The installed host/native correction preserves pending initiation using stable
native state `+0x10` and the bounded power-protocol ID vector. Animation frame,
animation-event index, and action state remain telemetry. Clear initiation does
not prove that effects or projectiles have finished, or replace action-specific
native legality. No fixed recovery or animation delay is intended.

The queued actor-skill follow-up also needs native request provenance. An exact
queued receipt and matching later ID multiplicity alone cannot distinguish the
original vector entry from a remove/re-add between updates. Review identified
this gap before qualification; the ID-only allowance is not accepted for release.
The implemented correction captures an epoch through the positively queued native
follow-up and preserves that exact epoch until attack entry. Reviewed ordinary
power entry, local follow-up, incoming protocol append and removal invalidate
older epochs. A same-ID remove/re-add cannot restore the earlier allowance.
Counter exhaustion disables the allowance. This global epoch conservatively
invalidates on other actors' observed power events too.

Ordinary native Use calls retain a thread-local in-flight guard through their
original call and restore it on SEH/C++ unwind. Nested automation admission and
cleanup defer before the native call publishes initiation state. The outermost
update guard also spans the original client callback. Native cleanup requires
mode 1, no combat target, and clear initiation; action state 1 is not required.
Cleanup does not imply that projectiles or server effects have ended.

The exact .13 mutation census includes constructor/destructor storage changes,
which are excluded while the same native actor reference and lifetime are held.
The contract covers the reviewed client and supported native entry paths, not
arbitrary injected memory writers. Prepared .12 is explicitly rejected by this
combat observer; other features retain their own image qualification.

Independent host/native reviews passed. Host checkpoint `0e218bc` passed 4,304
tests with 788 subtests and 36 skips. Native focused tests and the original and
prepared .13 initiation probes passed; each initiation probe executes 23 cases.
Host .60/native .40 contain the correction. Exact-source qualification and
installation and bounded live follow-through are recorded below.

## Qualified and installed .60/.40

Exact package source `f0263c38ef36874da0e68e0aa5e0c8775550e618` is retained in
the PR #54 main merge. Package `artifacts/b40/b1c83d60` passed **4,325 host tests**,
**788 subtests**
and Ruff, with 35 explicit environment skips. Each native profile passed **204
native tests**, **72 movement IPC tests** and **85 combat IPC tests**. Three
generic image skips per profile are covered by explicit private image gates.
The five image-admission cases require rejection of unqualified .12 images and
admission of prepared .13 for the new combat semantics.

Both original and prepared .13 images passed the 23-case native INITTIME/protocol
probe in each profile. The expanded native power observer, 48-case combat-mode
predicate and 2,048-case melee probes also passed. Package verification checked
all 60 steps, 104 required native gates, 86 indexed artifact hashes, exact Git
source, wheel source/RECORD, both DLL versions, IPC execution and all seven
unchanged prepared-client writes. The two known optional renderer-transparency
failures per profile remain recorded separately from required acceptance gates.

- Archive SHA-256: `3bedee0961e994e0c0e1f8c34f76788fa6a2c1ae0f8edb2c55ce44f7a0afd1c5`.
- Receipt SHA-256: `eb8ec69dcd71e1a299fa6dea8275b64dd8aa97b1cda34767e7c20bca8b4e6cb6`.
- Full DLL SHA-256: `7d3a7b139abb84912370300b8eaeb45155c7fef1a77e58021ddefa2a9528e364`.
- Wheel SHA-256: `cc2854313d10d7cf57cf37a56e18906371cf9dc41730900103c406648af53ed4`.

Independent source, completed-package and private deployment-helper reviews passed.
The updated bounded NPC harness passed 80 offline tests. After explicit user
merge/install approval and a fresh closed-client check, all 15 hosted checks
passed and PR #54 merged. Installation verified **455 modules**, **9,569 preserved
files** and **one client DLL inventory change**. Manager PID **3900** was healthy
and unbound; all five shortcuts and startup preflight passed.

The inspected obsolete .59 host contained **2,098 files**, totaling **47,646,848
bytes**, with inventory SHA-256
`3561c4961fe42c1bb874c875870873fa493b1375000ffa42b4f2dbe6edc2912e`.
It and the exact old .59 wheel and .39 DLL payloads were removed, totaling
**50,327,590 bytes**. Actual settings, jobs, saves and diagnostic evidence remain
in place. No runtime or payload rollback copies were retained.

Launch at **17:45:09.8119540 UTC** verified the exact qualified DLL in PID **1836**,
creation FILETIME `134353503028775811`, HWND `3736294`. Passive readiness reported
login/loading and sent no action. These process values are recorded evidence,
not continuing authorization. After fresh Umbra login, bounded follow-through
ran as recorded below. Twelve compact deployment receipts and seven independent
installed-file hashes were exported and verified. Four additional obsolete .59/.39
staging binaries were removed by exact hash, totaling 5,361,484 bytes. Actual user
data and diagnostic evidence remain in place.

## Live .60 follow-through and supplementary evidence review

Run `f005467068ad49e1970090b037c26ce6` queued one SELF_POWER for Shot to the Leg
563795161 and one ATTACK against NPC key `[23885,37]`, token
`27b214e91d69bf94569114dd`, under the same engagement, binding digest and exact
Grant. Production trace step 10 observed health 400; step 11 recorded the same
available tracked object at health zero, maximum 400, with
`kill_confirmation = native_health_zero`. The controller ended COMPLETE with
`kill_limit_reached`. The trace's 1,734 ms value is the frame timestamp, not an
exact damage or server-event time. Terminal cleanup returned NATIVE_STOPPED for
the same NPC. No owner or manual-list entry remained; no error or watchdog fired.

The original `acceptance.json` remains **partial**. Its wrapper logged
`population.observe()` before the production frame refreshed the bound object
through `observe_character_detail()`, so its private health list still showed
400. That later native detail replaces the tracked character before controller
policy and trace serialization. Independent supplementary review checked the
registered key/address/token transaction, canonical address-derived token,
exact serialized request/engagement/Grant correlations, and the later zero-health
trace with confirmed cleanup. Missing or replaced objects are not treated as
death. The native engagement retains the target reference until cleanup; passive
registry rereads alone are not a universal ABA or cross-thread ownership proof.

This existing evidence establishes observed native-object death and cleanup;
another fight is not needed to manufacture the missing logger sample. Original
partial evidence is preserved beside `supplemental-review.json` in the private
run directory. The private logger correction now captures canonical detail
observations and passed 87 offline tests; the installed runtime did not change.
No player kill credit, skill consumption, snare application, or server-effect
attribution is claimed. The one-kill run intentionally ended COMPLETE, so it does
not establish subsequent recovery or another encounter on .60. The next bounded
recovery check uses the existing nearby-NPC authorization, at most two distinct
NPCs and a 20-second watchdog, without UI input or movement. Historical .57
manual-player-to-PvE recovery passed; a .60 repeat would require fresh presence
and identity confirmation for the already authorized player, Day. Automatic
retaliation still needs the separate authoritative server session/attribution
contract and cannot be enabled merely by passing another live test.

## .60 recovery attempt and passive buff-stat transition

Run `daa891ed86f24f3e9c8192a847b333e0` remains **not_passed**. SELF_POWER request 1
queued for the first bound NPC. ATTACK request 2 was definitively DEFERRED with
NEVER_ENTERED; the next ATTACK request 3 queued. Native health fell from 400 to
61.6008, without an observed death. At frame timestamp 7,187 ms, the NPC crossed
the controller's 20-unit close-range threshold, from distance 26.45 to 4.59.
Production proposed an attack renewal against the same engagement, but the private
one-attack acceptance boundary rejected it before native entry. Its summary count
of two combines one actual rejection with the failure latch; it does not mean
two additional action attempts reached the native service.

There was no second NPC, later SEEKING or recovery proof. STOP request 4 confirmed
native cleanup; no owner or attack-list entry remained, the error field was null,
and the watchdog did not fire. Preserve the original not-passed result. This is a
private acceptance-scope mismatch, not evidence that the installed runtime needs
a behavior change. The planned private correction permits at most four positively
queued ATTACK requests, including the first, for the exact first NPC; one SELF_POWER,
the same engagement
and owner, and the original 20-second deadline. The second NPC still stops after
its first queued attack. Uncertain requests retain their identity. Retrying an
unaccepted command requires definitive no-entry evidence; an ordinary renewed
attack can follow a positively acknowledged attack on the same engagement.

After the failed run, the user reported buff loss. A passive native-vitals read
at **18:04:05 UTC** confirmed the following maximum-stat changes; all three current
resources were full at the later observation:

| Native maximum | Earlier | Later |
| --- | ---: | ---: |
| Health | 3,957.6018 | 3,260.2568 |
| Mana | 480.185 | 312.16 |
| Stamina | 839.272 | 693.852 |

Private `artifacts/bot-deploy/20261001-b40/buff-transition-vitals.json` retains the
observation. No effect identity, expiry mechanism, or causal link to the skill,
attack or cleanup is established. Fresh stats must be used for the next bounded
run. Installed host .60/native .40 source `f0263c3` is unchanged.

The [offline retaliation session-boundary audit](retaliation-session-boundary-20261001.md)
records reviewed client connection/login paths and the remaining authoritative
session and attribution gaps. The user has no server source or protocol docs;
the client-only findings do not enable automatic retaliation.

## .60 renewal retry and observer lifecycle boundary

Run `npc-recovery-renewal-a4844073bacf46e5a187331889c4f043` remains
**not_passed**. The corrected private action boundary allowed four total positively
queued attacks for the first exact NPC, including the initial attack. Its fresh
preflight used the post-transition resource maxima, with all resources full.
SELF_POWER request 1 queued, ATTACK request 2 was definitively deferred without
entry, and ATTACK request 3 queued on the same engagement. Both canonical population
and bound detail recorded the original NPC at zero health at frame 1,672 ms;
production entered POST_KILL.

At 1,906 ms, the explicit stop event was set before the normal post-kill delay
completed. Native cleanup then confirmed NATIVE_STOPPED, with no retained owner
or attack-list entry. No action-boundary rejection, watchdog, hotkey stop or
reported runtime error occurred. The production interruption was
`parent_operation_cancelled`; the sampled Grant still matched. There was no later
SEEKING frame or second encounter.

The private population decorator can set this event after an observation or
identity-validation exception. Its original retry path did not retain the exact
exception, so the reason cannot be recovered from this run. A dead object's
registry disappearance is a hypothesis, not a demonstrated cause. Preserve the
original failed result and trace. The next private recorder must retain bounded
failure diagnostics and allow an already positively observed dead object to leave
the registry without fabricating a sample or transferring its engagement to a
replacement. Native cleanup and a strictly later production SEEKING frame remain
required before a distinct second encounter. Installed runtime is unchanged.

The [native combat-effects audit](native-combat-effects-20261001.md) records the
actor-owned effect interface and update-message paths. The decoded vector is not
yet qualified as a persistent gameplay-effect inventory; the buff-stat transition
does not identify an effect, its source, or an expiry reason.

## Historical .57 live evidence

Installed .57/.37 source `1d107a25` passed manual-player attack, list removal,
correlated native stop and a strictly later PvE SEEKING frame. The final list was
empty, ordinary NPC submissions were zero, the watchdog did not fire and the
dispatcher had no interruption. The harness's final explicit stop occurred after
recovery. Its loop timestamps are not exact native latency measurements, and the
queue/cleanup evidence does not prove a server-accepted hit.

Two .57 NPC attack attempts queued successfully but cleanup was not positively
confirmed within the old host's immediate retry window. A repeat also failed
after the user reported possible concurrent Track input; Track is not established
as the cause. Later passive idle snapshots do not retroactively pass cleanup.
The .58 settlement fix preserves the exact owner while awaiting the native reply;
its offline and real-process qualification is distinct from live acceptance.

## Active todos

- Complete: generic opener, native learned-skill resolver, character settings,
  bounded same-owner cleanup and native combat-mode prerequisite correction.
- Complete: historical .59 skill-request/attack/native-cleanup gate and saved
  Umbra/Wonderbane basic Shot to the Leg opener, revision 1.
- Complete: registry-backed population, outermost native update guard, host/native
  initiation and request-provenance correction, with independent validation.
- Complete: exact-source .60/.40 qualification at `f0263c3`, both native profiles,
  original/prepared image gates, all 15 hosted checks and approved PR #54 merge.
- Complete: .60/.40 installation, manager activation, shortcuts/startup preflight,
  exact DLL launch verification and obsolete-runtime retirement; user data preserved
  without rollback copies.
- Complete: .60 skill/attack queue sequence, exact-object zero-health observation
  and confirmed native cleanup, with original partial result preserved and a
  separate supplementary evidence review.
- Complete: correct the private renewal bound; the retry observed native death
  and confirmed cleanup but stopped before recovery. Both failed runs are preserved.
- Active: correct the private observer lifecycle and preserve stop diagnostics,
  then repeat bounded .60 recovery with exact cleanup and a later SEEKING frame.
  No runtime source change is planned.
- Complete: publish this installation receipt through draft PR #55; its merge
  remains pending. PR #53's included tip is already merged.
- Pending: qualified server-effect evidence and the authoritative
  server-character-session fence required for automatic retaliation.
