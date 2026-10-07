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
assets stay in place; only launch-time display arguments and child-process DPI
compatibility flags are owned by this feature.

Completed: startup policy and Windows argument-escaping tests pass under MSVC.
Active next: native launcher integration, build qualification and one live launch after
the existing game closes. No client or shortcut has been changed yet.
