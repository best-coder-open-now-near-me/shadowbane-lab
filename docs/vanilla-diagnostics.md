# Vanilla Shadowbane diagnostics release

This release is the plain-client boundary for streaming and stutter captures. It is published from
`codex/vanilla-diagnostics-release` and must not be replaced with the testing checkout's general
diagnostics package.

## Safety contract

The collector attaches to one exact running `sb.exe` and records its process ID, creation FILETIME,
path, and SHA-256. It accepts only the two reviewed unmodified WonderBane 1.0.5 executable hashes.
Before sampling, it fails closed if it finds a patched executable, `wonderbane-extension.dll`, an
extension deployment receipt, an identity-bound extension heartbeat/status file, an empty module
inventory, or the extension DLL in the target's loaded modules.

The published runtime is standard-library-only and does not import `shadowbane_lab`, graphics
runtime code, client-extension code, camera telemetry, native-position readers, or renderer timing
producers. Final evidence and marker writes are pinned to
`\\VBOXSVR\codexdiag\vanilla-diagnostics`. Samples remain in the collector's memory until sealing,
so the VirtualBox share is not written every frame.

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

## Publish from the host

Publish only from a clean committed checkout of the release branch. The output directory must be the
host folder that backs the plain VM's `codexdiag` share, beneath
`vanilla-diagnostics\packages`:

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
3. Open PowerShell. Run the capture from the exact published package directory. The command blocks
   while the capture is active, so leave that PowerShell window open and return to the game.

```powershell
& '\\VBOXSVR\codexdiag\vanilla-diagnostics\packages\<exact-package>\capture-shadowbane-vanilla-diagnostics.ps1' `
    -ClientExecutable "$env:USERPROFILE\Downloads\WonderbaneClient\Wonderbane\sb.exe" `
    -DurationSeconds 900
```

4. Optional: open a second PowerShell window before returning to the game and use it for phase
   markers. Each invocation finds the sole active vanilla capture and writes one marker.

```powershell
& '\\VBOXSVR\codexdiag\vanilla-diagnostics\packages\<exact-package>\capture-shadowbane-vanilla-diagnostics.ps1' -Marker baseline_sdr
& '\\VBOXSVR\codexdiag\vanilla-diagnostics\packages\<exact-package>\capture-shadowbane-vanilla-diagnostics.ps1' -Marker departed_sdr
& '\\VBOXSVR\codexdiag\vanilla-diagnostics\packages\<exact-package>\capture-shadowbane-vanilla-diagnostics.ps1' -Marker first_stutter -Note 'visible hitch while moving'
& '\\VBOXSVR\codexdiag\vanilla-diagnostics\packages\<exact-package>\capture-shadowbane-vanilla-diagnostics.ps1' -Marker turtles_center
```

5. Let the timer finish. `capture-complete.json` is written last. Closing the game early seals the
   session as `target_exited`; pressing Ctrl+C seals it as `operator_interrupted`.
6. Do not rerun after a preflight rejection until the named residue or executable mismatch is
   understood. The rejected run directory contains `preflight.json` with the exact reason.

The capture never starts, closes, focuses, or sends input to the game. It also does not close the
control center or any unrelated process.
