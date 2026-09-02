# Vanilla Shadowbane diagnostics release

This release is the plain-client boundary for streaming and stutter captures. It is published from
`codex/portable-vanilla-diagnostics` as a portable Windows application and must not be replaced
with the testing checkout's general diagnostics package.

## Portable physical-PC release

The supported end-user package is the GitHub Release ZIP named
`ShadowbaneVanillaDiagnostics-<version>-win-x64.zip`. Its only runtime requirement is 64-bit Windows
10 or 11. It does not require Python, Git, a repository checkout, a VM, or an installer.

Download the ZIP and its `.zip.sha256` sidecar, verify the ZIP with `Get-FileHash`, extract the whole
folder to a normal writable location, start one vanilla `sb.exe`, and run
`ShadowbaneVanillaDiagnostics.exe`. The native window performs the non-capturing vanilla check,
starts and gracefully seals captures, adds hotspot markers, and creates a shareable evidence ZIP.
All evidence stays beneath the extracted application's `evidence` folder.

The executable is intentionally self-verifying but is not commercially code-signed. Windows may
show an unrecognized-app warning. Do not disable Defender or SmartScreen globally; proceed only
after the downloaded ZIP matches the checksum attached to the official GitHub Release.

## Safety contract

The collector attaches to one exact running `sb.exe` and records its process ID, creation FILETIME,
path, and SHA-256. It accepts only the two reviewed unmodified WonderBane 1.0.5 executable hashes.
Before sampling, it fails closed if it finds a patched executable, `wonderbane-extension.dll`, an
extension deployment receipt, an identity-bound extension heartbeat/status file, an empty module
inventory, or the extension DLL in the target's loaded modules.

The published runtime is standard-library-only and does not import `shadowbane_lab`, graphics
runtime code, client-extension code, camera telemetry, native-position readers, or renderer timing
producers. Final evidence and marker writes are pinned beneath the verified portable package.
Samples remain in the collector's memory until sealing, so the disk is not written every frame.

Captured channels are:

- exact process identity, CPU, memory, I/O, handles, and GDI/USER objects at 5-10 Hz;
- exact-process TCP/UDP endpoint metadata at 1 Hz, with no packet payloads;
- window bounds, visibility, foreground ownership, minimized/maximized/hung state;
- time since the last system input and cursor position, with no keys or message content;
- a 16x9 SHA-256 fingerprint of the visible client surface, with no pixels retained;
- DWM compositor counters when available; and
- create-only operator markers.

The visible-surface fingerprint identifies repeated or changing displayed images while the player is
moving. It is useful frame-change evidence, but it is not an exact application-present timer. DWM
counters are also monitor/compositor scope. Exact `SwapBuffers` timing is intentionally excluded
because obtaining it from the client would cross the vanilla boundary.

## Build and publish

The release workflow is `.github/workflows/release-vanilla-diagnostics-portable.yml`. A tag named
`vanilla-diagnostics-portable-v<version>` builds on a 64-bit Windows runner with locked packaging
tools, runs the packaged executable's self-test, and publishes the ZIP plus checksum to GitHub
Releases. The local equivalent is:

```powershell
python -m pip install -r .\requirements\vanilla-diagnostics-portable-build.txt
& .\scripts\build-shadowbane-vanilla-diagnostics-portable.ps1 `
    -Version '<version>' `
    -OutputDirectory '<artifact-directory>'
```

The build refuses a dirty checkout or an existing output, inventories the executable and README,
embeds the exact source revision, and runs the frozen app's read-only self-test before producing the
ZIP.

## Legacy VM package

The earlier source package remains available for the previous plain-VM workflow. Publish it only
from a clean committed checkout. The output directory must be the host folder that backs the plain
VM's `codexdiag` share, beneath `vanilla-diagnostics\packages`:

```powershell
& .\scripts\publish-shadowbane-vanilla-diagnostics.ps1 `
    -OutputDirectory '<codexdiag-host-path>\vanilla-diagnostics\packages'
```

The publisher creates a new immutable version/revision directory, inventories every executable
input, records hashes and lengths in `package-manifest.json`, and runs package self-verification.
It refuses dirty source and existing destinations.

## Plain VM lifecycle

1. Use the plain VM and its unmodified client. Do not launch a graphics, cel, diagnostics-extension,
   or testing client.
2. Launch the intended `sb.exe`, log in, and reach the starting position.
3. Run the non-capturing preflight first. It writes a small result to `codexdiag`, reports whether
   the exact process is accepted, and explicitly does not start the timed sampler.

```powershell
& '\\VBOXSVR\codexdiag\vanilla-diagnostics\packages\<exact-package>\capture-shadowbane-vanilla-diagnostics.ps1' `
    -ClientExecutable "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\sb.exe" `
    -PreflightOnly
```

4. Run the capture from the same exact published package directory. The command blocks
   while the capture is active, so leave that PowerShell window open and return to the game.

```powershell
& '\\VBOXSVR\codexdiag\vanilla-diagnostics\packages\<exact-package>\capture-shadowbane-vanilla-diagnostics.ps1' `
    -ClientExecutable "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\sb.exe" `
    -DurationSeconds 900
```

5. Optional: open a second PowerShell window before returning to the game and use it for phase
   markers. Each invocation finds the sole active vanilla capture and writes one marker.

```powershell
& '\\VBOXSVR\codexdiag\vanilla-diagnostics\packages\<exact-package>\capture-shadowbane-vanilla-diagnostics.ps1' -Marker baseline_sdr
& '\\VBOXSVR\codexdiag\vanilla-diagnostics\packages\<exact-package>\capture-shadowbane-vanilla-diagnostics.ps1' -Marker departed_sdr
& '\\VBOXSVR\codexdiag\vanilla-diagnostics\packages\<exact-package>\capture-shadowbane-vanilla-diagnostics.ps1' -Marker first_stutter -Note 'visible hitch while moving'
& '\\VBOXSVR\codexdiag\vanilla-diagnostics\packages\<exact-package>\capture-shadowbane-vanilla-diagnostics.ps1' -Marker turtles_center
```

6. Let the timer finish. `capture-complete.json` is written last. Closing the game early seals the
   session as `target_exited`; pressing Ctrl+C seals it as `operator_interrupted`.
7. Do not rerun after a preflight rejection until the named residue or executable mismatch is
   understood. The rejected run directory contains `preflight.json` with the exact reason.

The capture never starts, closes, focuses, or sends input to the game. It also does not close the
control center or any unrelated process.
