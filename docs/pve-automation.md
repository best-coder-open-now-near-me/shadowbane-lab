# Native PvE automation

The production runner uses registered native objects, exact process/actor lifetimes,
and one shared native owner for preparation and combat. UI selection, hotbar
bindings, HUD messages and combat-log text are not action or kill authority.
The installed release and live qualification limits are recorded in the
[buff preparation receipt](buff-preparation-20261001.md) and
[branch map](git-branch-map.md). The latest buff acceptance is partial; the commands
below describe the existing production interface, not authorization to repeat it.

## Control and ownership

Fresh registry-backed population identifies eligible NPCs by exact key and opaque
lifetime token. The controller retains the admitted object across selection
changes. Learned powers use native numeric IDs; SELF_POWER applies to the actor
while preserving the encounter context, and ATTACK applies to the exact NPC.
Native initiation and reuse admission decide whether a proposal may enter.
Animation frame/index telemetry does not prove cast completion or interrupt safety.

A correlated queued receipt proves client enqueue, not damage, skill consumption
or server acceptance. Exact native health zero can confirm target death; it does
not assign server kill credit. Missing objects, changed identity, lost authority
and uncertain commands retain their cleanup obligations. Recovery requires the
appropriate correlated native closure. Closing an NPC context may retain the
shared parent for further preparation or another encounter. Parent LOCAL_RELEASED
is distinct from a claim that the actor is idle.

Configured buffs use canonical effect coverage and native readiness. Pending
potion application suppresses duplicates without a fixed application sleep.
Either configured Transform form satisfies its coverage group. Item queue,
local settlement, remote application and effect presence remain separate facts.
See the [buff contract](buff-preparation-20261001.md) for exact selectors and
current acceptance gaps. No host timer fabricates buff success.

## Profile and saved character settings

Use the installed host and a reviewed VM-local client profile for the current
window geometry and native build. A live run requires both
`"live_input_enabled": true` in that local profile and `--live`. Keep machine-local
and live-enabled profiles out of Git. Profile action bindings retained for other
adapters do not enable hotkey fallback in native PvE.

Validate the local profile and read the current character settings using a fresh
process ID; the example variables must point to the installed release and local
files in the game VM:

```powershell
$py = 'C:\ShadowbaneLab-Guided\vendor-1.8.3-bd08ffc\host-0.3.64\Scripts\python.exe'
$profile = 'C:\path\to\reviewed-client-profile.json'
$processId = 7932 # Replace with the freshly verified current client process.
$env:PYTHONPATH = $null
& $py -B -m shadowbane_lab.cli client validate-profile $profile --json
& $py -B -m shadowbane_lab.cli client pve-settings --process-id $processId --json
```

`pve-settings` is scoped to the exact current server/character and saves with a
revision check and final session validation. With no mutation flags it only shows
settings. `--buff-config <reviewed.json>` persists typed intent, not proof that an
item is owned, a power is learned or its effects are active; the native runner
resolves those facts again. A buff-only settings update preserves the saved policy
and opener. Umbra's authorized opener is Shot to the Leg (`563795161`), with basic
policy; do not substitute a universal proc-Assassin/Shadow Touch configuration.
The runner loads settings once at startup; editing settings does not reconfigure
an already running operation.

## Run a finite encounter

Choose a new evidence path, use the installed source, and focus the matching client
during the guarded wait. `run-pve` selects the matching foreground client; it does
not accept the `pve-settings` process-ID argument.

```powershell
$evidence = 'C:\path\to\new-pve-evidence.json'
& $py -B -m shadowbane_lab.cli client run-pve `
  --client-profile $profile `
  --navigation-cache-directory 'C:\path\to\Wonderbane\cache' `
  --max-kills 1 `
  --max-seconds 60 `
  --max-encounter-seconds 45 `
  --recovery-timeout-seconds 30 `
  --recovery-health-fraction 0.75 `
  --recovery-mana-fraction 0.15 `
  --recovery-stamina-fraction 0.25 `
  --wait-for-client-seconds 15 `
  --evidence-output $evidence `
  --live `
  --json
```

Omitting `--policy` and `--opening-skill` uses saved settings, whose unsaved defaults
are basic policy and no opener. `--no-opening-skill` explicitly suppresses a saved
opener for that run. No `--hotbar-config` is needed: that legacy option is rejected
by the native path. Native state is the default control source; legacy HUD/log
options are likewise rejected. Do not use an old hotbar-oriented wrapper as a
substitute for this interface.

Finite mode stops for its kill/session limits or an earlier safety/encounter
condition. Cleanup may take its separately bounded settlement time. A finite run
may finish before a queued potion's remote application becomes observable; this
is not permission to repeat the item or report its effect as active.

## Camp and approach limitations

`--camp-radius` currently applies only with `--continuous`, around the starting
position. Finite mode passes no camp radius to the controller, so adding that flag
to the finite command above does not enforce a custom starting-camp boundary.
Native NPC admission retains its own exact-object and nearby eligibility checks;
those are not a substitute for an arbitrary smaller finite camp.

Continuous mode requires durable evidence output and runs until stopped; its
controller does not apply the finite global kill/session limits. Do not combine
`--continuous` with `--max-seconds` and describe the result as a time-bounded run.

The standalone command constructs the native movement operation and
`PvEApproachController`, using the active navigation map and A* planner. It may
approach or reposition for an encounter. There is no CLI switch that makes this
path stationary. The private acceptance harness's explicit target, distance,
action-count and movement restrictions do not silently carry over to production
CLI runs. Native ATTACK can also initiate the client's own approach behavior.

## Evidence and stopping

Read the final typed result and incremental journal together: proposal identity,
actual enqueue, coverage, exact health/death, child closure and parent closure
answer different questions. Never promote a rejected observation or unavailable
publication into missing coverage, and never use a system message as bot authority.

Foreground, character lifetime, scene, owner lease and manual-input protections
remain active. An uncertain entered action is polled/cleaned up under its original
identity; it is not replayed as a fresh cast. Native STOP_CONTEXT/STOP_OWNER
receipts must be assessed at their own scope. Saved settings and historical
journals remain in place; deployments retain no rollback runtimes.

The source boundaries for these commands are `cli_commands/parser.py`,
`cli_commands/client_pve.py`, `cli_commands/client_pve_settings.py`, and the
`pve` controller, runner and shared actor coordinator. Historical keyboard, HUD,
animation-interrupt and proc-Assassin calibration instructions are superseded by
this native path; Git history preserves those earlier experiments.
