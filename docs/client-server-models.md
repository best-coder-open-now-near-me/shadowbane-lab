# Wonderbane client/server model alignment

The first own-server work is now collecting and aligning the model contracts
expected by the chosen client. Gameplay-service implementation follows this
inventory. The server sends resource references, appearance and live object state;
the client resolves those references against its shipped asset catalogs.

## Collected baseline

The passive watcher runs against prepared client 1.3.38.14. The
[compact inventory](../research/client-models/wonderbane-1.3.38.14-20261007.json)
pins the executable, all 13 cache hashes, source revision and public database.
Private live observations remain local. No asset payloads are copied into Git.

| Resource category | Archive | Entries |
| --- | --- | ---: |
| Object definitions | CObjects | 10,690 |
| Geometry | Mesh | 24,387 |
| Render definitions | Render | 33,097 |
| Animation | Motion | 1,503 |
| Skeletons | Skeleton | 105 |
| Textures | Textures | 9,924 |
| Visual effects | Visual | 483 |
| Zone definitions | CZone | 861 |
| Terrain rasters | TerrainAlpha | 20,912 |
| Terrain tiles | Tile | 9 |
| Sound | Sound | 1,086 |
| Other indexed archives | Dungeon / Palette | 0 / 0 |

Every resource key retains **archive + group ID + resource ID**. A runtime entity
ID, a CObject definition, a render node and a mesh are different namespaces.
The existing CObjects prefix parser reads ten numeric type buckets. Its 295 type-17
records produce control characters in the name field; keep those records
unclassified until their layout is decoded. Zero parser exceptions does not mean
all prefixes are semantically correct. Names alone are not a type contract.

## First server-reference comparison

Checked against bootstrap source `bafb48fe14e5356a64137954cf2d79205835a204` and its
paired public SQL `cbc0bb3607d6ba9fafa4b7ad5270ff2086cfb9814012d9671a2087e330a37226`.
These are group-zero resource existence checks, not end-to-end compatibility tests.

| Server reference | Present unique IDs | Missing unique IDs |
| --- | ---: | --- |
| Item base ID -> CObjects | 5,089 | 576, 577, 7000511, 7000512, 7000513 |
| Mob load ID -> CObjects | 2,375 | None |
| Race definition ID -> CObjects | 26 | None |
| Placed building meshUUID -> CObjects candidate | 1,289 | 622010 |
| Positive placed zone LoadNum -> CZone | 611 | None |
| Zone-size loadNum -> CZone | 861 | 15001 |
| Blueprint rank 0 -> CObjects | 168 | None |
| Blueprint rank 1 -> CObjects | 149 | 1699900 |
| Blueprint rank 3 / 7 -> CObjects | 95 each | 1699800, 1699900 |
| Blueprint destroyed -> CObjects | 148 | None |

Repeated references are deduplicated; zero/nonpositive values remain separately
counted in the report. Absence does not establish whether a row is reachable,
placeholder content, uses another resource path, or needs replacement. Do not
silently substitute a similarly named asset. Trace each affected server use and
client resolver first, then make an explicit content/schema correction.

Verified server serialization locations:

- `Mob.serializeForClientMsgOtherPlayer` emits `mobBase.getLoadID()` in the race
  rune path; it is distinct from the mob instance ID.
- `Item._serializeForClientMsg` emits `item.getItemBase().getUUID()` as a definition
  reference.
- `Building._serializeForClientMsg` emits object type/instance ID and `meshUUID`
  separately. The name meshUUID alone does not prove it directly indexes Mesh.cache.
- `Zone.serializeForClientMsg` emits `loadNum` separately from its runtime identity.

## Runtime object-type discrepancy

The pinned server uses `GameObjectType.ordinal()` in messages. Client memory
observations expose a two-word object key; legacy reader field names must not be
mistaken for wire order. Record those fields losslessly before normalization.

| Category | Pinned server ordinal | Observed client key discriminator |
| --- | ---: | ---: |
| NPC | 42 | 42 |
| Player | 52 | 53 |
| Zone | 78 | 79 |

Later upstream source inserts `Petition` between `Nation` and `PlayerCharacter`,
which explains the pattern. Confirm receive/dispatch field mapping before applying
a protocol change. A blanket increment is wrong for earlier types. Audit persistence
as well: `dbPlayerCharacterHandler.ADD_HERALDY` stores the enum ordinal in
`dyn_character_heraldy.characterType`. Preserve existing data during any migration.
This report identifies the mismatch candidate; it does not claim a packet trace or
change a running server.

## Passive watcher

`scripts/watch-wonderbane-models.py` uses existing read-only process readers. It
captures loaded character identity fields, roles, health and location, and the zone
chain. It binds to one process handle and hashes the executable. It does not send
input, invoke gameplay actions, patch memory, attach a debugger, scrape messages,
or equate selection with combat ownership. It does not capture every network message
or prove that every catalog asset is loaded/rendered.

The initial catalog includes directory metadata and CObject prefix candidates only.
The live stream and cache catalog are different evidence sources. Population and
zone reads in a sample are independent observations, not an atomic world snapshot.

```powershell
python scripts/watch-wonderbane-models.py --pid PID --output NEW_DIRECTORY
python scripts/audit-client-server-models.py --catalog CACHE_JSONL --sql PINNED_SQL --output NEW_JSON
```

