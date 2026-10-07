# Automatic desktop fullscreen

This client work is on `codex/client-desktop-fullscreen`, based on the pinned
client baseline in PR #96. The integration destination is `main`; PR #96 must
be included before this branch is integrated. The managed bootstrap worktree and
running client remain independently owned.

The official .14 executable imports and calls `ChangeDisplaySettingsA`, including
`CDS_FULLSCREEN` at VA `0xCA5E43`. Its default preferences request 800x600 fullscreen.
The host reported 800x600 at 60 Hz while that client was running. These facts fit
the user's report of Discord and other windows scaling when the game is active.
They do not establish that Wonderbane introduced the inherited display behavior.

The startup policy selects the current desktop size, retains the existing refresh
rate and DPI configuration, and launches the reviewed client's windowed rendering
path. The launcher owns borderless placement across the selected monitor. It must
verify process/window identity, the actual client-area dimensions, DPI awareness
and unchanged desktop mode before reporting success. No global display-mode or
registry change is part of this policy. Server logic is unaffected.

A different current versus configured desktop mode blocks launch until the other
exclusive fullscreen application closes. Starting a second copy of the same
client directory is also rejected. Existing settings, credentials and client
assets stay in place. The launcher owns only four keys in `Config/ArcanePref.cfg`:
`RESOLUTION`, `FULLSCREEN`, `REFRESH`, and `VIDEOSETTINGSVALIDATION`. It preserves
other bytes, annotations and line endings, rejects duplicate display keys, and
uses atomic replacement without a retained backup. The child-only DPI compatibility
flag does not change registry settings or the environment of other applications.

The `.14` executable does not establish support for the historical manager's
`-windowed -resolution` switches. This launcher uses the actual preference reader
and passes no unverified display arguments. The game renders through its windowed
path while the launcher presents it as a borderless, non-topmost fullscreen window.

## Build and use

Build with `scripts/build-client-desktop-launcher.ps1` using Visual Studio 2022,
Windows SDK, CMake and Python 3.11+. Runtime needs only the resulting
`ShadowbaneLauncher.exe` beside the reviewed `sb.exe`; it has a static C++ runtime
and needs no Python, bot DLL, patcher or administrator privilege.

The default target is the primary monitor. An optional `--monitor` accepts an
exact connected Windows device name such as `\\.\DISPLAY2`. Startup does not
change Windows scale percentages, resolution, refresh rate or other monitors.
Windowed/fullscreen toggles inside the original game remain legacy controls;
use this launcher for the desktop-fullscreen startup policy. Live monitor changes
or an in-game resolution change after readiness are not managed by this launcher.

For read-only inspection, run:

```powershell
.\ShadowbaneLauncher.exe --inspect --client-root C:\Games\ShadowbaneLocal
```

The JSON response reports client-marker verification, current/configured display
modes and readiness. It launches nothing and writes no preferences. Exit code 0
means preflight ready, 2 means a running client or display state blocks launch,
and 1 means a failure. `--report NEW_PATH` optionally saves a new receipt without
overwriting an existing file. Normal launches retain compact receipts in
`LauncherLogs` inside the client directory, without account data or credentials.

Normal startup verifies canonical executable/cache pins, excludes another client
in the same directory, coordinates concurrent launches by the executable's file
identity, prepares display preferences, launches and keeps its process handle,
then requires a unique owned game window. It verifies physical bounds, client
area, DPI awareness, non-topmost styling and two seconds of stable dimensions.
All monitor modes/positions must remain unchanged. Failure leaves an already
started game running and reports the actual state; it never kills the game or
changes the display mode to recover.

Completed: the MSVC build and three native/CLI test groups pass. Coverage includes
negative monitor coordinates, path quoting, DPI environment isolation, marker
hash/write locks, atomic preference replacement, preservation of other settings,
stale window rejection, and inspection failures without gameplay input.
Read-only preflight matched the current client markers and correctly rejected a
second launch; primary current mode was 800x600 while configured desktop was
1920x1080, with two other 1920x1080 monitors unchanged.

## Installed and verified - October 7

The Release launcher from source `f665f106a72b29e69fbd7a489b6562271cc09925`
(implementation `fe500a7c2ae2f467b57933464a6cf97a5830f8e0`) is installed beside the
local client. Its SHA-256 is
`f940a2469cc4fbafba4cae8af25152b849164bf7e92015647d00a321cc670f74`.
The existing `Play-ShadowbaneLocal.cmd` now starts `ShadowbaneLauncher.exe`.
Use that entry for future starts; launching `sb.exe` directly bypasses placement.

The first live start returned `desktop_fullscreen_ready`: the physical client
area and borderless frame matched 1920x1080, DPI awareness was active, and all
three monitor modes/positions remained unchanged. A subsequent inspection
confirmed the desktop was still unchanged. The executable/cache hashes matched,
only `ArcanePref.cfg` changed among configuration files, and all non-display
preference bytes were preserved. No rollback copy was created.

The user responded positively to the live display/input/Alt-Tab acceptance prompt.
This is acceptance of the observed startup, not qualification of every DPI or
monitor arrangement or the entire game/server pairing. The earlier client had
stalled while exiting; its exact process was cleared after the user closed it.
The launcher itself never terminates an existing client.

All 17 hosted checks passed at the installed source revision, including both
launcher jobs. Private installation and live receipts are retained under
`artifacts/magicbane-local-runtime/desktop-fullscreen-20261007/`; no client assets,
settings contents or private captures are published. Source and reproduction
instructions are in [PR #100](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/100).
Next: review and integrate the baseline dependency #96, then #100 into `main`.
The task worktree remains for that review; no startup implementation todo remains.
