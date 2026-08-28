# Automated Windows VM setup

The VM bootstrap installs the development/runtime prerequisites and prepares a local,
live-locked WonderBane calibration. It does not install or modify WonderBane itself.

The script performs these operations in order:

1. Install Git for Windows through `winget` if Git is absent.
2. Install Python 3.12 directly from the Python Software Foundation's `winget` package if a
   compatible Python is absent. Microsoft Store App Execution Alias stubs are ignored.
3. Clone the public `feat/simulator-foundation` branch without GitHub authentication, or
   use the checkout containing the script.
4. Create `.venv` and install the editable project with test and PyAutoGUI dependencies.
5. Copy the tracked template to ignored `configs/wonderbane.local.json` without overwriting
   an existing local calibration.
6. Strictly validate the local profile.
7. Run Ruff and the complete desktop-safe unit test suite.
8. Optionally launch and discover the visible client without depending on foreground focus.

## One-time bootstrap

Open a regular PowerShell window inside the WonderBane VM. Administrator elevation is not
normally required, although Windows may request approval if a package installer selects
machine scope.

Download the script as a file so it can be reviewed before execution:

```powershell
$setupScript = Join-Path $env:TEMP "setup-wonderbane-vm.ps1"
$setupUrl = "https://raw.githubusercontent.com/best-coder-open-now-near-me/shadowbane-lab/feat/simulator-foundation/scripts/setup-wonderbane-vm.ps1"
Invoke-WebRequest -UseBasicParsing $setupUrl -OutFile $setupScript
notepad $setupScript
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setupScript
```

The default checkout is `%USERPROFILE%\shadowbane-lab`. To select another directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setupScript `
    -InstallDirectory "C:\Projects\shadowbane-lab"
```

No GitHub credentials or tokens are used. The repository is cloned over public HTTPS.

## Useful options

- `-InspectClient` performs read-only visible-window discovery. Supply
  `-ClientLauncherPath` with the `.cmd`, `.bat`, or `.exe` used to launch WonderBane. The
  script first looks for an existing visible client from that directory and launches only when
  none is present. Terminal focus does not affect discovery.
- `-ClientDiscoveryTimeoutSeconds` controls how long discovery waits after starting the
  launcher. The default is 90 seconds, which accommodates the software-rendered startup path.
- `-UpdateExisting` updates an existing clean checkout using fetch, switch, and fast-forward
  pull. It refuses to update when tracked changes exist.
- `-SkipPrerequisiteInstall` makes missing Git or Python an error instead of invoking
  `winget`.
- `-SkipTests` skips Ruff and unit tests for a faster repeat installation.

The script never overwrites `configs/wonderbane.local.json`. Delete or rename that local file
manually only when intentionally restarting calibration.

Prerequisite installation is idempotent. Existing exact Winget packages are accepted without
attempting an upgrade, and Git is discovered in both standard machine-wide and per-user
locations even when the current PowerShell session has a stale `PATH`.

To bootstrap and discover the text-fixed client in one command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setupScript `
    -UpdateExisting `
    -InspectClient `
    -ClientLauncherPath "C:\Users\admin\Downloads\WonderbaneClient\Wonderbane\Launch-WonderBane-TextFix.cmd"
```

Discovery enumerates visible top-level Windows windows and accepts exactly one whose owning
process executable is in the launcher's directory. It ignores the foreground terminal by
construction and fails closed if both a patcher and game window match.

## After setup

Launch WonderBane in its permanent window mode, resolution, and Windows scaling. First discover
its identity without changing focus, then focus it and exercise the stricter foreground
inspection used by the input guard:

```powershell
cd "$env:USERPROFILE\shadowbane-lab"
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client discover `
    --process-directory "C:\Users\admin\Downloads\WonderbaneClient\Wonderbane"
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client inspect
notepad .\configs\wonderbane.local.json
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client validate-profile `
    .\configs\wonderbane.local.json
```

Keep `live_input_enabled` set to `false` through calibration and recording-mode verification.
The separate [client-input runbook](client-input-harness.md) covers dry-run and controlled
live enablement.

## Install the VM control center at logon

VirtualBox must expose the persistent `codexrepo` and `codexdiag` machine folders before this
step. Install a VM-local bootstrap and start it immediately with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\install-wonderbane-vm-control-center.ps1 `
  -StartNow
```

The installer writes the operational manager manifest and runner beneath
`%LOCALAPPDATA%\ShadowbaneLab`, creates a desktop shortcut, and creates a current-user Startup
shortcut. The small share-waiting bootstrap is deliberately local so Windows can load it before
the VirtualBox shares are ready. It waits up to 90 seconds and then invokes the current runner
from `codexrepo`, so fetched runner changes take effect on the next logon without reinstalling.
The runner starts the guarded in-game command listener, preflights the manager manifest, and
starts the authenticated localhost dashboard. A listener configuration failure is logged without
hiding the lifecycle dashboard. The dashboard opens automatically but does not launch a game
client until its Start control is used.

The dashboard also watches `%LOCALAPPDATA%\ShadowbaneLab\workers` for strict per-slot worker
heartbeats. The control center does not start bot workers yet: game launch and per-slot worker
bootstrap remain an explicit follow-on. When that bootstrap is connected, each worker must bind
its heartbeat to the manager's exact `client_id` and `instance_id`; a PC name or character role is
not an ownership key. Missing or unhealthy workers keep effective dispatch disabled without
preventing lifecycle inspection, attach, tile, or close operations.

Every live-input worker must also consume its publisher's dynamic dispatch gate. The manager
renews exact allow permits while the binding and worker remain healthy, revokes them for lifecycle
actions and shutdown, and otherwise lets them expire within two seconds. A heartbeat producer that
does not put this gate in its guarded-input stop chain is incomplete and must not be started live.

The manager launches `sb.exe` directly with the reviewed Mesa text-rendering environment. The
listener starts even when several character hotbar files exist; exact hotbar validation is deferred
until `/pve` is requested. Bootstrap and manager logs stay under
`%LOCALAPPDATA%\ShadowbaneLab\logs`; listener evidence stays in `codexdiag`.
