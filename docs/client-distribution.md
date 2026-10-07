# Independent client distribution based on Wonderbane

Decision recorded October 7, 2026: use the reviewed Wonderbane x86 client as the
starting point for our own server's client distribution. Adopt upstream fixes
selectively, on our release schedule. Players should have a dedicated install
for our server, with a single update path. A separate installation for another
server is an active product install, not a deployment rollback copy.

This is a binary-and-assets distribution decision. We have the Magicbane Java
server source and our extension/tooling source, not the proprietary client engine
source. The x64 Steam client is outside this baseline. Keeping our server in
Wonderbane's listing is not a release requirement and has not been established
as technically or operationally available.

## Baseline selected

Profile `wonderbane-1.3.38.14-objects-20261007-v1` records the October 4 executable
and October 7 objects-cache update already documented in
[the client update evidence](client-update-20261004.md). It pins an evidenced
starting point; it does not track whatever upstream currently calls latest.

| Marker | Bytes | SHA-256 |
| --- | ---: | --- |
| Official `sb.exe` | 21,143,613 | `e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e` |
| Prepared `sb.exe` | 21,143,613 | `78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903` |
| `cache/CObjects.cache` | 5,433,065 | `08c115baeef5da811f7ee2802ccdc1002cfeba29cf1818956c452e3e594efef6` |

The source manifest receipt is
`22e083d1ef09aa94ced7380cc7e2bf994e69b3a3d8450f319c8f19c4dabbb95c`.
The prepared executable includes our reviewed extension bootstrap. Identifying
that executable does not verify that its DLL is present, qualified, or running.
The official variant is the initial candidate for own-server login; a prepared
variant is only needed if we choose qualified client-side fixes for that release.
Existing bot DLLs are not an own-server prerequisite.

The older local `Downloads/WonderbaneClient/Wonderbane` copy is **not this
baseline**. Its observed executable starts `57cac833` and objects cache starts
`d30f4e55`. Do not silently promote it based on its folder name.

## Read-only identification

From an environment containing this source:

```powershell
python -m shadowbane_lab.cli client inspect-distribution "C:\Games\OurShadowbane" --variant official --json
```

Use `--variant prepared` explicitly for the bootstrap-patched executable.
The command hashes only the two markers above, compares sizes and digests, rejects
missing files and path indirection below the client root, and rechecks file
identity after hashing. It does not write to the client or contact a server.

Exit 0 means `markers_match: true`; exit 2 means mismatch or inspection failure.
JSON report schema 1 includes the exact profile, variant, expected and observed
markers, individual statuses, and a `not_evaluated` list. Size mismatches avoid
reading arbitrarily large files. Observable file changes invalidate the result.
This is an offline observation, not an atomic snapshot of an active patcher.

**A marker match is not a qualified release.** It does not verify the other
client files, installed extension/host, live capabilities, game rules, or server
compatibility. Full release admission must retain the existing package integrity
and fresh launch checks and add the selected server/data pairing. Never use this
command's exit status to grant gameplay actions or to skip those checks.

## Durable ownership and API boundaries

| Boundary | Existing implementation / decision |
| --- | --- |
| Policy and simulation API | Keep `protocol` version 1 and [ADR 0001](adr/0001-unified-semantic-protocol.md): Observation -> Affordances -> Decision -> Events. The server migration lane owns the authoritative adapter. |
| Server game authority | Magicbane owns character legality, identities, combat, cooldowns, buffs, inventory and persistence. Emit actual server outcomes through the semantic adapter. |
| Client implementation | Executable offsets, native hooks, rendering fixes and wire details stay inside client adapters. They are not the public game API. |
| Existing native contracts | Extension status ABI 1, combat wire 2, actor wire 3 and their ownership/fence contracts are separate versions. An initialized DLL is not proof that an action capability is available. Preserve these only where retained client functions need them. |
| Exact client content | The new distribution markers identify this baseline. Existing `client_observation/build_compatibility.py` only establishes reviewed native-layout equivalence; it cannot qualify a data or server pairing. |
| Release qualification | Reuse extension package/manifest verification and deployment receipts where applicable. Bind a release to exact client asset inventory, source commit, component hashes, server revision, database/data revision and ruleset. The own-server release is not yet qualified. |

