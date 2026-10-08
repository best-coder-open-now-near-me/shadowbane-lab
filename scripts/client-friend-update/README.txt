SHADOWBANE LOCAL - FULLSCREEN UPDATE

1. Close Shadowbane. Keep Tailscale connected.
2. Extract this ZIP, then double-click Install-ShadowbaneLocal.cmd.
3. Choose YOUR DEDICATED PRIVATE-SERVER CLIENT FOLDER (the folder containing sb.exe).
   Do not select a client folder you still use for another server.
4. Launch Play-ShadowbaneLocal.cmd inside that client folder from now on.

This update installs the desktop-fullscreen launcher and sets only SERVER and
PORT in Config/ArcaneIP.cfg to 100.87.213.55 and 6000. Other client settings stay
in place. The launcher adjusts four display settings at startup for your desktop.
It does not install game assets, change Windows display modes, or run the game
as administrator. It requires the reviewed .14 executable and October 7 cache.
A mismatched client is rejected before the installer changes anything.

Use Play-ShadowbaneLocal.cmd for this server. Running sb.exe directly bypasses
the fullscreen fix. Do not run the other server's patcher in this folder: it can
replace files or change the server address. This is a launcher update, not a
replacement for the game's full installer or a background auto-updater.

Tailscale sharing and host authorization are still required. On connection
failure, run these commands in PowerShell; both should say True:
Test-NetConnection 100.87.213.55 -Port 6000
Test-NetConnection 100.87.213.55 -Port 8000

No rollback copies are created. Rebuild the launcher from the source revision
in package.json if needed. Keep your existing game installation and settings.
