# Bounded PvE automation

The live PvE slice repeatedly acquires nearby mobiles, attacks only a newly confirmed living
target, waits for bounded resource recovery after each kill, and stops at explicit kill,
encounter, recovery, or session limits. It consumes exact player vitals and position,
selected-target health, position, action state, local-player animation state, and native
service-role identity. Native message events are optional evidence;
the persistent in-game command does not depend on a populated message HUD.

## Control loop

The controller progresses through `INITIALIZING`, `SEEKING`, `ENGAGED`, and `POST_KILL`.
It records the initially selected object's opaque token, sends `Target Next Mob`, and will
attack only after observing a different, valid target token. A kill must be confirmed by a
typed native `TARGET_KILLED` event or exact selected-target health reaching zero before it
counts or another target can be acquired. A zero-health acquisition candidate is treated as a
corpse and is never attacked.

Every living candidate is also checked against the client-native `merchantData` presence marker
and the `shopkeeper`, `banker`, `isTrainer`, and `isMinion` sparse flags. Protected characters
participate in target-cycle accounting so the nearest-target scan can finish, but they are never
admitted to the attack candidate set. A missing or incoherent identity snapshot withholds
engagement. `merchantData` is presence-based rather than boolean; live 1.0.5 validation found it
on `Lirak, Master Bard` even though that service NPC exposed neither `isTrainer` nor `shopkeeper`.
If an otherwise stable candidate exposes an unreadable sparse-role table, the evidence trace
marks its identity classification unavailable and the controller skips it. The failure remains
fail-closed for combat while allowing the bounded target scan to continue.

The live profile maps semantic operations to the installed client's captured native
preferences:

- `client.pve.target_next_mobile` uses `;` (`Target Next Mob`, native action `188`); and
- `client.pve.target_previous_mobile` uses `'` (`Target Previous Mob`, native action `189`);
  the nearest-target sampler uses it to rewind directly through the bounded sample instead of
  traversing the rest of a crowded camp; and
- `shadowbane.basic_attack` uses `Ctrl+A` (`Attack Selected`).

`Clear Target` is native action `102`, but it had no key record in that capture, so the harness
does not pretend it has a working clear-selection key. Inspect the current file without changing
it before any live run:

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
target the game acquired automatically only after a fresh native player-hit record, then
observes that target's native action queue. It uses rank-40 Shadow Touch once when the mob
queues or begins an attack aimed at the local player and native mana is at least its verified
55-point cost. When an explicitly acquired target is already within measured melee range, it
sends `Ctrl+A` immediately. If neither participant deals damage, the controller watches the
local player's native action sequence: it cycles a target after 1.5 seconds when the attack
animation never begins, or after 2.5 seconds when an animation begins but still produces no
hit. A newly auto-selected target is accepted only after the previous kill has been confirmed
by the native message stream.

The target-action profile is locked to the verified WonderBane executable hash and reads the
selected `ArcCharacter` action-pending flag, current `ArcMotion` ID, impact marker, and
target-of-target pointer. Live traces showed the queue transition 543-909 ms before the attack
motion on the first calibrated target. A second live target confirmed that animation IDs and
queue-to-impact timing vary by creature, and that a new queue may overlap the previous attack's
lingering impact marker. The queue flag therefore has precedence and is the earliest interrupt
trigger; verified motion IDs provide an additional windup signal. The policy never triggers on
impact alone, never for an attack aimed elsewhere, and never more than once per mob. That
per-target limit avoids spending Shadow Touch again during its verified 27-second stun-immunity
effect.

The first end-to-end bounded validation observed a queued attack aimed at the player, accepted
the guarded Shadow Touch input, and measured the expected roughly 55-point native mana decrease
on the next sample. That queued action returned to a non-impact motion without producing its own
impact marker; the next queue arrived 12.3 seconds later and was correctly ignored by the
once-per-target guard. This proves the native signal-to-semantic-input path on the calibrated
client build; it does not claim every creature has identical animation timing.

The same guarded `ArcCharacter`/`ArcMotion` layout is sampled for the local player. Each trace
records player motion ID, action-pending flag, impact frame, selected action target, derived
phase, action sequence, and exact motion-transition sequence. A targeted action or motion
transition after dispatch proves that an attack animation started; unrelated player animations
do not extend the target grace period. Live validation also showed that the local player's
impact marker can linger while motion and targets change, so impact alone is neither treated as
a fresh animation nor allowed to suppress recovery. There is not yet a separately decoded
player-stun bit; actual LT/LG displacement—not the input dispatch—is the authority for whether
a reposition succeeded.

