# Bounded PvE automation

The first live PvE slice acquires a nearby mobile, attacks the newly selected target, and
stops after a small explicit kill or time limit. It consumes exact player vitals,
selected-target health, and the native combat log; it does not use OCR, pixel health
estimates, or fixed entity coordinates.

## Control loop

The controller progresses through `INITIALIZING`, `SEEKING`, `ENGAGED`, and `POST_KILL`.
It records the initially selected object's opaque token, sends `Target Next Mob`, and will
attack only after observing a different, valid target token. A kill must be confirmed by a
typed native `TARGET_KILLED` event before it counts or another target can be acquired.

The live profile maps the semantic operations to bindings documented by the installed
client itself:

- `client.pve.target_next_mobile` uses `Home` (`Target Next Mob`); and
- `shadowbane.basic_attack` uses `Ctrl+A` (`Attack Selected`).

The controller deliberately does not toggle combat mode with `C`: combat mode is a stateful
toggle and the current state is not yet part of the native observation contract. `Ctrl+A`
is the client's direct attack-selected command and therefore avoids an unobserved toggle.

## Fail-closed behavior

The run stops without issuing more input when any of these conditions occurs:

- the foreground executable, title, window size, or DPI guard changes;
- the independent `Ctrl+Shift+F12` emergency stop trips;
- native process identity, executable hash, pointer stability, or health validation fails;
- exact player health reaches the 50-percent safety threshold;
- the selected target changes while an engagement is active;
- the combat log reports player death or multiple ambiguous kills;
- acquisition, combat progress, engagement, session, or kill bounds are exceeded; or
- an input plan is rejected or interrupted.

The runner never attacks a target that was already selected when it started. A stalled
fight may retry the direct attack command twice, but it never adds movement, retargeting,
or power use during that engagement.

## Prepare a VM-local profile

Copy `configs/wonderbane-pve.template.json` inside the game VM. Verify that the target
window is exactly 1920 by 955 at DPI scale 1.0 and that the client reports the expected
bindings. Change only the local copy to:

```json
"live_input_enabled": true
```

Do not commit a live-enabled or machine-local profile. Validate it before use:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client validate-profile `
  .\configs\wonderbane-pve.local.json --json
```

## Run one bounded encounter

Before touching the client, run the trace-backed semantic bridge. It drives the production
`PvEController` through the same typed target-health, player-vitals, and combat-event boundary
used by the VM:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m shadowbane_lab.rollouts `
  --scenario frost-walker `
  --seed 23 `
  --json
```

The checked profile contains the live-observed Frost Walker values (10 health, player hits of
4 and 5, and 744 experience) plus exact player vitals. Seed 23 completes one controller-confirmed
kill in 2.4 simulated seconds with rolls `[4, 5, 5]`, no rejected semantic actions, and the
terminal reason `kill_limit_reached`. The output always carries its evidence and assumptions;
incoming attacks, misses, regeneration, movement, loot, and exact weapon timing remain outside
that profile. This is the automation preflight, not a claim of emulator parity.

After the simulation gate passes, stand near a Frost Walker spawn with no valuable or friendly
object selected. Start the command in PowerShell, then focus the Shadowbane window during the
wait period:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client run-pve `
  --client-profile .\configs\wonderbane-pve.local.json `
  --combat-log "C:\Users\admin\Downloads\WonderbaneClient\Wonderbane\Logs\shadowbane-combat.log.txt" `
  --max-kills 1 `
  --max-seconds 30 `
  --wait-for-client-seconds 15 `
  --live `
  --json
```

The result includes the terminal reason, confirmed kill count, and every semantic input
that passed the live guard. A successful first trial ends with `kill_limit_reached`. Move
the pointer to a PyAutoGUI fail-safe corner or press `Ctrl+Shift+F12` to stop immediately.

## Current scope

This slice intentionally assumes the player is already positioned within target and attack
range. Navigation, healing, looting, and power rotation must enter as separately tested
vertical slices; they are not hidden inside the nearby-mobile loop. Exact player health,
mana, and stamina are already observed so those additions can be gated on real resources.
