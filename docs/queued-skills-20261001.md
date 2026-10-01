# Queued native skills and delayed-stop settlement

Installed host **0.3.59** / native **1.8.39** use exact qualified package source
`e90d2f64ea49df5af94365012548266e6829e3a1` with official client **1.3.38.13**.
[PR #52](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/52)
merged at `72f13d5f64f896a5b646838ed3bd5c268fac7773` on October 1,
15:53:29 UTC after all 15 hosted checks passed at the approved final head.
Installation, activation and loaded-DLL identity passed. The bounded .59 gate
passed: Shot to the Leg SELF_POWER queued, then ATTACK queued against the same
NPC and owner, followed by confirmed NATIVE_STOPPED cleanup. This proves local
queue admission and cleanup, not server consumption, snare or damage attribution.
Umbra/Wonderbane now has basic policy with saved opener 563795161 at revision 1,
validated for the next run. The earlier .58 and .57 results remain historical.

The normal checkout is on the PR #52 main merge. The reused worktree is on
`codex/native-stance-deployment-20261001` for this documentation-only receipt,
with main as its integration destination through
[draft PR #53](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/53). The merged
PR #52 feature branch is retired. PR #50 is closed as superseded; its relevant
historical receipt facts are incorporated, while its branch is retained because
its exact tip is not an ancestor of main.

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
Host **0.3.59** / native **1.8.39** now contains the merged and installed
correction, with qualification and live results below.
Owner revocation was a distinct later
event; the sampled generation/no-owner state does not identify its trigger.
Existing fail-closed handling stays in place, with no automatic restart.

Combat-mode preparation belongs inside the native power invocation under the
same actor, Grant, engagement and fence. Host policy continues to propose the
configured numeric skill; only its correlated queue acknowledgement can advance
the attack. UNCERTAIN retains the exact command for status/cleanup. Native
callbacks must revalidate ownership after any mode transition and preserve entry
history. No new hotkey, configuration flag or arbitrary host delay is required.

## Qualified and installed .59/.39

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
- Complete: exact-source .59/.39 qualification, all 15 hosted checks, approved
  PR #52 merge, installation, activation, launch and obsolete-runtime retirement.
- Complete: bounded .59 skill-request/attack/native-cleanup gate and saved
  Umbra/Wonderbane basic Shot to the Leg opener, revision 1.
- Active: bounded one-NPC follow-through with exact native health/death observation
  and cleanup; no player kill-credit or skill-consumption inference.
- Pending: review/integrate this documentation-only deployment receipt.
- Pending: qualified server-effect evidence and the authoritative
  server-character-session fence required for automatic retaliation.
