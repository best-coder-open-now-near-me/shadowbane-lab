# Closed-loop LT/LG travel

Travel uses exact native player coordinates as feedback and guarded right-clicks on the
minimap as the actuator. Start the foreground-scoped chat bridge once per client session:

```powershell
python -m shadowbane_lab.cli client listen-go `
  --destination-state .\last-travel-destination.json `
  --client-profile .\configs\wonderbane-travel.local.json `
  --world-def 'C:\path\to\Wonderbane\Config\WorldDef.cfg' `
  --live --json
```

Inside the configured VM, the checked-in launcher starts the same listener in a hidden
process, refuses to create a duplicate, and writes JSON Lines status plus errors to the
`codexdiag` shared folder:

```powershell
powershell.exe -NoProfile -File \\VBOXSVR\codexrepo\scripts\start-wonderbane-go-listener.ps1
```

Stop that background listener by resolving and validating its recorded process identity:

```powershell
powershell.exe -NoProfile -File \\VBOXSVR\codexrepo\scripts\stop-wonderbane-go-listener.ps1
```

While that process is running, enter `/go LT LG` in Shadowbane's chat command line. The
installed `WorldDef.cfg` also enables names such as `/go black drake swamp` and numbered
placements such as `/go runegate 1`. Duplicate names resolve to the placement nearest the
exact current player position. `/go oblivion gate`, `/go death gate`, and `/go doomgate`
resolve to the nearest Runegate because the black Death portal at any Runegate is the actual
transition to Oblivion; the travel controller stops at that Runegate and does not enter the
portal automatically. Unknown names fail closed and appear as rejected events in the listener
log.

Use `/stop` to cancel the active route and immediately clear Shadowbane's last click-to-move
destination through the same guarded minimap-center input path. The listener observes
keyboard events only while the calibrated `sb.exe` window owns foreground
focus, never suppresses the game's input, and retains only text that is still a possible
`/go` or `/stop` command. Opening chat cancels the bridge's active route before more travel
clicks are issued. A physical foreground mouse-button press also cancels the route, while
the listener ignores mouse input injected by the guarded travel actuator. This lets a manual
click take ownership without the controller overwriting it at the next interval. Ordinary
chat and all other slash-command prefixes are discarded immediately.

When more than one `sb.exe` process exists, each command binds native position and vitals
reads to the process that owns the guarded foreground client window. Every later input guard
check remains pinned to that process, so switching to another Shadowbane client cannot mix
memory from one client with movement input sent to another.

The one-shot CLI equivalent is:

```powershell
python -m shadowbane_lab.cli client go 120000 60000 `
  --client-profile .\configs\wonderbane-travel.local.json `
  --live --json
```

An explicit destination is remembered locally. After pausing or intervening, bare `/go`
resumes the last LT/LG destination through the running bridge; the one-shot CLI equivalent
omits both positional coordinates:

```powershell
python -m shadowbane_lab.cli client go `
  --client-profile .\configs\wonderbane-travel.local.json `
  --live --json
```

The default state file is `~/.shadowbane-lab/last-travel-destination.json`. Override it
with `--destination-state` when the harness and client should share a specific state file.
Supplying only one coordinate fails closed.

Named coordinates are not a hand-maintained list. The listener preserves the client-shipped
`ZONE_#NAME` comments and `ZONELOADFILE` names, composes every nested `CENTX`/`CENTZ` through
its parent placement and rotation, and maps the resulting world X/-Z values to LT/LG. It
validates every named point against the installed world's declared bounds before listening.

The calibrated WonderBane build exposes the canonical position vector through the player
object's verified position component. The native reader follows that exact object path and
maps native `x/y/z` to `LT/altitude/-LG`. It requests query/read rights only.

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
right-clicks the calibrated minimap center when a commanded run reaches a terminal state, which
cancels the client's final click-to-move command instead of allowing an arrival overshoot. It
stops on arrival, low player health, focus/profile rejection, emergency stop
(`Ctrl+Shift+F12`), repeated observation failures, click-budget exhaustion, or the session
deadline. Three no-progress checkpoints trigger a bounded reverse-zig-zag, lateral sweep,
and forward bypass. Recovery phases use measured displacement rather than click counts
alone: a blocked sub-leg changes strategy, a cleared bypass reacquires the destination
early, and meaningful manual progress also returns control to direct travel. Each retry
starts on the opposite side and widens its clearance target. The escape budget is finite;
after it is exhausted the controller stops instead of blindly continuing into a wall.
Sustained direct progress resets that budget so unrelated obstacles later in a long route
do not inherit earlier recovery attempts.

The client also ships a native character pathfinder and a `PATHFINDING` preference, currently
disabled in the inspected WonderBane configuration. The historical `/path on` chat command is
not registered in this build, and a previous preference-toggle attempt caused a launch error.
Native pathfinding is therefore out of the live controller path unless its startup failure is
isolated separately. See [client world data](world-data.md).
