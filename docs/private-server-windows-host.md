# Private Windows host preparation - October 7, 2026

This deployment builds the destination independently from the existing game
server and supports private remote play through an explicit Tailscale overlay. Follow the
[handoff](https://github.com/best-coder-open-now-near-me/shadowbane-lab/blob/245f7d911a0bbb29022b96da1382b27ed9d3a01c/docs/handoffs/private-server-pc-20261007.md)
and [deployment policy](deployment-policy.md). Keep original user data until the
destination is verified and source retirement is authorized. For an explicitly
requested fresh world, leave the original world untouched and skip migration.
Once the destination contains characters, preserve its existing volumes too.

## Source and build

Base deployment: lab `30e66d57133479e399bedf443185dd52f0e3c427`.
Server: `65952a25afe3fc86cb4cf23a5ff375d1b2f854b5`, including credential-safe
logging; complete tree `173a4699d597b8cf0e4bec933b669545839d55ea`.
The MagicBox image digest, seed SQL and all eight application libraries remain
pinned to the qualified pair.

Use an independent clean server checkout at that exact commit. From the lab root:

```powershell
./deploy/magicbane/prepare-source.ps1 -SourceRepository <server-checkout> -OutputDirectory <private-build-input-directory>
```

The helper creates an incremental Git bundle requiring original server commit
`bafb48fe14e5356a64137954cf2d79205835a204`. It contains the two published
commits, not a modified export or a copy of a running deployment. Recreate it
from committed source when needed. Do not commit the bundle, credentials or
runtime data to the lab.

Add `SHADOWBANE_SERVER_SOURCE_CONTEXT=<private-build-input-directory>` to the
private env file described in [the bootstrap guide](magicbane-bootstrap.md).
The image build verifies its embedded base, bundle head, complete tree, seed
SQL and dependency hashes before compiling with networking disabled. It checks
821 Java sources / 970 class files and runs a synthetic credential test that
verifies value preservation, missing-key rejection and absence of values in logs.
It never invokes the upstream mutable build/entrypoint scripts.

The image is `shadowbane-private:65952a25-bloodline-costs`; its OCI revision and
`/opt/shadowbane/build-receipt.txt` record the installed source. Record the actual
image identity and JAR hash from each build. Build timestamps can change JAR
bytes; a revision tag alone is not an installed-image receipt.

## Host and resource bounds

Inspect Windows, virtualization, WSL and Docker compatibility before installing.
Keep machine identities, installed-version inventory and private paths in local
receipts outside source control.

Allocate enough WSL memory for the container while reserving memory for Windows.
Compose caps the server at 5 GiB, four CPUs and 512 PIDs. Login Java uses
128 MiB initial / 512 MiB maximum heap; world Java uses 512 MiB / 2 GiB.
These are initial small-server bounds, not a player-capacity guarantee.
Real remote gameplay and sustained load validation remain required.

## Private networking

Install Tailscale, sign in and use unattended mode for hosting. Keep incoming
connections blocked with `shields-up` until policies are verified. Do not enable
subnet routes, an exit node, Tailscale SSH or Funnel for the game service.

Local Compose still publishes exactly TCP 6000/8000 on 127.0.0.1.
The optional `compose.tailscale.yaml` replaces the ports using `!override`,
requiring Compose 2.24.4 or newer. Obtain `TAILSCALE_IPV4` from this host's
`tailscale ip -4`; never use a sample address. The override sets the advertised
world address to that same IPv4. Validate before starting:

```powershell
docker compose --env-file <private-env-file> -f deploy/magicbane/compose.yaml -f deploy/magicbane/compose.tailscale.yaml config
```

The resolved config must contain only the intended VPN IPv4 and TCP 6000/8000,
with no database/debug/admin publication. Configure Windows Firewall and
Tailscale policy for the intended users/devices and these ports before removing
shields-up or launching remote mode. Audit existing allow-all ACLs/grants:
adding a restrictive rule does not remove existing broader access.

Share this server device with the friend, not broad membership in the user's
network. Consult current [Tailscale sharing guidance](https://tailscale.com/docs/features/sharing).
An actual remote login, world entry and failed access to an unrelated port are
mandatory. Local socket tests do not establish this isolation.

## Destination validation and cutover

A temporary loopback test used the fixed image with no named game-data volumes.
The seed boot reached healthy with 125 base tables, eight views, 179 heightmaps
and about 2.1 GiB memory during startup. TCP 6000/8000 were reachable locally;
3306 and 5000 were not. The new database secret was absent from collected logs.
A clean restart returned to healthy with the same schema and about 1.9 GiB memory.
The four pre-existing NPC-slot content errors (15551, 15895, 16056, 31969)
remain. This is bootstrap qualification only, not real character persistence.

Before replacing the original host:

1. Finish policy review and obtain the actual client/source device identities.
2. Agree on a source cutover window. Stop game writes and shut down login/world
   and MySQL cleanly using the existing source runtime procedure.
3. Privately transfer a consistent set of the actual database, world-data and log
   volumes (`shadowbane-local-database`, `shadowbane-local-world-data`,
   `shadowbane-local-logs`), preserving numeric ownership and settings. Record
   transfer hashes and private row-count/state receipts. Logs may contain old
   passwords: never publish them or put them in a friend package.
4. Populate previously empty destination volumes with the transfer, not the seed.
   Use the independently generated destination service-account secret; startup
   provisions that account. Preserve the source world name and other settings.
   Do not overwrite any populated destination volume without inspecting it.
5. Verify transferred hashes/state, login with an existing account, load the
   existing character/inventory/location, save, restart cleanly and reconnect.
   Complete remote world-entry and blocked-port checks and observe stability.
6. Retire the source only after destination acceptance and explicit authorization.
   Remove completed transfer staging when verified; retain no rollback runtimes
   or deployment archives. Preserve original user data and private diagnostics.

If the source resumes accepting changes after export, that transfer is stale;
do not declare cutover complete. Do not run volume pruning or factory reset.

The matching client can use `Config/ArcaneIP.cfg` with `SERVER= <VPN IPv4>`
and `PORT= 6000`, launching `sb.exe` directly. Preserve user settings; verify the
full official client hash and manifest before deployment. Additional launcher
server-menu entries have not been qualified by this checkpoint.

## Human and Elven bloodline creation costs

A valid build with Born of the Taripontor showed nine points remaining in the
client but was rejected with minus one by the paired server. Its seed charged
ten points for each Human bloodline. The qualified official client charges zero
for all five Human bloodlines: Ethyri (252129), Taripontor (252130), Gwendannen
(252131), Invorri (252132), and Irydnu (252133). The same mismatch also affects
all three Elven bloodlines: Dar Khelegeur (252134), Gwaridorn (252135), and
Twathedilion (252136). Race starting allowances remain unchanged.

Evidence is the [official manifest](http://87.99.132.84/manifest.json), SHA-256
`22e083d1ef09aa94ced7380cc7e2bf994e69b3a3d8450f319c8f19c4dabbb95c`, and
its [CObjects.cache](http://87.99.132.84/client/cache/CObjects.cache), SHA-256
`08c115baeef5da811f7ee2802ccdc1002cfeba29cf1818956c452e3e594efef6`.
The [official ArcRune decoder](https://repo.magicbane.com/MagicBane/mbEditorPro/src/commit/75efa29012592d7d0e35ebfd0703990f90f10995/mbEditorPro2.0/arcane/objects/ArcRune.py)
decoded all eight records completely and returned `rune_creation_cost = 0`.
The same decode confirmed unchanged comparison costs: Fleet of Foot 10,
Lightning Reflexes 12, Lucky 8, Precise 8, Taught by Master Thief 8, Tough Hide 12.
Client assets and private gameplay logs are not included in source control.

The `65952a25-bloodline-costs` image retains the exact credential-safe Java source,
libraries and original seed SQL. Before starting either Java process, it runs
`bloodline-costs.sql` against the existing database. This transaction
changes only the eight cost attributes, so creation, later rune application and
point recalculation use the same corrected values. It leaves character rows,
race allowances, other costs, prerequisites and overspending checks intact.

Startup requires InnoDB, exact rune identities, one cost row per rune, and
costs of either the original ten or corrected zero. Unexpected custom costs,
missing/duplicate rows or a failed update abort startup. The batch client must
never use `--force`; connection closure rolls back an incomplete transaction.
Repeated startup is idempotent. The build receipt includes the migration hash.

Run `test-bloodline-costs.sh` in a disposable image container with MySQL
started, no live data mounts and no published ports. It verifies the eight-row
change, all unrelated static rows, repeat application, upgrade from an already
corrected Human-only database, the reported nine-point
balance, rejection cases and transaction failure. It uses only a synthetic test
database seeded from the image's static tables.

Deploy after a clean save/logout and verify the same existing character and the
previously rejected build after restart. Do not reseed populated volumes or keep
the superseded image/container for rollback.

The full Human/Elven correction passed isolated migration tests, including
upgrading the previously corrected Human-only database, and a complete
login/world startup. The live update returned healthy. Account, character and
item table checksums were identical before and after deployment; the existing
character was preserved. The database secret was absent from startup logs, and
VPN policy, firewall and port-publication guards passed. Temporary test
containers and the superseded runtime image were removed. Client build retry,
world entry/reconnect, remote port-isolation checks and reboot startup remain
pending.
