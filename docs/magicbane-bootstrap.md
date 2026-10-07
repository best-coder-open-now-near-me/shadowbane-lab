# Magicbane bootstrap pairing — October 7, 2026

## Verified starting point

The public MagicBox image contains a recoverable source/data combination. Select
its embedded source revision for **initial bootstrap qualification**, with the
Wonderbane client selected in PR #96 as an unverified client candidate. This is
not a production-readiness claim. The newer `magicbox-1.5.2.1` source candidate
cannot simply be substituted into these inputs.

The [machine-readable receipt](../research/magicbane/bootstrap-pairing-20261007.json)
contains exact identities, library hashes, terrain hashes and validation limits.
No SQL records, credentials, client binaries or dependency JARs are published.

| Component | Verified identity |
| --- | --- |
| Public image | `docker.io/magicbane/magicbox@sha256:20050d2a9a1e59deb83a270f78e5cd2111c5fc0a786651de0f0c1c39c56214a2` |
| Image config | `914b44d019597f0e20b9181a6429576948913670a301b7a79114356c69074ed8` |
| Embedded server source | `bafb48fe14e5356a64137954cf2d79205835a204`, August 9, 2023 |
| Public SQL dump | `cbc0bb3607d6ba9fafa4b7ad5270ff2086cfb9814012d9671a2087e330a37226`, 13,115,683 bytes, 125 CREATE TABLE definitions |
| Data layer | `7275e5608da5b07188e4ab81a2e66a3947c940378b73dfce1a59c83c9a55225b` |
| Application-library layer | `843fb025821ce5c1dbc3204fdc431fea687c1b95d6445c4c630f5b222a6e7a80` |

The image config and SQL hashes match the historical MagicBox provenance already
recorded in our equipment catalog. This identifies the same public dataset; it
does not make that dataset current Wonderbane game data.

