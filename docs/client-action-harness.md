# Bounded client-action acceptance harness

Live client acceptance uses semantic actions with explicit preconditions, one bounded input,
an independent postcondition, cleanup ownership, and versioned evidence. A visible gameplay
result is never sufficient by itself.

Every action emits the same ordered lifecycle boundaries:

```text
started
  -> precondition_passed
  -> input_dispatched
  -> effect_observed
  -> cleanup_completed
  -> succeeded | failed
```

Failures carry a stable terminal reason and the boundary where progress stopped. Normal automated
tests use recording input and synthetic native observations. Live actions require both an explicit
`--live` argument and a calibration profile with `live_input_enabled: true`.

## First action: world-map destination click

`client.world_map.destination_click` verifies only the first independently provable boundary of
world-map travel:

```text
one exact guarded right click
  -> one exact in-process world-map destination event
```

Before input, the action requires all of the following to agree:

- the calibrated client is visible and foreground;
- the exact process ID, process creation time, and window handle are available;
- the build-guarded world-map reader belongs to that process;
- the map is open and the requested fractional point resolves inside the projected world;
- the extension event channel belongs to the same process lifetime;
- the channel exposes both the world-map and tagged-test-input capabilities with no producer
  error; and
- this test process exclusively owns and renews the channel's bounded consumer lease.

The action snapshots the map projection and extension sequence, rechecks both immediately before
dispatch, moves the pointer through the guarded PyAutoGUI executor, and emits one right-button
transition pair through Windows `SendInput` with the extension's dedicated acceptance-test tag.
Ordinary injected input and lower-integrity tagged input remain ignored by the extension. It succeeds
only if sequence `baseline + 1` contains exactly one event with the expected process lifetime,
window, desktop/client pixel, button, and projected LT/LG. A changed projection, additional event,
dropped event, producer error, mismatched value, or timeout fails the action.
The exact verified event is acknowledged only after every field matches; a mismatched or skipped
event remains pending and prevents the harness from claiming a clean pass.

This boundary deliberately does **not** claim that a route was accepted or that the player moved.
Those are later actions with separate oracles:

```text
world_map.destination_click
  -> travel.destination_accepted
  -> travel.steering_started
  -> travel.position_progress
  -> travel.destination_reached
```

## Run the watched live action

Use a disposable patched client in the WonderBane VM. Open the world map before starting the
command, then return focus to the still-open map during the guarded wait. Choose a point that is
safe for the eventual route consumer; fractions address the current map rectangle from zero to
one.

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client test-world-map-click `
  --client-profile "\\VBOXSVR\codexdiag\wonderbane-travel.local.json" `
  --map-x-fraction 0.60 `
  --map-y-fraction 0.50 `
  --wait-for-client-seconds 15 `
  --timeout-seconds 2 `
  --evidence-output "\\VBOXSVR\codexdiag\world-map-click-001.json" `
  --live `
  --json
```

The evidence destination must not already exist. Move the pointer to a PyAutoGUI fail-safe corner
or press `Ctrl+Shift+F12` to stop input. If Windows accepts only part of the tagged transition pair,
the sender immediately attempts a button-up cleanup and fails the action. A successful result
includes each lifecycle boundary and
the exact emitted destination event. A failure remains useful evidence and names the boundary that
did not complete.

## Adding actions

New actions implement the shared bounded contract rather than adding bespoke long-running test
scripts. Each action must select one strongest verification level:

- `native_verified` — an independent build-guarded observation proves the postcondition;
- `visual_review_required` — the action records evidence but cannot auto-pass without review; or
- `unverifiable` — the current client exposes no reliable oracle, so the action cannot be used as
  an automated acceptance gate.

Composite PvE and travel scenarios should sequence these atomic results. They must not replace
them with a controller phase that is asserted by the same controller under test.
