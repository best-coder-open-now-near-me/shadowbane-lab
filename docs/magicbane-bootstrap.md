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

Before launching our paired server, supply a startup/build path that uses the
exact chosen source commit without following a moving branch. Keep the database
and configuration in durable locations, use localhost-facing ports for initial
validation, and preserve all created characters and settings. Use the existing
[deployment policy](deployment-policy.md); no retained fallback deployments.
Neither the default entrypoint nor its account/database configuration scripts
were executed during this investigation.

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

## Remaining qualification and concrete blocker

Complete: identify image/source/database/library provenance, compare embedded
source with Git and compile the original source with its bundled libraries.

**Active next:** recover Docker startup, then import the database and start the
pinned login/world servers with durable data. Afterward verify Wonderbane login,
world listing, character creation, reconnect and persistence before declaring the
client/server pair usable. No database import or live server/client test has run.

Docker Desktop is stopped. Its exact zero-byte `run/dockerInference` reparse point
still returns Windows error 1920 (file cannot be accessed) when queried; exact
non-recursive removal also fails. No Docker settings, disk images, volumes or
runtime directories were removed or renamed. The next recovery attempt is a
user-timed Windows restart, followed by another Docker launch and fresh logs.
A restart is an attempted recovery, not a guaranteed fix. Related reports exist
in [Docker's issue tracker](https://github.com/docker/desktop-feedback/issues/625).
