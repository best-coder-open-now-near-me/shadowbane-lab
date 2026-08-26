# Closed-loop LT/LG travel

Travel uses exact native player coordinates as feedback and guarded right-clicks on the
minimap as the actuator. The human-facing command is `go LT LG`; the equivalent CLI is:

```powershell
python -m shadowbane_lab.cli client go 120000 60000 `
  --client-profile .\configs\wonderbane-travel.local.json `
  --live --json
```

The calibrated WonderBane build stores position as three floats ordered `LT, ALT, -LG`.
The native reader locates the local player's matching render-transform cluster from the
verified executable signature, anchors it to the player object's altitude, and then tracks
the median of the agreeing copies. It requests query/read rights only.

At 1920x955, the minimap player center is `(1812, 107)`. A rightward minimap click increases
LT; an upward click increases LG. The checked-in profile uses an 82-pixel radius within the
minimap and remains live-locked. Copy it before live use and change only the local copy:

```powershell
Copy-Item .\configs\wonderbane-travel.template.json `
  .\configs\wonderbane-travel.local.json
```

Set `live_input_enabled` to `true` only after confirming the exact client size and minimap
geometry. Do not commit the local profile.

Each click is a short lease. The controller observes LT/LG again before issuing another one,
recomputes direction toward the active waypoint, and verifies that distance decreased. It
stops on arrival, low player health, focus/profile rejection, emergency stop
(`Ctrl+Shift+F12`), repeated observation failures, click-budget exhaustion, or the session
deadline. Three no-progress checkpoints trigger a bounded reverse-zig-zag sequence. Each
retry starts on the opposite side and widens its lateral component so concave obstacles can
be backed out of before direct travel resumes. The escape budget is finite; after it is
exhausted the controller stops instead of blindly continuing into a wall.