Schema 2 checks the native character name/server and local key before collection;
`--character umbra --server Wonderbane` pins the requested character. A confirmed
switch stops collection. Transient identity errors omit that sample's population.
The live run was verified as Umbra on Wonderbane with the same key as the initial
watcher. Names are private local metadata, not part of the published catalog.

Before writing, duplicate filtering keeps first sightings, changes in kind/roles,
owner, maximum health or alive/dead state, departures/returns, zone changes and
error/recovery transitions. Position movement and ordinary current-health changes
only update the compact last observation. This is a model-discovery journal, not
a complete movement/damage trace. `entity-summary.json` keeps first/last seen,
sighting/appearance/change counts and latest state; it updates every 15 samples
and on stop. `status.json` exposes suppression and written-record counts. Population
order does not matter, and failed reads do not mark objects as departed. Instance
keys remain distinct from template IDs; duplicate-looking actors are not assumed
to share an asset. The ledger stops at 10,000 distinct entity keys.

Use `--skip-cache` when this same client catalog is already recorded; retain the
original catalog reference beside the new run instead of copying it again.
Defaults: one sample every two seconds, two hours, maximum 64 MiB of live JSONL.
The one-time static catalog is separate (about 18 MB for this client). The output
directory must be new; it is never reused or cleared. Create an empty `STOP` file in
the run directory to end collection. `status.json` reports actual samples, errors,
last success and completion. Closing the game does not attach the watcher to a new
process; later read failures are recorded until stop/expiry. Loading/read errors
must not be interpreted as an empty population. Keep live data private.

The October 7 run is under the testing VM diagnostics share's
`client-models-20261007` directory. It uses a standalone script and the installed
host's read-only library; no runtime replacement or rollback copy was created.

## Current todos and ownership

- [x] Start passive collection and fingerprint/catalog shipped resource namespaces.
- [x] Compare explicit bootstrap SQL references and record missing/ambiguous IDs.
- [ ] **Active:** resolve the object-type wire mapping and affected persisted fields;
  trace missing resource references through their client resolver before changes.
- [ ] Decode unsupported definition layouts and resolve render/mesh/appearance links.
- [ ] Apply reviewed server protocol/content corrections and validate client-visible loads.
- [ ] Resume shared server-side buff/combat behavior against the aligned contracts.

Continue PvE/PvP bot work owns this inventory and alignment. Find Wonderbane fix
notes owns server bootstrap and client connection qualification. The server source
repository is `best-coder-open-now-near-me/shadowbane-server`; this lab owns the
collector, offline audit and evidence summaries. Detailed live records stay local.

## Starter inventory observation

`scripts/watch-wonderbane-inventory.py --pid PID --output NEW_DIRECTORY` waits at
character selection and binds to the first stable Wonderbane character inventory.
It polls every half second for up to two hours, stopping on a confirmed character
change, `STOP`, or an 8 MiB journal limit. It opens the process read-only and never
calls native functions or performs game input. Prepared client 1.3.38.14 is the
reviewed executable for this census.

The two actor-owned container trees and item classes follow
`native/wonderbane_extension/actor_inventory_native.cpp`. Each observation checks
actor identity, tree ownership/order/endpoints, duplicate keys and exact item
classes, then rereads dependencies. It records instance keys, template keys,
container membership and raw quantities for exact ArcItem objects. Derived item
classes retain their identities with unknown quantity. No inventory window is
required. External reads cannot lock objects or prove absence of transient changes.

`inventory.jsonl` distinguishes initial inventory from later first-observed items,
quantity/container changes and items no longer observed. Failed reads preserve the
previous successful snapshot; identical samples and errors are suppressed. Samples
have local sequence numbers and timestamps, not network sequence numbers. If starter
items arrive before the first stable sample, the evidence establishes initial item
presence only, not the grant's ordering, cause or packet contents. The known bot
concentration-potion template is not assumed to be the starter potion's template.
`latest-inventory.json` preserves the latest successful state; `status.json` reports
waiting/recording/unavailable/stopped. These live records remain private.

## Inventory and profession checkpoint

The [October 7 inventory/profession report](../research/client-models/starter-inventory-and-professions-20261007.json)
joins a fixed, hashed prefix of the private live inventory journal to the same
client catalog and pinned SQL. All 31 observed item templates (66 distinct native
instances) have exactly one CObjects group-zero resource and one server item row.
The report exports template aggregates only, omitting character names, native
instance IDs, positions and event timestamps. The optional `--inventory` audit
argument consumes complete JSONL records only, so collection can continue.

The known Greater Concoction Potion is one observed object with raw count 5 then
4; its SQL definition has `numCharges=5`, `useID=429021400`, `useAmount=35`. It
must not be reported as five separate potion objects. Uncharged equipment and
gold can have this raw field zero, so it is not a universal stack-size field.
The server Item serializer explicitly writes `chargesRemaining` separately from
its item-count behavior; exact client field transfer remains to be aligned.

All four base-class IDs, 33 promotion IDs and 315 rune-base IDs in the pinned
server SQL exist in CObjects group zero, with no ambiguous joins. This proves
resource availability, not matching promotion rules, stat formulas or effects.
The running model/inventory watchers do not yet decode the character's learned
profession/rune list; profession transition interpretation requires that evidence
or a separately verified server event. Continue collection through promotion.

The upstream Petition insertion is confirmed at `e2add187`, but no ordinal
migration is justified from native object class numbers alone. The local old
server already loads a client character. Resolve wire tags versus constructed
native class identities before changing the 435 enum-related use sites or stored
heraldry types.
