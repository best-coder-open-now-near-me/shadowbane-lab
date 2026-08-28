# Closed-loop LT/LG travel

Travel uses exact native player coordinates as feedback and guarded right-clicks on the
minimap as the actuator. Start the foreground-scoped chat bridge once per client session:

```powershell
python -m shadowbane_lab.cli client listen-go `
  --destination-state .\last-travel-destination.json `
  --client-profile .\configs\wonderbane-travel.local.json `
  --hotkey-config 'C:\path\to\Wonderbane\Config\SCREEN_GAME_character.cfg' `
  --navigation-cache-directory 'C:\path\to\Wonderbane\cache' `
  --learned-navigation-state .\learned-navigation-state.json `
  --world-def 'C:\path\to\Wonderbane\Config\WorldDef.cfg' `
  --live --json
```

Inside the configured VM, the checked-in launcher starts the same listener in a hidden
process, upgrades a legacy travel-only listener without creating a duplicate, enables the
camp-scoped continuous `/pve` battle command from the current verified hotbar, and writes JSON Lines status
plus errors to the `codexdiag` shared folder:

```powershell
powershell.exe -NoProfile -File \\VBOXSVR\codexrepo\scripts\start-wonderbane-go-listener.ps1
```

The listener no longer requires exactly one character `SCREEN_GAME` file at startup. When one
unambiguous file exists it is supplied automatically; otherwise travel and zone commands remain
available and `/pve` rejects at command time until `-PveHotbarConfig` identifies the reviewed
active character hotbar.

Running the launcher again replaces every process whose command line identifies this scoped
listener, so checked-out code changes take effect without a VM reboot and accidental duplicate
listeners collapse back to one instance.

Stop that background listener by resolving and validating its recorded process identity:

```powershell
powershell.exe -NoProfile -File \\VBOXSVR\codexrepo\scripts\stop-wonderbane-go-listener.ps1
```

While that process is running, enter `/go LT LG` in Shadowbane's chat command line. Enter
`/zone QUERY` first when the canonical destination name is unknown. It fuzzy-ranks up to
five names from the same catalog accepted by `/go`, including active server runegates, and
shows each result with its exact LT/LG plus a ready-to-type `/go NAME` line. The temporary
topmost overlay does not take focus or mouse input, starts no movement, and disappears after
15 seconds. The same result set is written to the listener JSONL log as a `zone_results`
event. For example:

```text
/zone drake swamp
/go Black Drake Swamp
```

The open world map is also a native destination input: right-click a point on the map to
start the same closed-loop `/go` route. Left-clicks retain their normal client behavior.
The listener reads `ArcWorldMapHud`'s live rectangle, hidden state, world dimensions, zoom,
and pan and applies the client's inverse projection; it does not assume a fixed resolution or
full-world zoom. After accepting the destination it closes the map through the current
`BEGINHOTKEYS` WorldMap binding before steering begins, so an extra physical exit click does
not immediately cancel the new route. A right-click is ignored unless the guarded Shadowbane
window owns focus, the world map is open, the pixel lies inside its HUD, and the projected LT/LG
remains inside the active world's bounds. Accepted events use `native_world_map` as their destination source.
Inspect that read-only projection without clicking with:

```powershell
python -m shadowbane_lab.cli client observe-native-world-map --json
```

The installed `WorldDef.cfg` enables client-defined names such as `/go black drake swamp`.
With a navigation cache configured, every coordinate, named, repeated, and world-map route uses
weighted A* over the active zone's terrain height, water, and object-density costs. The terrain
window refreshes after 600 world units and whenever the native current-zone token changes, while
retaining sparse global costs learned earlier in the same listener session. Route smoothing
preserves A*'s weighted-cost choice instead of shortcutting back across water or object-density
cells. If exact position feedback shows
two consecutive steering leases without progress, the controller marks the cell ahead as blocked
and replans around it before falling back to the bounded zig-zag escape sequence. Exact
stall-learned cells are shared by `/go` and `/pve` and atomically persisted by the VM launcher in
`codexdiag/learned-navigation-state.json`, so later routes and listener restarts plan around them
before issuing their first movement lease. Derived terrain costs are rebuilt from client caches
rather than copied into that state file. The final JSON
event reports A* replan count, terrain refresh count, active zone, and navigation revision.
Long-distance travel uses two-second steering leases and an eight-unit progress threshold. Learned
obstacles occupy their measured 20-unit cell without an additional clearance ring, while diagonal
corner cutting remains forbidden; this keeps single-tree and mushroom detours local instead of
turning them into 60-unit exclusion squares.

The planner deliberately keeps exact LT/LG feedback and guarded minimap input as the execution
loop; terrain data supplies route costs and waypoints rather than replacing client movement.

Runegates are different: the listener reads the active registry populated by the server's
CityData message and replaces the incomplete baked `WorldDef.cfg` runegate candidates with
those live records. Each record supplies its object identity, parent-zone label, and exact
LT/LG. `configs/wonderbane-named-destinations.json` remains as a normalized-name and
coordinate override for emulator-confirmed additions or corrections, including Sea Dog's
Rest at LT 88980/LG 45020. A confirmed correction replaces a CityData record with the same
gate name even if the emulator stored a different placement. Other duplicate names resolve
to the placement nearest the exact current player position. The accepted listener event
records whether the result came from the live server registry, static client definition,
or confirmed fallback. `/runegate` is a shortcut for `/go runegate`.
`/go oblivion gate`, `/go death gate`, and `/go doomgate` use the same Runegate candidate set;
the travel controller stops at the gate and does not enter its portal automatically. Unknown
names fail closed and appear as rejected events in the listener log.

Enter `/pve` to run the continuous proc-Assassin battle loop inside a 120-unit lease centered on
the exact LT/LG where the command starts. It returns toward that anchor when the camp is empty or
the player drifts, and it remains active until `/stop`, manual interaction, the emergency hotkey,
player death, a health-safety stop, or a hard observation/input failure.
The in-game command uses exact target health, player vitals, positions, and target action state;
it also projects the active zone's cache-backed height field into its weighted-A* approach map,
adds high traversal cost for explicit zone-local water, then layers stall-learned obstacles onto
that static seed. It does not require the native message HUD to contain a current transcript. Each run writes a
uniquely named final evidence artifact and an incrementally flushed JSONL journal beside the
listener logs. The in-memory trace is a bounded tail rather than an ever-growing session log.
Use `/stop` to
cancel either an active battle or route and immediately clear Shadowbane's last click-to-move
destination through the same guarded minimap-center input path. The listener observes keyboard
events only while the calibrated `sb.exe` window owns foreground focus, never suppresses the
game's input, and retains only text that is still a possible `/go`, `/pve`, or `/stop` command.
Opening chat cancels the bridge's active operation before more automated input is issued. A
physical foreground left, right, or extra-button press does the same, while middle-button camera
rotation remains available and the listener ignores mouse input injected by its own guarded
actuators. This lets manual movement input take ownership immediately without sacrificing camera
control.
An accepted world-map right-click first revokes the old operation, then starts its replacement
route from the resolved native coordinate.
Ordinary chat and all other slash-command prefixes are discarded.

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
The runegate exception is intentional: emulator servers can inject buildings that are absent
from `WorldDef.cfg`, so the calibrated read-only runegate reader follows the client's native
server registry instead. Inspect that registry without moving or selecting anything with:

```powershell
python -m shadowbane_lab.cli client observe-native-runegates --json
```

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
