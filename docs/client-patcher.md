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
release. Interrupted installation resumes that same signed release, with completed
files recognized by their hashes. Successful installs retain only compact signed
metadata; no prior runtime or rollback archive is retained. Retired files are
removed only when their bytes match an explicitly signed retirement record.
Changed retired files are preserved and reported.

Offline Play re-verifies the installed signed manifest, every managed file, the
pinned base markers and absence of an unfinished update. Network failure never
authorizes unverified code. Settings, server endpoint and game credentials are
outside the patcher's update ownership.

## Active todos

- Complete: select the release boundaries, private distribution and signed format.
- Complete: 39 update/repair, interruption, path, signature and concurrency checks pass.
- Active: build the player window, native startup handoff and release tooling; commit.
- Next: publish the first private feed, install and validate the actual patcher.
- Next: document delivery and publish the source PR for integration into main.
