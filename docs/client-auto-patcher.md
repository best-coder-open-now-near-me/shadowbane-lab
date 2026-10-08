# Complete client and automatic patcher

This replaces the earlier launcher-only friend installer. The standalone Windows
`ShadowbanePatcher.exe` installs the complete pinned client into an empty folder,
updates an existing dedicated client, repairs altered files, and starts the
verified desktop-fullscreen launcher. Future starts through
`Play-ShadowbaneLocal.cmd` check our published release before enabling Play.

## Release ownership

The patcher reads only our fixed HTTPS channel at
`codex/client-release-channel/channel.json` in this repository. That small
channel record pins an immutable release manifest by SHA-256. The manifest pins
each bundle and each client file. All runtime downloads come from this
repository's GitHub release assets. The patcher never reads Wonderbane's live
manifest or downloads from the upstream host.

The initial release contains all 211 files from the official manifest with
SHA-256 `22e083d1ef09aa94ced7380cc7e2bf994e69b3a3d8450f319c8f19c4dabbb95c`,
plus the reviewed desktop-fullscreen launcher and seed display preferences.
The build script verifies the entire source inventory before packaging. The
original publisher's game files and notices remain included. These asset bytes
are release artifacts, never Git source content.

Our releases advance only after deliberately selecting, testing, and publishing
a compatible client/server pair. Publish versioned bundles and the immutable
manifest first; anonymously verify them, then atomically update the channel
branch's JSON pointer. Never point the channel at incomplete uploads or mutable
upstream assets. The source baseline inventory is in
`native/client_patcher/baseline.manifest.json`.

## Player behavior

Download the patcher, select an existing dedicated client folder or an empty
folder, then click Install / update. New installation downloads the full client;
existing installs hash files and fetch only bundles needed for repair/update.
The patcher installs itself and a Play entry into that folder. Use the Play entry
for subsequent sessions. Tailscale sharing and the host's device allowlist still
govern game access; publishing client downloads does not open game ports.

Config .cfg files and DoubleFusion state are seed-only; existing values survive.
The patcher owns only SERVER and PORT in ArcaneIP.cfg and preserves its other
lines. The fullscreen launcher owns its existing four display preferences.
Unlisted files, screenshots, credentials, logs, and other settings are not deleted.
No other launcher or patcher manages this dedicated install.

The patcher requires a closed game, verifies every changed file before replacing
it atomically, blocks Play on errors, and discards downloaded bundles and staging
files afterwards. It keeps no rollback runtime. A power loss may leave an
incomplete staging file; normal cancellation is cleaned up. A subsequent repair
revalidates files before Play. Multi-file updates are resumable repairs, not
database-style transactions. Network failure blocks update completion; no
unverified/offline launch fallback is added.

The version-1 patcher updates client files and the fullscreen launcher. A future
release that needs a new patcher protocol reports that requirement before any
changes; replacing the running patcher itself is not implemented.

## Validation and reproduction

`scripts/build-client-patcher.ps1` builds with the Windows .NET Framework compiler
and runs the offline engine checks. No Python or compiler is needed by players.
Windows CI repeats this build and test sequence.

`scripts/build-client-release.py` builds bundles from a verified official client
tree, the exact launcher executable, and the tested patcher. It writes an immutable
manifest, channel candidate, and hash list. The release validation executable
uses the same engine to install the entire actual release, damage and repair one
executable, and verify a second unchanged run downloads nothing. It confirms
personal preference and server-selection preservation without launching the game.

Friend-specific fullscreen/input/world-entry testing remains a live acceptance
step; a successful package check does not claim those observations.