The current WonderBane 1.0.5 regression also exercised mixed town targets. A preselected Tree
of Life was classified as a non-character and cycled without attack input; service characters
were skipped by their native role data. A later run abandoned a nonresponsive 75-health Crab,
kept its opaque token excluded, acquired a 10-health Turtle, normalized the client's signed
overkill health to zero, and completed at the one-kill limit.

The local-player animation regression then repeated that path with the native-state source. In
the final bounded run, two 75-health targets showed targeted motion transitions from motion 15
to motion 3 but no health exchange; they were excluded 2,500 and 2,563 ms after direct attack.
A later 10-health target transitioned through the same motion evidence and reached exact native
health zero, completing the one-kill run. The trace also confirmed that player impact-frame
state lingered across multiple motion and target changes, which is why motion sequence—not an
impact marker by itself—is the animation authority.

Shadow Touch must have a real key mapping in the local client profile before this policy can
run. The checked profile intentionally does not invent one; a proc-Assassin run fails before
input if `shadowbane.assassin.shadow_touch` is absent. The dry-run replay exercises target
cycle, automatic selection, attack interruption, automatic attack observation, and the bounded direct-attack
fallback through the same guarded input compiler and executor without touching the VM.

The farming loop separates the total session bound from a per-encounter bound. The verified
live target started 61 units away, `Attack Selected` closed to melee range, and automatic
attacks removed about 2,400 of 5,526 health during the first 28 seconds. The former 30-second
ceiling was therefore too short for that target. The default encounter allowance is now 120
seconds, while the no-progress detector still retries or abandons stalled targets much sooner.
After a confirmed kill, the controller waits for 75% health, 15% mana, and 25% stamina before
acquiring another mob. If those floors are not reached within 30 seconds, the run stops rather
than entering another fight depleted.

## Fail-closed behavior

The run stops without issuing more input when any of these conditions occurs:

- the foreground executable, title, window size, or DPI guard changes;
- the independent `Ctrl+Shift+F12` emergency stop trips;
- native process identity or executable hash validation fails;
- three consecutive native observation polls fail pointer, health, identity, action, or resource validation;
- exact player health reaches the 50-percent safety threshold;
- the selected target changes while an engagement is active;
- the native message HUD reports player death or multiple ambiguous kills;
- post-kill resources fail to recover to their configured floors in time;
- acquisition, combat progress, engagement, session, or kill bounds are exceeded; or
- an input plan is rejected or interrupted.

The runner never attacks a target that was already selected when it started. A stalled
proc-Assassin selection gets a one-second grace for a fresh native hit, then the controller
uses the verified Target Next Mob binding to acquire a different mobile. A stalled fight may
retry the direct attack command twice. If the client still makes no combat progress, the
proc-Assassin policy remembers that target for the rest of the session, abandons it, and uses
the verified Target Next Mob binding to seek a different mobile. It requires a new native
target token before engaging again and permits at most four such retargets, so an unresponsive
cluster cannot create an input loop.

If the player loses health within melee range while the selected target loses none, and the
player is natively idle rather than animating, the controller can request at most two combat
repositions per target. The approach layer tightens its arrival radius from 20 units to 3 and
reuses the terrain-seeded weighted-A* and learned-obstacle recovery. Continued input without
measured displacement does not count as successful recovery; the existing engagement and
stalled-target bounds still terminate or retarget.

A single torn native observation is not treated as a trustworthy state change. The runner
withholds all input while retrying up to three consecutive polls and resets that count only
after a complete target, target-identity, player-vitals, player-position, target-position, and
combat-log observation succeeds. During engagement, health, identity, position, and action must resolve the same
opaque target token. A third
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

## Start from in-game chat

The persistent foreground chat listener owns both travel and battle commands. Start it once
inside the VM (or restart it after updating the repository):

```powershell
powershell.exe -NoProfile -File \\VBOXSVR\codexrepo\scripts\start-wonderbane-go-listener.ps1
```

