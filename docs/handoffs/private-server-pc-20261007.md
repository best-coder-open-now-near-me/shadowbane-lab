# Handoff: dedicated PC and private remote access

## User request and scope

Set up the user's other, non-work PC as the private Shadowbane server host, with
Tailscale access for the user away from home and a trusted friend. The user has
explicitly authorized this setup and requested this handoff for the chat already
running on that PC. Inspect that PC's actual OS, available disk, virtualization,
Docker and existing VPN before choosing installation steps. Do not assume the
source PC's Windows paths exist there or reinstall an OS without authorization.

The destination has 16 GB usable RAM and reportedly runs stably despite failed
memory channels. Current source-host server-container use measured about 2 GB;
that is a small-test snapshot, not a player-capacity guarantee. Set sensible JVM
and container limits after inspecting the host; current bootstrap has neither
explicit heap limits nor a Compose memory cap. Verify stability under load.

Use private VPN access, not public router port forwarding or Tailscale Funnel.
No network access has been opened and Tailscale has not been installed by this
source chat. The user may need to complete interactive sign-in on the new PC.

## Exact source checkpoints

Fetch remotes and inspect current PR state before integration. These were the
verified published tips when the handoff was written on October 7, 2026:

| Repository / purpose | Branch and exact commit | Integration |
| --- | --- | --- |
| [shadowbane-lab](https://github.com/best-coder-open-now-near-me/shadowbane-lab), bootstrap deployment | `codex/magicbane-runtime-pairing` / `30e66d57133479e399bedf443185dd52f0e3c427` | [Runtime pairing PR](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/97), open, targets main |
| [shadowbane-server](https://github.com/best-coder-open-now-near-me/shadowbane-server), credential-safe source | `codex/server-credential-logging` / `65952a25afe3fc86cb4cf23a5ff375d1b2f854b5` | [Remove credentials from logs](https://github.com/best-coder-open-now-near-me/shadowbane-server/pull/2), open draft, targets main |
| Lab model alignment and this handoff | `codex/client-server-models-20261007`; pre-handoff checkpoint `57e23241571b47cfd1193765151db0392a1855e5` | [Model alignment PR](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/98), open, targets main |

Start deployment work from the bootstrap branch in an independent checkout.
Read its `docs/magicbane-bootstrap.md`, `docs/git-branch-map.md` and
`docs/deployment-policy.md`. Use a focused `codex/` task branch; commit and push
validated checkpoints, preserving unrelated work. Main is the integration target.
The server credential branch also includes the ownership-only server PR's docs.

The paired original Java source is
`bafb48fe14e5356a64137954cf2d79205835a204`. The fixed bootstrap image is
`magicbane/magicbox@sha256:20050d2a9a1e59deb83a270f78e5cd2111c5fc0a786651de0f0c1c39c56214a2`.
The paired seed SQL SHA-256 is
`cbc0bb3607d6ba9fafa4b7ad5270ff2086cfb9814012d9671a2087e330a37226`.
Do not replace these with moving upstream master/latest: newer code needs data
and dependencies absent from the paired image. Do not run the image's original
pull/reset entrypoint; the lab supplies a fixed-source replacement.

## What is already working, and what is not installed

The current host runs `shadowbane-local-server-1`, image
`shadowbane-local:bafb48fe`, with login/world TCP ports 6000/8000 published only on
loopback. Database port 3306 and debug port 5000 are not published. The server has
125 base tables, eight views, and 179 loaded heightmaps. Local client login, world
entry and play have been user-tested. Broader gameplay compatibility is unfinished.

Credential-safe source compiled all 821 Java sources into 970 classes using the
paired Corretto 8/JARs. Its configuration-init smoke test preserved dummy secrets
while keeping them out of logs. It removes configuration values and the supplied
username/password pair from startup/registration logging. It is NOT yet installed
in the running image. The bootstrap Dockerfile currently compiles original source,
so merely checking out the fixed server repository will not deploy that fix.
Integrate the exact reviewed fixed source into the image build, validate it, and
verify the built image's source receipt before allowing remote players.

Existing logs may contain real passwords. Keep them private; do not paste or
publish them, include them in a friend package, or silently erase diagnostic data.
No credentials belong in source, handoff messages, command output or PRs.

## Preserve the current world and account data

Named Docker volumes on the source host are `shadowbane-local-database`,
`shadowbane-local-world-data`, and `shadowbane-local-logs`. Real account/character
state already exists. A newly seeded database is NOT a migration of that state.
Prepare the destination independently; coordinate a brief source shutdown and
consistent transfer at cutover. Preserve actual game data, settings and diagnostics.
Do not replace populated data with the image seed or run volume pruning/factory reset.
Generate a destination secret securely and let the startup provision the service
account. Transfer game/account data privately; never post secrets in chat.

Mandatory policy: no retained deployment rollback copies, backup runtimes, old
builds kept for fallback, or rollback-space gates. Rebuild software from committed
source. A necessary migration transfer is user-data transfer, not permission to
accumulate rollback archives. Preserve original user data until the destination
is verified and any retirement is authorized. Do not stop or delete the source
server merely to prepare the destination.

## Private network configuration

1. Install/use Tailscale on the server PC and complete the user's sign-in. Obtain
   its actual VPN IPv4 address; do not invent one or use the old host LAN address.
2. Publish TCP 6000 and 8000 on that VPN interface (and loopback only if useful).
   Keep the local-only default unless remote mode is explicitly configured. Do
   not expose database/debug/admin ports. Avoid conflicting Compose port merges;
   validate the resolved Compose configuration before starting it.
3. Set `SERVER_EXTERNAL_ADDRESS` to the same reachable VPN IPv4. The entrypoint
   maps it to `MB_EXTERNAL_ADDR`, which the login server advertises for world
   connection. Keep the container bind address separate. `SERVER_WORLD_NAME`
   currently defaults to `ShadowbaneLocal`; names with spaces break an upstream
   population-file shell call.
4. Restrict host firewall and Tailscale policy to the intended users/devices and
   those two TCP ports. Sharing the server device plus explicit port policy is
   preferable to giving a friend broad access to the user's network. Audit any
   existing allow-all policy: rules can be additive. Do not enable subnet routes,
   exit-node access, or public Funnel as part of this task.
5. The user and friend run the matching client with its login address set to the
   server's VPN IPv4. Finish a real remote login AND world-entry test, then verify
   an unrelated service/port is inaccessible. Local health checks alone do not
   establish remote reachability or isolation. Router port forwarding is unnecessary.

Official guidance: [device sharing](https://tailscale.com/docs/features/sharing),
[Docker port publishing](https://docs.docker.com/engine/network/port-publishing/).
Consult current platform documentation when implementing policies/install steps.
Do not install software on an employer-managed device without its owner's authority.

## Client and gameplay context

The currently qualified official client is Wonderbane 1.3.38.14. Official executable
SHA-256: `e703e7cf` prefix; use the complete hash from the client baseline receipt,
not this prefix for verification. Manifest SHA-256:
`22e083d1ef09aa94ced7380cc7e2bf994e69b3a3d8450f319c8f19c4dabbb95c`.
CObjects SHA-256:
`08c115baeef5da811f7ee2802ccdc1002cfeba29cf1818956c452e3e594efef6`.
Reconstruct official assets from the verified manifest/source, preserving user
settings. No bot DLL/harness is required for the private server client.

Set `Config/ArcaneIP.cfg` to `SERVER= <actual VPN IPv4>` and `PORT= 6000`, and launch
`sb.exe` directly. The bootstrap enforces the matching client version. Automatic
account registration is enabled; use a distinct game password. Do not copy the
source host's client credentials or settings to a friend's machine.

Model alignment and passive Wonderbane captures continue independently on the
original testing VM. Do not restart that VM or its client. Known open alignment
issues include client/server health calculations and six Shinobi armor templates
present in client assets but missing from the old server SQL. Runtime native
object types are not proven wire types; do not blanket-shift server enum ordinals.
These findings do not justify inventing item stats, loot rates or combat rules.

## Ownership and next actions

The original chat named **Find Wonderbane fix notes** owns bootstrap/runtime/client
qualification. **Continue PvE/PvP bot work** owns model alignment and authored the
credential fix. This destination chat owns the new PC's hosting/VPN setup.
Coordinate source cutover instead of editing another active checkout. The user
can relay this handoff; no destination chat ID has been identified here.

Next: inspect the destination, provision Docker/Tailscale, integrate the credential
fix into the reproducible image, and prepare data migration. Ask only for genuinely
missing access, interactive sign-in or the cutover timing. At delivery report the
actual source/image, network policy, remote connection result, persistence result,
remaining limitations, and clean committed/pushed Git state.
