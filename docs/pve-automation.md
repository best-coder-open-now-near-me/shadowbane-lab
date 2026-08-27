# Bounded PvE automation

The first live PvE slice acquires a nearby mobile, attacks the newly selected target, and
stops after a small explicit kill or time limit. It consumes exact player vitals and
position, selected-target health and position, and the native combat log.

## Control loop

The controller progresses through `INITIALIZING`, `SEEKING`, `ENGAGED`, and `POST_KILL`.
It records the initially selected object's opaque token, sends `Target Next Mob`, and will
attack only after observing a different, valid target token. A kill must be confirmed by a
typed native `TARGET_KILLED` event before it counts or another target can be acquired.

The live profile maps semantic operations to the installed client's captured native
preferences:

- `client.pve.target_next_mobile` uses `;` (`Target Next Mob`, native action `188`); and
- `shadowbane.basic_attack` uses `Ctrl+A` (`Attack Selected`).

The same client exposes `Target Previous Mob` as native action `189`, bound to `'` in the
captured preferences. `Clear Target` is native action `102`, but it had no key record in that
capture, so the harness does not pretend it has a working clear-selection key. Inspect the
current file without changing it before any live run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client inspect-hotkeys `
  "C:\Users\admin\Downloads\WonderbaneClient\Wonderbane\Config\ArcanePref.cfg" `
  --json
```

The controller deliberately does not toggle combat mode with `C`: combat mode is a stateful
toggle and the current state is not yet part of the native observation contract. `Ctrl+A`
is the client's direct attack-selected command and therefore avoids an unobserved toggle.

## Proc-Assassin policy

`--policy proc-assassin` is the guarded translation of the smart-camp policy. It accepts a
target the game acquired automatically only after a fresh native player-hit record, uses
rank-40 Shadow Touch once when native mana is at least its verified 55-point cost, and then
observes the game's automatic weapon attacks. It sends `Ctrl+A` only after five seconds
without a health decrease or player-hit record. A newly auto-selected target is accepted only
after the previous kill has been confirmed by the native combat log.

Shadow Touch must have a real key mapping in the local client profile before this policy can
run. The checked profile intentionally does not invent one; a proc-Assassin run fails before
input if `shadowbane.assassin.shadow_touch` is absent. The dry-run replay exercises target
cycle, automatic selection, opener, automatic attack observation, and the bounded direct-attack
fallback through the same guarded input compiler and executor without touching the VM.

## Fail-closed behavior

The run stops without issuing more input when any of these conditions occurs:

- the foreground executable, title, window size, or DPI guard changes;
- the independent `Ctrl+Shift+F12` emergency stop trips;
- native process identity or executable hash validation fails;
- three consecutive native observation polls fail pointer, health, or resource validation;
- exact player health reaches the 50-percent safety threshold;
- the selected target changes while an engagement is active;
- the combat log reports player death or multiple ambiguous kills;
- acquisition, combat progress, engagement, session, or kill bounds are exceeded; or
- an input plan is rejected or interrupted.

The runner never attacks a target that was already selected when it started. A stalled
proc-Assassin selection gets a one-second grace for a fresh native hit, then the controller
uses the verified Target Next Mob binding to acquire a different mobile. A stalled fight may
retry the direct attack command twice. If the client still makes no combat progress, the
proc-Assassin policy may abandon that unreachable target and use the verified Target Next Mob
binding once. It requires a different native target token before engaging again and never adds
movement input or cycles indefinitely.

A single torn native observation is not treated as a trustworthy state change. The runner
withholds all input while retrying up to three consecutive polls and resets that count only
after a complete target, player-vitals, player-position, target-position, and combat-log
observation succeeds. Health and position must resolve the same opaque target token. A third
failure stops the run and records the concrete reader error in the terminal reason.

## Prepare a VM-local profile

Copy `configs/wonderbane-pve.template.json` inside the game VM. Verify that the target
window is exactly 1920 by 955 at DPI scale 1.0 and that the client reports the expected
bindings. The verified WonderBane character hotbar has Shadow Touch (`ASS-013`) on F2;
inspect the current character config before enabling input:

```powershell
$env:PYTHONPATH = "src"
$hotbar = Get-ChildItem "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\Config\SCREEN_GAME_*_Wonderbane.cfg" | Select-Object -First 1
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client inspect-hotbar `
  $hotbar.FullName `
  --json
