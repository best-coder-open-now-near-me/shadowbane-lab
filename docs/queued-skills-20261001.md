# Queued native skills and delayed-stop settlement

Installed host **0.3.58** / native **1.8.38** use exact qualified source
`05c888a4ff1e1443163ef3cb2ea6e2432672c372` with official client **1.3.38.13**.
[PR #51](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/51)
merged at `214bcdede95b8ef4f51cb1b13bdd64a31378dcb1` on October 1,
04:14:59 UTC after all 15 hosted checks passed. Qualification, installation,
manager activation and loaded-DLL identity passed. The current live gate awaits
Umbra login: no .58 NPC or skill combat has run. The earlier .57 manual-player
attack/cancel/recovery gate passed; its NPC cleanup attempts remained unconfirmed.
The qualification and deployment evidence is recorded below.

The normal checkout is on the PR #51 main merge. The deployment documentation
worktree uses `codex/queued-skill-deployment-20261001`, targeting main. The merged
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
continuing authorization. Passive readiness was not ready while awaiting login.

The inspected obsolete .57 host contained 2,090 files and 47,557,363 bytes;
inventory SHA-256 was
`7fb2c3caddce9084623d7c3f8fc2dd7aa249bf7d2a6883e5f794db45494e9508`.
It and two exact old guest payload binaries were removed, totaling 50,226,673
bytes. No rollback runtime or payload copies were retained. User settings, jobs
and diagnostic evidence remain in place. Twelve compact receipts and seven
installed-file hashes were verified under private
`artifacts/bot-deploy/20261001-b38/receipts`; private captures are not published.

## Historical .57 live evidence and active todos

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

- Complete: generic actor-directed opener, learned-skill resolver and character
  settings; bounded cleanup settlement and independent source reviews.
- Complete: exact-source package qualification, all hosted checks, approved PR #51
  merge, installation, activation, launch identity and obsolete-runtime retirement.
- Active: fresh Umbra login/readiness for bounded NPC attack/cleanup acceptance.
- Pending: queued skill then attack acceptance; no .58 live combat has run yet.
- Pending: receipt PR review/integration, then supersede the still-open PR #50.
- Pending: server-consumption/impact proof and the authoritative
  server-character-session fence required for automatic retaliation.
