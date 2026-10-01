# Queued native skills and delayed-stop settlement

Installed host **0.3.58** / native **1.8.38** use exact qualified source
`05c888a4ff1e1443163ef3cb2ea6e2432672c372` with official client **1.3.38.13**.
[PR #51](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/51)
merged at `214bcdede95b8ef4f51cb1b13bdd64a31378dcb1` on October 1,
04:14:59 UTC after all 15 hosted checks passed. Qualification, installation,
manager activation and loaded-DLL identity passed. The bounded .58 basic NPC
attack/cleanup gate passed after login. The skill-opener attempt did not pass:
SELF_POWER remained UNCERTAIN without queue evidence or a followup attack, while
terminal native cleanup was confirmed. The earlier .57 manual-player recovery
pass and unconfirmed NPC cleanup attempts remain separate historical evidence.
The qualification and deployment evidence is recorded below.

The normal checkout is on the PR #51 main merge. The deployment and combat-mode correction
worktree uses `codex/queued-skill-deployment-20261001`, targeting main through
[draft PR #52](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/52). The merged
feature branch is retired. This record incorporates the relevant historical
PR #50 facts; #50 remains open until the replacement receipt PR is reviewed.

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

## Qualified package and verified deployment

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

## Live .58 NPC results and combat-mode prerequisite

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
Source review confirms the attack entry enters combat mode, while the installed
power entry does not establish that prerequisite. A later exact-session passive
read at 15:28:51 UTC confirmed Shot's native definition field `+0x1F0 = 1`, with
actor mode 1 and action state 1. The reviewed classifier requires combat mode for
requirement 1. The read invoked no native function or input and acquired no lease;
its private receipt is `skill-stance-result.json`, definition SHA-256
`7c70f270975fd819291090f887e8e9487c20156f1c0539525e8f507b5b161f1f`.
This confirms the definition/prerequisite mismatch at that observation; it does
not retrospectively establish the sole cause of the earlier failed attempt.
Candidate host **0.3.59** / native **1.8.39** contains the correction on the
existing PR #52 branch and awaits qualification. Installed .58/.38 is unchanged.
Owner revocation was a distinct later
event; the sampled generation/no-owner state does not identify its trigger.
Existing fail-closed handling stays in place, with no automatic restart.

Combat-mode preparation belongs inside the native power invocation under the
same actor, Grant, engagement and fence. Host policy continues to propose the
configured numeric skill; only its correlated queue acknowledgement can advance
the attack. UNCERTAIN retains the exact command for status/cleanup. Native
callbacks must revalidate ownership after any mode transition and preserve entry
history. No new hotkey, configuration flag or arbitrary host delay is required.

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

- Complete: generic actor-directed opener, learned-skill resolver and character
  settings; bounded cleanup settlement and independent source reviews.
- Complete: exact-source package qualification, all hosted checks, approved PR #51
  merge, installation, activation, launch identity and obsolete-runtime retirement.
- Complete: .58 bounded basic NPC queue/terminal-cleanup gate; no server-hit or
  PvE-recovery claim.
- Active: qualify candidate .59/.39's native combat-mode prerequisite correction
  for the unconfirmed skill attempt, on draft PR #52 outside main. The later revocation's trigger remains
  unknown from the retained evidence; it does not justify relaxing owner guards.
- Pending: qualify/review the corrected source, approved deployment and bounded
  queued-skill/attack acceptance.
- Pending: expanded PR #52 review/integration, then supersede the still-open PR #50.
- Pending: server-consumption/impact proof and the authoritative
  server-character-session fence required for automatic retaliation.