With Shadowbane focused, submit `/pve` in game chat. The launcher configures that command for
three kills, a 300-second session, a 120-second per-target bound, and the verified current
Shadow Touch hotbar mapping. It uses the native-state combat source, so exact selected-target
health confirms kills, target identity excludes protected characters, and target action state
drives interrupts. Submit `/stop`, open chat,
click a mouse button, or press
`Ctrl+Shift+F12` to cancel it. `/stop` keeps the background listener alive for another `/pve`;
the emergency hotkey shuts down the listener itself. Each `/pve` run writes a unique
`pve-chat-*.json` evidence artifact to `\\VBOXSVR\codexdiag`.

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
  --combat-source hud `
  --hotbar-config $hotbar.FullName `
  --navigation-cache-directory 'C:\path\to\Wonderbane\cache' `
  --policy proc-assassin `
  --max-kills 1 `
  --max-seconds 180 `
  --max-encounter-seconds 120 `
  --recovery-timeout-seconds 30 `
  --recovery-health-fraction 0.75 `
  --recovery-mana-fraction 0.15 `
  --recovery-stamina-fraction 0.25 `
  --wait-for-client-seconds 15 `
  --evidence-output "\\VBOXSVR\codexdiag\pve-fight-001.json" `
  --live `
  --json
```

The VM wrapper validates the live-locked profile, native message-HUD build, unique character
hotbar, and single visible Shadowbane window; refuses to overwrite evidence; and runs the same one-kill
proc-Assassin command with a timestamped artifact. Focus Shadowbane during its guarded
15-second wait:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\run-wonderbane-pve-evidence.ps1
```

After a one-kill evidence run succeeds, the same wrapper can exercise the complete bounded
three-kill lifecycle. The longer session allowance is deliberate: the calibrated simulation's
median three-target clear is about 175 seconds before any passive-recovery wait.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\run-wonderbane-pve-evidence.ps1 `
  -MaximumKills 3 `
  -MaximumSeconds 300
```

Before an approach begins, the live runner resolves the active native zone in the same guarded
`sb.exe` process, loads its first `CZone` terrain layer, and seeds a bounded local weighted-A* window with
height-transition exclusions and costs. Runtime stalls still add learned obstacle cells and
replan around them. Explicit zone-local `CZone` water planes become high-cost traversable cells;
parent/world-relative water remains neutral rather than being guessed from sample darkness.
`CZone` object-population masks are joined through `CObjects`, `Render`, and `Mesh`; populations
whose render graph contains collision-bearing mesh geometry seed a soft density cost. The masks
do not encode individual placements, so exact trunks and structure edges remain online-learned.

Selected-target health is guarded structurally rather than by a low gameplay cap: the build and
pointer must match, the selection must stay stable across the read, both float values must be
finite, and `0 <= current <= maximum`. This admits legitimate multi-million-HP targets without
weakening pointer or coherence validation.

The versioned JSON result includes native build/profile provenance, the active terrain seed, and a sample-by-sample
trace: player health/mana/stamina and LT/LG/altitude, target native role flags, opaque identity,
health/position, planar
and three-dimensional target range, target and local-player native action
phase/motion/impact/action-sequence/motion-sequence state,
typed native combat events, controller phase, and guarded
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
player/target health decreases even when no complete native message is available. Duplicate trace
content is rejected rather than counted twice. Timing remains limited by the controller poll;
native message damage and aggregate health changes do not identify individual weapon/proc/mitigation
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
  --max-ticks 1500 `
  --pve-calibration "\\VBOXSVR\codexdiag\proc-assassin-calibration.json" `
  --json
```

Supported observations replace the generic camp's health, engagement distance, incoming damage
range/cadence, and starting player resources. Sparse fields retain their declared baseline
defaults, and applying aggregate observations to every generic camp mob remains an explicit
assumption rather than named-archetype evidence.

The first 1,000-seed run from the 5,526-health live target trace cleared 988 camps and timed out
12 at the default 200-second analysis ceiling, with no player defeats. Raising only the bounded
analysis window to 300 seconds cleared all 1,000: median 175.2 seconds, p90 189.6 seconds, and
p99 200.4 seconds. This supports the cohesive target-retention and replacement policy under the
current aggregate damage model; it does not turn a single unnamed target trace into universal
mob stats or validate unattended live farming.

## Current scope

`Attack Selected` is now live-validated to close ordinary open-ground distance, while the
existing stalled-target path remains the bounded response to blocked approaches. The loop can
confirm native zero-health kills, recover passively to explicit resource floors, and repeat
target acquisition. Active healing, looting/inventory limits, hostile-relation validation, and
a larger hotbar power rotation remain separate vertical slices; they are not inferred from
unverified keys or hidden inside the nearby-mobile loop.
