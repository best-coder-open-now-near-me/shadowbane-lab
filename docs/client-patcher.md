# Private client patcher

The patcher lives on `codex/client-patcher`, based on the accepted desktop
fullscreen source at `540c9a3af03f3f62da883426caf5029d30af7831`. The shared
integration destination is `main`, with baseline PR #96 and launcher PR #100
included before this lane. The normal checkout remains on `main`.

## Ownership and release contract

Players keep a dedicated copy of the pinned Wonderbane x86 client. The patcher
owns our launcher and the `ClientFixes/` directory. Schema 1 deliberately cannot
write the base executable, upstream assets, configuration, logs or player data.
A future base-client migration requires separately reviewed policy and pairing;
publishing a patch manifest cannot expand these write permissions.

A release has a monotonic sequence, display version, source commit, baseline
profile, minimum patcher version, notes and the exact size/SHA-256 of each file.
ECDSA P-256 authenticates the exact manifest payload before parsing its contents.
The public key is built into the patcher; the signing key stays on the release
machine, outside the repository and served feed. Players need no GitHub token.
Distribution is through private Tailscale HTTPS, never Funnel. Signed offline
release folders use the same installation path and remain a supported transport.

The patcher's own application version is separate from fix-package versions.
An unsupported minimum patcher version blocks installation and requires the
current patcher download; this updater does not overwrite its running executable.
The first maintained package is the verified desktop fullscreen launcher.

## Updates, settings and failures

The updater downloads and checks every changed file before modifying the client.
The shared Windows startup mutex excludes updates during a launch or a running
game. A signed pending journal blocks Play until all files match the intended
release. Interrupted installation repairs the same signed release or moves forward to a
newer signed release, with completed files recognized by their hashes. This allows
obsolete feed payloads to be removed without retaining fallback builds. Successful installs retain only compact signed
metadata; no prior runtime or rollback archive is retained. Retired files are
removed only when their bytes match an explicitly signed retirement record.
Changed retired files are preserved and reported.

Offline Play re-verifies the installed signed manifest, every managed file, the
pinned base markers and absence of an unfinished update. Network failure never
authorizes unverified code. Settings, server endpoint and game credentials are
outside the patcher's update ownership.

## Active todos

- Complete: select the release boundaries, private distribution and signed format.
- Complete: 49 engine/publisher/player-CLI checks and three native test groups pass.
- Complete: player window, native startup handoff and standalone release packaging.
- Complete: install signed release 1.0.0 and launch the real client through verified Play.
- Complete: publish source and delivery notes in draft PR #102.
- Active: enable Tailscale Serve and verify the private HTTPS feed/download.
- Next: review/integrate dependencies #96 and #100, then #102 into main.

## Qualified local release — October 7, 2026

Release 1.0.0, sequence 1, was built from
`7b6a8810593834af9cbf7dc917a61c1d858c684e`, committed and pushed on
`codex/client-patcher`. [Draft PR #102](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/102)
targets `main`; it includes the unmerged baseline and launcher dependencies.
Retain the dedicated worktree for review. The normal checkout remains clean on
`main`; no unrelated changes are included.

| Artifact | SHA-256 |
| --- | --- |
| Standalone patcher | `b8fcb1fe3b9915f4b3df10b154839ff60478e86614382bb799f333e121b9f7c6` |
| Desktop launcher | `7eaec31f534bce17d88e90cff222117f03b550bb73c7bb4382e21c2635541032` |
| Signed release envelope | `5e50d370f6ae41fc4a5f896593dc1ad94089e096bcff796283f68278ad8616fa` |
| Portable player download | `1d980513bea3e9956a0099c6151e86dd287d12c5006ba929e6ef9477aef55b5b` |

The actual installed patcher applied the signed offline feed to the local client,
preserved all configuration file hashes, and launched through its verified Play
path. The native report confirmed a physical desktop fullscreen client area and
all three 1920×1080, 60 Hz desktop modes unchanged. There is no pending update
journal. The existing play entry now opens the patcher. Private receipts remain
under the normal project's ignored `artifacts/client-patcher/20261007/`, including
`apply-1.0.0.json`, `play-1.0.0.json` and `live-startup-1.0.0.json`.

The private feed and portable ZIP are prepared on the release host. Tailscale
reported Serve disabled, so HTTPS publication and a friend's download remain
unverified. The tailnet administrator must enable Serve before the maintainer
can complete those checks. No public hosting or Funnel was enabled. This host
must remain online while friends check for or download updates; an already
verified installed release supports offline Play.

## Player setup

1. Connect Tailscale and obtain access to both the game server and the private
   update host. Access to one machine does not establish access to the other.
2. Use the dedicated, pinned Wonderbane x86 client described in the
   [client baseline policy](client-distribution.md). Keep its configured server
   endpoint. The patcher download does not contain the upstream game assets.
3. Extract the private patcher ZIP beside `sb.exe`, retaining all four files:
   `ShadowbanePatcher.exe`, `PatcherFeed.json`, `Play-ShadowbaneLocal.cmd` and
   `Patcher-Readme.txt`.
4. Open `Play-ShadowbaneLocal.cmd`, close the game before updating, select
   **Update / Repair**, then **Play**. Future fix releases use this same entry.

## Build and release ownership

Run `scripts/build-client-patcher.ps1` with .NET SDK 10, Python, CMake and Visual
Studio 2022. It derives baseline markers from the canonical Python profile,
executes 49 failure-oriented checks plus the native tests, and produces a
self-contained `ShadowbanePatcher.exe`. Players do not install Python or .NET.
The public key in `client/patcher/release-public.pem` is compiled into the app.

The named `ShadowbaneClientRelease-friends-v1` signing key is non-exportable in
the release maintainer's Windows CNG user key store. Preserve that Windows user
profile/key as non-reproducible signing data. It is never included in a release,
client install, repository, CI secret, or served directory. Loss of the key needs
an explicit trust-key migration and new patcher distribution. CI tests use fresh
throwaway keys and delete only their own test keys.

`Patcher.ReleaseTool init-key --key NAME --public-key PATH` establishes a signing
identity without replacing a different public key. `publish` takes `--key`,
`--input` (only owned fix files), `--output` (a dedicated feed directory),
`--sequence`, `--version`, `--source` (qualified full Git SHA) and `--notes`.
It signs notes and file hashes, serializes publication, publishes the manifest
last, retires previously owned paths, and removes obsolete payload blobs.
Only compact signed historical manifests remain as receipts.

The portable player download includes `PatcherFeed.json` with `feedUrl` set to
the private HTTPS directory. That host-specific file is generated outside source.
The patcher defaults to the directory beside itself, or the player's last selected
folder. Only that folder preference is saved under LocalAppData. Game credentials
and the game server endpoint remain in the existing client settings.

The UI offers Check, Update / Repair and Play. `--inspect`, `--apply`, and `--play`
provide the same engine for repeatable validation; `--client-root` and `--feed`
select a target, and optional `--report` creates a new JSON receipt. The native
launcher waits briefly on the shared startup lock and refuses an unfinished
`.patcher/pending.json` even when started directly.
