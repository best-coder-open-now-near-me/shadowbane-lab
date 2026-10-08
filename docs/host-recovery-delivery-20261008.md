# Host .79 recovery delivery - October 8

PR #111 merged at `85e31947ea2c0e440fd75428d5b439328cce5079` after all
15 hosted checks passed for exact source
`7cd5d22c0a475ecb3eecaccc8f77a5ce95d0ceee`. It includes the preparation
registration recovery from PR #92, worker attachment recovery from PR #94,
and the three-kill live acceptance record. GitHub marked both component PRs
merged by ancestry. `main` is the shared integration destination.

## Qualification

Host 0.3.79 retains native 1.8.54 and the reviewed client 1.3.38.15.
The complete host suite passed 5,213 tests with 38 skips. Both native profiles
passed 74 movement, 86 combat and 148 actor IPC cases each; the actual Windows
worker handshake passed. The 14-step package qualification had zero failures.
All 467 base Python source modules matched the isolated installed wheel.

- Wheel SHA-256: `07263e79eb46e374092c09fda90cd2bfc5c695b7838ec630b2a1649a7a48a08e`.
- Qualification receipt: `07240ef2add68e65d6eb0f8b0c76cd6162de8c937457abb346ae05402818b0e0`.
- Source archive: `97e178156689c58fac607ad381759544c293a37167fa81575efe38f38d306ecc`.

The separate cosmetic overlay is preserved: native source
`0f808385d83c731306021b38109e623bde265be1`, DLL
`e6dcdef161abac62b91c5275b3334c07f0a77d6755ef48c7dd950fa21689a2c7`.
Its reviewed graphics app and katana module are retained in the new host,
with their distribution RECORD rows resealed to the actual bytes. The effective
installed host contains 468 verified modules. This does not claim that the
cosmetic overlay is part of main or that its DLL is the base package DLL.

## Deployment evidence

Preparation installed and verified .79 without switching the manager or
stopping either game. An initial stop attempt failed before any pause/stop:
Windows PowerShell 5 wrapped the two-process graphics dependency JSON array.
The corrected decoder passed empty, single, double and multiline array cases
on actual Windows PowerShell 5, including reproduction of the old failure.
The repair changed only that helper and its plan/preparation provenance; it did
not reinstall the host. Independent review and 17 Python / 5 PowerShell cases
cover the repair and its generated wrapper.

Original plan: `cac43c461b2734f9b8b70899d31e03bb673265a540d12e5d488f462fb4261dbd`.
Repaired plan: `8e47fa8f2ef19114a11794cb9a876f434160e9a39d729ad30feb21a1b78cc89e`.
Original preparation receipt: `893326fad85d4a12aeb33225d5c0c7cb972218af3152d9270a6c207ae89420cf`.
Repaired preparation receipt: `fced08a12380f1afc29381eac6b3e4797089e710bd5dbfb43cedad486a9d826e`.

Both clients retain exact process-lifetime and native-module checks. Native
freshness gates apply to manager-owned clients; an independent unbound client
at character selection does not block a host-only update. The captured manager
had zero bound clients and no worker operations. No global one-client restriction
or window geometry requirement is introduced.

The open graphics panel still depends on .78. Keep that active dependency until
its exact process pair exits; it is not a fallback runtime. No rollback copy or
archive is created. User settings, jobs, journals and launch receipts remain in
place under the [deployment policy](deployment-policy.md).

Private diagnostics are under `host-update-20261008-0.3.79` on the testing VM
share, and package evidence is under local `artifacts/bot-deploy/20261008-host79`.
No captures, third-party binaries or credentials belong in source delivery.

A subsequent stop attempt also stopped before pause: it classified the manager's
signed Windows console host as an independent workload. A separately reviewed
classification correction preserves its launcher/interpreter identity and leaves
the console to exit naturally. That repair was prepared but not applied; the
baseline was subsequently superseded below. Neither failed attempt stopped or
restarted a game.

## Superseded live deployment baseline

Before the console correction could mutate the prepared deployment, both game
processes exited during its read-only validation. That attempt made no changes.
A subsequent inspection found a separately authorized Visual Inspector deployment:
cosmetic source `2f14379eb1bfccdbb9e138915c4ed07cd7ceadcd`, native DLL
`52ac0004d1d2645f8f42e40005d3b78e856a4d40269ccbca4bd914374875bea5`.
The graphics chat reopened a new client and panel. Its source is draft PR #113,
which depends on PR #106. The active manager remains host .78, PID 2560.

The bot .79 host remains prepared against the earlier overlay; its manager was
never stopped or switched. Do not execute the old repair/apply wrappers against
this new baseline. The original console correction and failed read-only attempt
remain diagnostic evidence, not approval to overwrite the newer graphics work.
Current overlay preservation requires its matching app, katana, visual inspector,
visual panel and object-navigation modules as well as the native DLL.

Next: coordinate the shared installation, requalify preservation of the current
graphics overlay, and activate the bot update only against a fresh baseline.
The earlier Umbra PID/readiness has expired. A live NPC check requires a fresh
native character binding and login.
Persistent background buff upkeep and the existing-character picker are separate
source work and are not capabilities of this .79 update.
