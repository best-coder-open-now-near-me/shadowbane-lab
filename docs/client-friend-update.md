# Friend launcher update

This package builds on PR #100 at `540c9a3af03f3f62da883426caf5029d30af7831`.
It uses the same native fullscreen launcher without changing its client pins,
display behavior, or game code. The server runtime is unaffected.

The Windows launcher workflow builds and tests the Release executable, tests the
installer with Windows PowerShell 5.1, and publishes a small ZIP artifact.
The package contains only the launcher, installation/play scripts, instructions,
and a manifest of exact source and file hashes. It contains no game assets,
credentials, user settings, or rollback runtime.

Extract the ZIP, run `Install-ShadowbaneLocal.cmd`, and select the dedicated
private-server client folder containing `sb.exe`. The client must be closed.
The installer verifies package hashes and uses the native launcher's read-only
inspection to enforce compiled executable/cache pins and startup readiness.
It replaces the launcher and play entry, sets only SERVER/PORT in ArcaneIP.cfg
to the private host, and preserves other endpoint lines and client preferences.
Configuration replacement uses an atomic write without a backup. An interrupted
multi-file installation reports failure and can be rerun; it is not a transaction
across all files. Client assets and preferences are never replaced by the installer.

Use `Play-ShadowbaneLocal.cmd` in that folder afterwards. Existing upstream
patchers must not manage this dedicated installation. This ZIP is a launcher
update, not a full client download or an automatic patch service. Tailscale sharing
and per-device host access remain prerequisites. Installation does not start the
game, install services, require elevation, or change network/firewall settings.

Reproduce after the native build:

```powershell
powershell.exe -NoProfile -File scripts/test-client-friend-update.ps1
python scripts/package-client-friend-update.py --launcher build/client-launcher/Release/ShadowbaneLauncher.exe --output build/ShadowbaneLocal-FriendUpdate.zip
```

Validate a friend's machine through installation, launch, mouse alignment,
Alt-Tab and world entry. The earlier live acceptance on the developer's machine
does not establish those results on a different display/client.