```

Change only the local client-profile copy to:

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
  --hotbar-config $hotbar.FullName `
  --policy proc-assassin `
  --max-kills 1 `
  --max-seconds 30 `
  --wait-for-client-seconds 15 `
  --evidence-output "\\VBOXSVR\codexdiag\pve-fight-001.json" `
  --live `
  --json
```

The VM wrapper validates the live-locked profile, combat log, unique character hotbar, and
single visible Shadowbane window; refuses to overwrite evidence; and runs the same one-kill
proc-Assassin command with a timestamped artifact. Focus Shadowbane during its guarded
15-second wait:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\run-wonderbane-pve-evidence.ps1
```

The versioned JSON result includes native build/profile provenance and a sample-by-sample
trace: player health/mana/stamina and LT/LG/altitude, target identity/health/position, planar
and three-dimensional target range, typed native combat events, controller phase, and guarded
input outcome. This is the evidence boundary used to calibrate later simulator profiles. A
successful first trial ends with `kill_limit_reached`. Move the pointer to a PyAutoGUI
fail-safe corner or press `Ctrl+Shift+F12` to stop immediately.

`--evidence-output` writes that complete payload atomically as a versioned artifact even when
the bounded controller stops without a kill. Compile one or more distinct artifacts into an
aggregate calibration without editing simulator constants by hand:

```powershell
python -m shadowbane_lab.cli client calibrate-pve `
  --evidence "\\VBOXSVR\codexdiag\pve-fight-001.json" `
  --output "\\VBOXSVR\codexdiag\proc-assassin-calibration.json" `
  --json
```

The calibration retains sample counts and histograms for observed target health, outgoing and
incoming damage, hit/miss opportunities, poll-observed attack intervals, starting resources,
engagement distance, experience, adjacent-poll Shadow Touch mana deltas, and exact aggregate
player/target health decreases even when the native text log is silent. Duplicate trace content
is rejected rather than counted twice. Timing remains limited by the controller poll, logged
damage and aggregate health changes do not identify individual weapon/proc/mitigation
components, and target tokens remain process-local opaque identities; those limitations are
carried in the artifact.

When exact target-health decreases are available, smart-camp uses their median interval as the
successful-hit opportunity cadence. It retains the sourced fist and proc mechanics, subtracts
their expected damage from the observed aggregate decrease, and samples the positive remainder
from the observed histogram as separately tagged `observed_unattributed_damage`. This aligns the
total damage envelope without claiming that the residual came from any specific weapon, proc,
mitigation rule, or polling boundary.

Apply the resulting evidence to the generic smart-camp simulator:

```powershell
python -m shadowbane_lab.rollouts `
  --scenario smart-camp `
  --episodes 1000 `
  --seed 0 `
  --pve-calibration "\\VBOXSVR\codexdiag\proc-assassin-calibration.json" `
  --json
```

Supported observations replace the generic camp's health, engagement distance, incoming damage
range/cadence, and starting player resources. Sparse fields retain their declared baseline
defaults, and applying aggregate observations to every generic camp mob remains an explicit
assumption rather than named-archetype evidence.

## Current scope

This slice intentionally observes range without issuing approach movement. Navigation,
healing, looting, and power rotation must enter as separately tested vertical slices; they
are not hidden inside the nearby-mobile loop. Exact player health, mana, stamina, and spatial
range are observed so those additions can be gated on real state.
