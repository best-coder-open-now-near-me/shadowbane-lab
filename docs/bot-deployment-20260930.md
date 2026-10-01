# Object combat deployment - September 30, 2026

Host 0.3.55 / native 1.8.35 is installed and launch-verified in Vendor Test.
Supervised live combat acceptance remains pending login. This receipt records
installation evidence, not a successful attack, cast, cancellation or recovery.

## Source and qualification

[PR #46](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/46)
merged at `7f250c6166b66459a6fba4de527743e5f7363c90` on September 30 at
18:39:06 UTC after all 15 hosted checks passed and explicit user approval.
The installed package was built from its exact head
`6f101f61a7a2f093b0360baef2b628bead057220`, before the merge commit.

Private package `artifacts/b35/3ca9481d/receipt.json` records
`acceptance_eligible=true`, 52 steps and 78 verified files. Full and
diagnostics-only profiles each passed 83 host/native IPC tests and 195 required
native tests, including separate reviewed-image qualification. The receipt
retains optional renderer-transparency findings separately; it does not claim
those diagnostics passed. The selected-cue supported path is qualified, and
particles/trails remain suppressed under the existing renderer policy.

| Artifact | SHA-256 |
| --- | --- |
| Acceptance archive | `0160208062a8b7c7d4ce3c268ca6c4b374f369336de51053a259a5701537ea3f` |
| Host 0.3.55 wheel | `436a6977c0d71f115cc5373780d52746a1d3b9ef6a95fea68d2c65f1165ffd22` |
| Installed full-profile DLL | `7fc16d4ad321bf395e1445a9cb63b22b3e8c64099594d5f24a13530b323503d8` |

## Installation and preservation

The update replaced host 0.3.54 / native 1.8.34 from source
`ab5e043a84808eea776b2e463e7d6e3d2cf63116`. It verified 9,564 preserved files,
450 installed module files, all five shortcuts and launch preflight. Client
1.3.38.12 and its prepared executable are unchanged. The
[September 30 official data patch](client-update-20260930.md), user settings,
saves and job records remain in place.

Manager health passed with observed PID 4456. Launch at 18:43:53 UTC loaded the
qualified DLL into game PID 1944, creation time `134352674273880386`, window
`3474082`. These identify the verified launch observation, not a promise that
those process identifiers remain current. Private deployment receipts and
captures remain under `artifacts/bot-deploy/20260930-b35`; they are not exported
with this source document. Eleven compact guest receipts and their local
`evidence-hashes.json` preserve the deployment evidence.

After installation verification, the exact obsolete `host-0.3.54` directory
(2,078 files, 47,361,515 bytes) and two superseded b34 guest payload binaries
were removed. The inspected retirement inventory had SHA-256
`5919615b49830a54403712ecc2636047ef22fe9db8ff028e919dc5ed328728e9`, no unknown
files or directories, and no active references. Total retired size was
49,986,227 bytes. No rollback copies were created or retained. Recovery follows
[the deployment policy](deployment-policy.md): rebuild committed source and
obtain original client assets from the official source.

## Remaining acceptance

The latest read-only observation was still at login. Next: obtain a ready
character and perform bounded NPC attack/cast plus manual-list cancellation
and recovery acceptance against the installed source. Preserve existing user
records and report native action/engagement receipts separately from observed
gameplay effects. Automatic retaliation remains disabled pending an
authoritative server character-session fence.

The [branch map](git-branch-map.md) records the current shared source and
`codex/object-combat-deployment-20260930` handoff branch, based on main at
`7f250c6`. The normal checkout is clean on that main merge. The merged local and
remote `codex/combat-target-query-20260930` branch was retired after confirming
its exact tip is retained in `origin/main`. Deployment and obsolete
runtime retirement are complete; live combat acceptance is the remaining todo.