The official [MagicBox documentation](https://repo.magicbane.com/MagicBane/Server/wiki/MagicBox-:-Magicbane-in-a-Box)
describes a bundled database and operational scripts. We checked the image
contents rather than treating that older documentation as a current release
manifest. The checked public tag remains an August 2023 image.

## Source and build verification

The image's `build/Server/.git/HEAD` references `refs/heads/master`, whose loose
ref contains `bafb48fe14e5356a64137954cf2d79205835a204`. That commit exists in the
public repository's history. All 821 embedded Java source files match a Git
archive of the commit after CRLF/LF normalization. None are byte-identical before
normalization; the complete comparison found no substantive differences.

A local Java 8 compilation of that Git-exported source against the image's eight
application libraries passed: 821 Java files produced 970 class files, exit 0.
The only compiler notes concern unchecked operations. This was a Windows build
using portable Amazon Corretto 8.504.04.1; it is not an execution test of the
image's Linux OpenJ9 runtime. Compiler archive SHA-256:
`7eaaa3fdc72fe39b466f6d18d1e30ada75cad21363c7c2544f2177c9bb090de6`.
The official [Corretto download reference](https://docs.aws.amazon.com/corretto/latest/corretto-8-ug/downloads-list.html)
provides the vendor checksum endpoint; the receipt pins the resolved version URL.
The archive was removed after verified extraction. Nothing was installed globally.

The bundled application libraries are EnumBitSet, HikariCP 4.0.3,
JDA 4.2.0_168, Joda-Time 2.3, MySQL Connector 8.0.23, SLF4J API/simple 1.7.7 and
TinyLog 1.3.5. Retain the exact hashes from the receipt when reproducing this
result. Do not silently resolve today's versions of those dependencies.

## Why the newer source does not match these inputs

At `9866632ad5aa083165170202d508a95e2bc556ba`:

- `dbItemHandler.java` queries `static_item_templates`; the inspected dump has no
  such table. `ItemTemplate.java` documents JSON exported from mbEditor Pro 2.1.
- `ItemTemplate` and other classes import `org.json.JSONObject`; none of the eight
  inspected application JARs contains that class. This is a check of those JARs,
  not an exhaustive inventory of every operating-system package in the image.
- `PowersParser.java` reads `mb.data/wpak/Powers.cfg`; that path is absent from the
  inspected data layer. The layer supplies SQL, terrain and realm maps instead.

These are concrete missing inputs, not evidence that the newer source is broken.
Upgrading requires the matching database migration/content export, power data and
library definitions. Do not manufacture empty tables or stub effects to make a
startup appear successful. `subdate2` remains a separate source candidate, not a
verified solution to those missing inputs.

## Startup must retain the pin

The inspected default `dockerentry.sh` sets the build branch to `master`, can
change it from a supplied `.mbp` filename, then calls `mbbuild.sh`. That script
fetches, checks out and pulls a branch before compiling. Consequently an image
digest alone does **not** pin the server code that default startup runs.

The tracked [Dockerfile](../deploy/magicbane/Dockerfile) verifies that exact Git
revision and a clean embedded source tree, compiles it with the bundled Linux
Java/Ant toolchain, and extracts the bundled heightmaps. Its own entrypoint never
runs the upstream branch-pulling or database-reset scripts.

The [Compose configuration](../deploy/magicbane/compose.yaml) publishes only
`127.0.0.1:6000` (login) and `127.0.0.1:8000` (world). It retains MySQL, world
files and logs in named Docker volumes. Docker seeds those volumes from the image
on their first use; subsequent starts reuse them without importing or dropping
SQL. The seed contains 125 base tables and eight views. The healthcheck verifies
both Java children, both listening ports and database availability. Component
failure stops the container; it does not silently restart into a partial server.

Supply an env file outside the managed worktree with these values:

```dotenv
SHADOWBANE_DATABASE_PASSWORD_FILE=E:/Projects/shadowbane/artifacts/magicbane-local-runtime/database-password
SERVER_WORLD_NAME=ShadowbaneLocal
SERVER_EXTERNAL_ADDRESS=127.0.0.1
```

The password file contains 64 random hexadecimal characters; preserve this file
and the env file in place. It is a read-only Compose secret, not a committed
credential. This host's files are already provisioned. On another host, generate
a fresh password once and use its own absolute path. Startup accepts LF/CRLF.
World names permit letters, digits, underscore and hyphen: the original login
server shells out to read its population file and crashes on names with spaces.

From this repository, using the absolute env-file path:

```powershell
docker compose --env-file E:/Projects/shadowbane/artifacts/magicbane-local-runtime/compose.env -f deploy/magicbane/compose.yaml up -d --build
docker compose --env-file E:/Projects/shadowbane/artifacts/magicbane-local-runtime/compose.env -f deploy/magicbane/compose.yaml ps
```

Use `stop` to shut down and `start` to resume the existing server. Do not use
`down --volumes`, volume pruning or a Docker factory reset on the populated
runtime. Follow the [deployment policy](deployment-policy.md): preserve user data,
rebuild software from its committed source, and retain no fallback deployments.
Upstream configuration logging includes the database password; keep these logs
private and redact secrets before sharing diagnostics. Database port 3306 and
debug port 5000 are not published. Automatic game-account registration is enabled.

This endpoint is for a client on the Windows host. A VM's own `127.0.0.1` cannot
reach it; VM access needs an explicit host/guest route and a matching advertised
world address. Do not treat Docker port availability as client compatibility.

## Local evidence and ownership

This lane uses the existing managed `client-api-baseline` worktree on branch
`codex/magicbane-runtime-pairing`, based on main `cdaafb234cfe324cc1c750c77102cfcc76552f50`.
The earlier `codex/client-api-baseline` branch and PR #96 remain published intact.
The normal project checkout remains on `main`.

Ignored inputs and diagnostic evidence live in
`artifacts/magicbane-runtime-pairing` in this worktree: the Git source export,
eight JARs, public SQL, terrain, inspected scripts, portable compiler, build output
and receipts. These are current bootstrap inputs/evidence, not deployment rollback
copies. Do not edit the exported source as a substitute for a tracked server branch.
Recover inputs from the pinned registry layers and source commit; do not upload
local binary/data captures to the source PR.

The **Continue PvE/PvP bot work** chat owns the authoritative gameplay migration
mapping in PR #95. It must remap source entry points to the chosen qualified base;
its historical `3649c629` references are not this image's embedded revision.
This lane owns source/data/bootstrap qualification and the client pairing.

## Live startup result and remaining qualification

On October 7, the pinned Linux image build succeeded. Login and world completed
bootstrap, including 179 heightmaps. Both listening ports and the healthcheck
passed. A clean Compose restart returned to healthy using the same database,
world-data and log volumes; 125 tables and eight views remained available.
This verifies server bootstrap and volume reuse, not character persistence.

The first attempts exposed two configuration issues now handled by startup:
Windows CRLF in the database secret and a space-containing world name. The
bundled content also logs NPC slot errors (15551, 15895, 16056, 31969) and an
initial loot-ID warning. These do not prevent startup, but are unresolved content
qualification findings; the server is not declared production-ready.

Docker recovered after the user's factory reset and fresh IPC socket paths.
Before the first server deployment, Docker reported no containers or volumes.
The reset was performed by the user, not by the startup tooling. Three inspected
runtime directories were renamed because their zero-byte AF_UNIX reparse sockets
could not be unlinked (Windows error 1920):

- `%LOCALAPPDATA%/Docker/run-inaccessible-sockets-20261007`
- `%LOCALAPPDATA%/Docker/run-inaccessible-sockets-20261007-after-reset`
- `%LOCALAPPDATA%/docker-secrets-engine-inaccessible-socket-20261007`

These inaccessible IPC leftovers contain no deployment, settings or database
backup. They remain diagnostic leftovers pending exact-path cleanup when Windows
permits it. Do not reset Docker again to remove them. Related failure reports are
in [Docker's issue tracker](https://github.com/docker/desktop-feedback/issues/625).

## Dedicated host client

The first real login reached the server but was rejected with
`Major Version Failure: 1.3.38.14`: the bundled configuration still expected
`1.2.26.0`. Startup now explicitly sets `MB_MAJOR_VER=1.3.38.14`, matching our
pinned executable while retaining the exact-version check. This configuration
correction is not proof of the remaining message/model compatibility.

The independent active install is `C:/Games/ShadowbaneLocal`. All 211 official
files (2,309,329,106 bytes) were verified against reviewed manifest
`22e083d1ef09aa94ced7380cc7e2bf994e69b3a3d8450f319c8f19c4dabbb95c`.
203 exact matching files were read from the older local install; eight changed
files were obtained from the official patch source and checked against the pins.
No user settings or credentials were copied. The testing VM and Umbra session
remain separate and unchanged by this setup.

The sole official-file override is `Config/ArcaneIP.cfg`, now advertising login
at `127.0.0.1:6000`. `Play-ShadowbaneLocal.cmd` starts `sb.exe` directly in its own
working directory. No upstream patcher or bot extension is required or launched.
The official executable remains `e703e7...`; CObjects remains `08c115...`.
A post-launch verification passed for every official file, allowing only the
explicit endpoint override. The game process opened a responding Shadowbane
window; this is not proof of login or character loading.

A full local file receipt is retained in the main checkout's ignored
`artifacts/magicbane-local-runtime/client-install-receipt.json`. Preserve game
settings created in this active install. Reconstruct official files from that
pinned manifest and their official source; do not retain rollback installs.

After the version correction, the user reported successful login, world entry,
normal play and a character death. These are user-observed acceptance results,
not an instrumented combat or persistence qualification.

Automatic registration creates the local account on first login. The original
server logs auto-registration passwords as well as its database password, so use
a new local-only password, keep logs private and redact AutoRegister lines from
shared output. Credential-log removal has been handed to the server-source lane.
**Active next for local bootstrap:** verify respawn, reconnect and saved character,
inventory and location. Full client/server compatibility and actual save/reload
remain unverified. The user's separate starter-inventory capture request targets
Wonderbane in the testing VM, not this local server.
The peer's model inventory owns client/server content alignment; bootstrap health
is not that proof.

## First-session findings still under investigation

- **Health:** the user reports sitting appears to fill health, then the next hit
  snaps it back to the base-health range. A guarded, read-only official-client
  snapshot recorded maximum health 1,066.5 at level 1. The server clamps both
  regeneration and damage updates to its own calculated `healthMax`. Race/class,
  effect-data and client calculation alignment remain open; no measured server
  in-memory maximum or exact flat-offset cause has been established. Do not add
  1,000 HP merely to make the display agree.
- **Loot:** the user reports no drops from Hulda, Winter Harpy and White Wolf.
  The running database contains 614 generator rows, 3,099 item rows and 22,745
  drop-set rows. Mob loot is enabled, normal drop/gold multipliers are 1.0, and
  all three mob bases reference populated drop sets. Their gold roll is about
  60%, with additional item rolls; not every kill must drop something. No
  source-type rejection was found in the inspected loot logs. Next establish
  whether a corpse window is empty or fails to open, then trace that request.

One user-requested Greater Concoction Potion was created through the server's
existing `item_CREATE` procedure with its template's five charges. The user
returned to character selection before a clean restart reloaded inventory.
The exact character/item receipt remains private in the main checkout's
`artifacts/magicbane-local-runtime/potion-grant-20261007.json`; do not replay the
grant. The item row was verified after restart; client visibility is pending user
confirmation. No loot-rate, character-stat or administrator-privilege changes
were made during these checks.