Do not introduce a second gameplay API over memory/IPC for systems the server
already owns. A launcher/update/account-management API may be useful, but it must
not become another implementation of combat. Stabilize semantic meaning and
causal results; keep transport and native ABI versioning separate. Reject
unsupported versions or absent capabilities explicitly. Never reinterpret a
local queue acknowledgment as a server-applied effect.

This checkpoint adds baseline identification and records the boundary. It does
not claim that every existing Python module is a stable public SDK or that the
server adapter has been implemented. The coordinated **Continue PvE/PvP bot work**
chat owns mapping policies, simulator knowledge and combat/buff findings to that
server adapter. Further client-circumvention harness development is on hold.

## Adopting fixes and issuing our releases

1. Record the candidate upstream manifest and exact changed files. Classify each
   change as executable/runtime, assets/data, server behavior, or launcher/UI.
   A changelog claim alone does not tell us where its implementation lives.
2. Compare with our pinned baseline and decide whether we want its behavior.
   Keep bug repairs separate from custom balance, races, classes and progression.
   No Saetor/Ninja removal or cache-ID remapping is approved by this decision.
3. Qualify changed executable adapters against exact images; qualify data changes
   against the chosen server database, tokens and character-creation rules.
   A compatible native layout is insufficient for either game-data semantics or
   login/world compatibility.
4. Validate the paired release through login, world listing, creation, reconnect,
   movement, combat, death/respawn and persistence. Record failures and unknowns;
   do not promote from an apparently smooth rendering session alone.
5. Publish one versioned manifest/update route for our distribution. Keep player
   settings and saves in place. An upstream patcher must not independently update
   that install. Reconstruct reproducible assets from committed source and the
   official upstream source; follow the [no-retained-rollbacks policy](deployment-policy.md).

The saved Discord-derived document **WonderBane PvP Simulation Knowledge — Current
Canonical State** still exists in the original September 1 chat attachment. It is
a filtered current-state summary: it explicitly excludes infrastructure, server
administration, cities/mines/zones, NPC placement, loot/vendors, patcher/UI fixes,
PvE-only changes, duplicates and superseded values. It is not the requested full
historical fix chronology. Treat entries such as starting-rune double charging,
stat-cap stacking, prerequisite accounting, passive-defense rounding and snare
sign corrections as regression candidates to verify against our server source.
Custom stat boons, progression, Saetor and Ninja behavior are ruleset decisions,
not automatically required fixes. Do not invent missing hit-curve coefficients.

## Server bootstrap handoff and next work

The existing local `magicbane-server-source` research checkout and its sibling
`magicbane-server` are clean `master` at
`3649c629b709c67625a09150a3752107f4b873cc`. These are research references, not a
selected current production base. A successful October 7 fetch refreshed master;
its fetch configuration only tracks that branch. An explicit upstream heads check
also found:

- `magicbox-1.5.2.1`: `9866632ad5aa083165170202d508a95e2bc556ba`.
- `subdate2`: `ab96cfcda4e983dd7fc1fc205205810f11ddd3de`.

Compare build/runtime requirements and data compatibility before selecting the
server base. On that master reference, `ClientMessagePump.java` dispatches
`PerformActionMsg` to `PowersManager.usePower` and `AttackCmdMsg` to
`CombatManager.setAttackTarget`. These are source investigation entry points,
not a proposed API or proof that another branch has identical dispatch.

Docker Desktop bootstrap remains blocked by the reported `dockerInference`
AF_UNIX listener/removal error. No server image was pulled, no container was
created, and no client endpoint was changed in this work.

- Complete: select and identify the evidenced Wonderbane baseline; document update
  ownership and API boundaries; coordinate server responsibilities.
- Active next: resolve the Docker startup failure and select a reproducible server
  source/runtime/data combination for initial login testing.
- Remaining: qualify the client/server pairing, recover a broader fix chronology,
  and classify/verify its repairs. The separate migration lane owns the server API.
