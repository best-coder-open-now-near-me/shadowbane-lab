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
step. Close every game client, then install two isolated guest-local runtimes and start the control
center with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\install-wonderbane-isolated-runtimes.ps1 `
  -ClientCount 2 `
  -StartNow
```

The installer accepts only the reviewed official `sb.exe` hash and the reviewed unmodified
`Textures.cache` hash. It rejects an extension DLL or package marker in the source directory,
stops only identity-checked manager/listener processes, checks local disk capacity, and freezes the
vanilla client beneath `%LOCALAPPDATA%\ShadowbaneLab\client-baselines`. It then applies the pinned
extension package independently to:

```text
%LOCALAPPDATA%\ShadowbaneLab\client-runtimes\vanilla-<UTC timestamp>\
├── client-01\
└── client-02\
```

Each directory has its own `Config`, `Logs`, `DoubleFusion`, and cache tree. After all slot copies
verify, one compare-and-swap manifest update points each slot at its unique directory. A failure
before that update removes only the new unpublished deployment and leaves the current manager
manifest byte-for-byte unchanged. The immutable source baseline is never launched. The deployment
also retains hash-pinned local bootstrap inputs; the dashboard uses them to publish one new isolated
runtime whenever **Add client** exhausts the currently provisioned slots.

The same script writes the operational manager manifest and runner beneath
`%LOCALAPPDATA%\ShadowbaneLab`, creates a desktop shortcut, and creates a current-user Startup
shortcut. The small share-waiting bootstrap is deliberately local so Windows can load it before
the VirtualBox shares are ready. It waits up to 90 seconds and then invokes the current runner
from `codexrepo`, so fetched runner changes take effect on the next logon without reinstalling.

The runner uses fixed loopback port `52739` plus a persistent random token beneath the same local
state root. Existing dashboard tabs therefore reconnect after manager restarts instead of becoming
dead controls on an abandoned ephemeral port. During the restart window, all action buttons are
disabled and the page reports the unavailable manager explicitly.

Every isolated slot launches a full 1920x955 client and has no resize tile. The windows overlap
because Shadowbane clips its render surface when its outer window is resized; the existing
1920x955 automation calibration therefore remains exact. A second smaller layout needs its own
observed profile. **Add client** grows this layout one verified runtime at a time without cloning a
live directory. Rerun the isolated-runtime installer with a new `-ClientCount` only when replacing
the complete deployment or changing its baseline, patch inputs, or calibrated resolution.

The older tiled-slot wrapper remains only for non-isolated test manifests:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\configure-wonderbane-client-count.ps1 `
  -ClientCount 4 `
  -Restart
```

It refuses an isolated tile-less manifest. The low-level `configure-build` command also refuses
multiple slots, preventing all slots from being retargeted to one mutable directory.

The dashboard also owns strict per-slot workers beneath
`%LOCALAPPDATA%\ShadowbaneLab\workers`. Start, attach, and resume ensure one worker exists for the
slot's exact `client_id` and `instance_id`; a PC name or character role is not an ownership key.
The worker independently verifies the game PID, process creation time, and HWND on every heartbeat.
Pause denies dispatch without killing the worker, while detach and close send an identity-bound
orderly stop request. Missing or unhealthy workers keep effective dispatch disabled without
preventing lifecycle inspection, attach, tile, or close operations.

Every live-input worker must also consume its publisher's dynamic dispatch gate. The manager
renews exact allow permits while the binding and worker remain healthy, revokes them for lifecycle
actions and shutdown, and otherwise lets them expire within two seconds. The current worker host is
the permanent exact-identity and dispatch boundary; travel, PvE, and later group strategy services
must run behind its gate rather than creating another process-ownership mechanism.

The manager launches `sb.exe` directly with the reviewed Mesa text-rendering environment. The
listener starts even when several character hotbar files exist; exact hotbar validation is deferred
until `/pve` is requested. Bootstrap and manager logs stay under
`%LOCALAPPDATA%\ShadowbaneLab\logs`. Every manager startup gets an immutable timestamped run
directory plus `manager-latest.json`; every listener start gets its own `go-listener-runs`
directory plus `go-listener-latest.json`. The convenience latest preflight may be overwritten,
but the per-run preflight/stdout/stderr evidence is retained. Listener behavior evidence stays in
`codexdiag`.
