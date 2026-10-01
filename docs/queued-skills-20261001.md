# Queued native skills and delayed-stop settlement

Integration destination: main through draft PR #51, branch
`codex/queued-weapon-skill-opener`, based on main `18e65bba` (merged PR #49).
Reviewed checkpoints: `b1d1fb4` native actor-directed skills, `962bca5` typed
controller opener and immediate attack followup, `44b660b` native learned-skill
resolution, `21e866b` saved settings/CLI, and `28c5ccf` bounded cleanup.
Source delivery does not imply installation or live acceptance.

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
absolute three-second budget is shared across cleanup and close; expiration never
means cleanup succeeded. Existing focus, lifetime, scene and owner guards remain.

## Evidence and active todos

Installed .57/.37 passed manual-player attack, list removal, native stop and a
later PvE seeking frame. Two NPC attack attempts queued successfully but cleanup
was not positively confirmed within the old host's immediate retry window. The
repeat also failed after the user reported possible concurrent Track input, so
Track is not established as the cause. Later passive snapshots showed idle native
action state and no retained owner. Those do not retroactively pass exact cleanup.

- Complete: reviewed native/host opener and passive resolver source checkpoints.
- Complete: saved settings/CLI and bounded cleanup implementation, focused tests
  and independent reviews. Real IPC verifies delayed parent-cancel cleanup.
- Active: qualify candidate host .58/native .38 from committed source.
- Pending: exact-source package and hosted checks, merge authorization, installation,
  then bounded NPC attack/cleanup and queued-skill/attack live acceptance.
- Pending: server-consumption/impact observation proof and authoritative
  server-character-session fence for automatic retaliation.

PR #50's deployment receipt is outside this source branch and awaits separate
approval. Preserve private diagnostic evidence and user records; retain no
rollback deployment copies. Rebuild committed source when recovery is needed.

Validation before packaging: 4,192 host cases and 801 subtests passed; the one
version-surface mismatch was repaired and all five version/graphics-target tests
then passed. Thirty-five native/platform cases require their qualified environments.
The final ticket-close deadline regressions also passed in a 55-test focused run.
Packaging requires a fresh full host run and both native profiles, including the
new mandatory delayed parent-cancel IPC test.
