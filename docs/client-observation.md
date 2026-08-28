# Client observation

The client-observation adapter reads structured state from a build-guarded WonderBane client.
It never sends keyboard or mouse input. Typed observations feed the overlay, differential trace,
and policy adapter from the same native sources. The calibrated color reader remains an
independent selected-health cross-check.

WonderBane exposes its structured state through the original Arcane HUD layer, native object
model, message logging, client configuration, and world protocol/cache data.

## Native player vitals

The build-guarded player reader follows the local-player pointer at image-relative
`0x16A2D98`. The verified player object stores health current/maximum at offsets
`0x5CC`/`0x5D0`, mana maximum/current at `0xCD0`/`0xCD4`, and stamina maximum/current at
`0xCD8`/`0xCDC`. A live cross-check returned native values `1075.375/1075.375`,
`53.75/53.75`, and `324/324`; the HUD rounded those to `1075/1075`, `53/53`, and `324/324`
respectively.

Read all three resources without focusing or capturing the game:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-player --json
```

The reader verifies the same executable hash and 32-bit address bounds as selected-target
health, requires a non-null aligned player pointer, performs stable pointer-before/value/
pointer-after reads, and validates every current/maximum pair. The bounded PvE controller
requires this observation and stops before further input when health reaches 50 percent.

## Native player position

The local-player position reader follows the player pointer through the canonical position
component used by the object's virtual position getter: player `+0x4B0`, component `+0`, then
the native `x/y/z` vector at `+0x20`. It maps that vector to `LT=x`, `LG=-z`, and
`altitude=y`.

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-position --json
```

The reader verifies the executable hash, the player object's vtable range, and the exact
getter implementation before following the component chain. It checks every pointer, samples
the vector twice, rejects incoherent movement and out-of-world coordinates, then rereads the
entire pointer chain so travel never acts on a mixed snapshot. This direct object-model path
replaces the older render-copy calibration and remains valid when the HUD or render state
changes.

## Native current zone

The local player stores the current `ArcGameZone` pointer at offset `0xD40`. This is the zone
object already consumed by the HUD banner. Its name is a native UTF-16 `Core::String` at zone
offset `0x1BC`; when that field is empty, the client follows the parent-zone pointer at `0xEC`
until it finds the inherited name. The inherited `ArcCacheObj` resource ID at `0x10` and group
ID at `0x14` identify the exact `CZone.cache` template, while `0x78`/`0x7C` contains the
server-issued object type and UUID for that placed zone instance. The runtime placement block
at `0x8C` through `0xF4` supplies validated local bounds, rotation, absolute and parent-local
centers, and radii. Native `x/z` becomes world `LT/-LG`, so the terrain raster can be addressed
directly from the same coordinates used by movement and target tracking.

Read the client-resolved identity without focusing or capturing the game:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-zone --json
```

Join every entry in the active parent chain to its complete terrain-raster maps by supplying the
client cache directory:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-zone `
  --cache-directory 'C:\path\to\Wonderbane\cache' `
  --json
```

The reader applies the executable hash and pointer guards used by the other native observers,
validates the `Core::String` begin/end/capacity pointers, decodes its exact UTF-16 length, checks
the terminator, rejects parent cycles and excessive depth, and retries if the player or current
zone changes during a sample. It emits the resolved name, an opaque zone token, and the parent
depth that supplied the name. It also emits each zone's exact template key and server-instance
key. Runtime-only zones may expose template ID zero; the reader preserves that exact key and
marks it non-cache-resolvable instead of inventing a cache identity. The optional cache join
skips only those runtime-only entries and accepts other terrain references only when the `CZone`
payload contains every tile in the referenced `TerrainAlpha` map; missing, partial, or duplicate
maps fail closed.
The emitted map order is meaningful: layer zero is the height field and later layers are reported
as material alpha. The runtime bounds, quaternion, absolute center, and parent-local center are
preserved so nonzero-centered and rotated zones project into the correct global LT/LG cells.

## Native group roster and follow state

`ArcWindowGame` owns an `ArcGroupManager` pointer at offset `0x98`. The manager retains the
group-member list populated by `ArcUpdateGroupMessage`: member object identifiers, names,
health/stamina/mana percentages, native `x/y/z`, role, and per-member follow state. The manager
also retains the local follow and split-gold flags. Native coordinates map to `LT=x`, `LG=-z`,
and `altitude=y`, matching the local-player position reader.

Read the current roster and leader position without focusing or capturing the game:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-group --json
```

The reader follows `ArcWindowGame -> ArcGroupManager -> std::list<ArcGrouperEntry*>` using the
verified client layout. It checks the executable hash, every pointer and list link, group-size
limit, UTF-16 name bounds, role and boolean fields, resource ranges, and finite coordinate
bounds. It rereads the list head, links, entry pointers, member state, strings, and manager
toggles so a concurrent group update cannot produce a mixed snapshot. The output identifies
the leader when the client roster marks one, making that member's exact coordinates available
to travel policy without requiring a selected target.

## Native progression core

The same stable local-player object exposes exact level, unspent ability and training points,
left/right attack rating, and defense. The bundled profile records the live level-59 calibration
at offsets `0xCC0`, `0xCAC`, `0xC20`, `0xCFC`/`0xD00`, and `0xD04` respectively. Read them
without focusing or capturing the game:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-progression --json
```

The reader is read-only and build-guarded: it checks the executable hash, pointer slot and player
pointer bounds, requires a stable pointer around bounded 64-byte reads, and rejects impossible
levels, point balances, ratings, and defense. This is the durable progression-observation core;
attribute caps remain a separate semantic source rather than a guessed memory field.

## Native skills and powers

The local-player object's skill vector begins at `0xC24` and its power vector at `0x670`.
Both are standard 32-bit start/end/capacity vectors with 16-byte records: unsigned token,
trained ranks, effective rank, and maximum effective rank. Read the complete vectors with:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-training --json
```

The reader applies the executable hash and pointer guards used by the scalar observer, validates
vector pointer order, alignment, capacity, counts, duplicate tokens, and rank bounds, and reads
in backend-safe 64-byte chunks. It rereads both metadata triples and the player pointer after the
payload; any concurrent mutation retries the entire snapshot. Unknown tokens remain lossless as
`power_0x...` entries instead of receiving guessed semantic names.

Live validation returned 9 skills and 43 powers. The bundled catalog resolves all nine skills and
30 powers, including every proc-Assassin roadmap power. Compose both native sources and compare
the live effective ranks with sourced build targets using:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client advise-irekei-proc --json
```

The audit reports power-rank increments separately from displayed skill-rank gaps because the
latter must not be confused with training-point costs.

## Native selected-target health

The preferred health source reads the same selected-object values that feed Arcane datafields
`8007` and `8009`. Live calibration against the current WonderBane build established:

- selected-object pointer: image-relative `0x16A2DA4`;
- current health: selected object offset `0x5CC`; and
- maximum health: selected object offset `0x5D0`.

During validation, a Frost Walker's current value regenerated continuously from `8.55689` to
`10.0` while maximum health remained exactly `10.0`; the selected pointer cleared on death. The
bundled native profiles target WonderBane 1.0.5 and are locked to SHA-256
`ef43784ba6ffa0de6c0c16c76569f864393ad1530e7149395bb560e5cca30f13`.
WonderBane can retain signed overkill on a selected corpse (live Turtle evidence observed about
`-82.8/10` after a 92-point killing hit), so finite non-positive current health is normalized to
zero while the maximum-health and target-identity guards remain in force.
The 1.0.5 migration was revalidated against a live selected Crab before combat input was
enabled; the selected-object pointer and native ArcCharacter role layout remained stable.
Service-role calibration also treats `merchantData` presence as protected because a live Master
Bard carried that marker without enabling the narrower `isTrainer` or `shopkeeper` flags.

Read it without focusing or capturing the game:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-target --json
```

The reader opens `sb.exe` with query and read rights only. It verifies the executable hash,
32-bit pointer size, image-relative pointer slot, user-address range, stable selection pointer,
finite health values, and current/maximum bounds. A changed build, ambiguous process, selection
race, partial read, or implausible value fails closed.

## Native selected-target position

The selected object at image-relative `0x16A2DA4` exposes its world position through virtual
slot `0x58`. For `ArcObj`, `ArcMobile`, `ArcCharacter`, `ArcCombatObj`, structures, items, and
the other verified base implementations, that slot contains the image-relative thunk `0xA3D0`.
The thunk's implementation reads a component pointer at selected-object offset `0x4B0`, follows
its value pointer at offset `0`, and returns the three floats at value offset `0x20`.

Read the selected target's exact position with:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-target-position --json
```

The output maps native coordinates to `LT=x`, `LG=-z`, and `altitude=y`. Its opaque target token
uses the same executable/process/object identity as the native health reader, allowing the two
snapshots to be joined safely. The position reader verifies the executable hash, selected
pointer, read-only image range for the vtable, exact getter thunk, component/value pointers,
coordinate bounds, and a bounded two-sample movement delta, then rereads the complete pointer
chain. A selected object with an unverified position-getter override fails closed.

## Native selected-target identity

The verified client classifies service characters from four sparse `ArcCharacter` boolean
fields: `shopkeeper`, `banker`, `isTrainer`, and `isMinion`. The bundled reader follows the
same selected-object pointer, requires the exact `ArcCharacter` vtable, and resolves the sparse
keys from the build's registered descriptors rather than inferring a role from a displayed name
or health value.

Inspect the current selection with:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-target-identity --json
```

The result includes whether the object is an `ArcCharacter`, each role flag, the protected-role
set, and `attack_eligible`. A stable non-character selection is reported as explicitly
ineligible without dereferencing sparse data. Missing sparse entries use the client's registered
`false` default. Pointer races, oversized or malformed sparse tables, duplicate keys,
non-boolean values, and build drift fail closed. Its target token is directly joinable with
native health, position, and action snapshots.

## Native loaded-character population

The selected-object pointer is not the only source of live actor data. The guarded population
reader enumerates the current build's private `ArcCharacter` allocations by their exact vtable,
then reads health, position, protected service roles, and each character's action target without
changing game selection. It also reports the player's selected-object token and action-target
token separately; Shadowbane can keep a melee action committed to one character while another
object is selected.

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-population --json
```

The allocation scan is cached for 15 seconds while character fields are refreshed on every
observation. Exact executable identity, private/read-write memory type, `ArcCharacter` vtable,
pointer bounds, health bounds, position chain, world bounds, sparse role descriptors, and
selection stability all fail closed. This is the acquisition source for distance-ranked PvE;
target-cycle input is retained only to place the chosen object into the client's selected slot.

## Pixel cross-check

The checked-in `wonderbane-1920x955` profile is based on three captures from the text-fixed
client at 1920 by 955 pixels and Windows DPI scale 1.0:

- no target: zero qualifying red pixels in the target-health strip;
- selected Frost Walker at full health: 122 of 122 left-anchored columns; and
- damaged Frost Walker: 78 of 122 left-anchored columns, or about 63.9 percent.

The calibrated strip is client-relative `left=340`, `top=3`, `width=122`, `height=10`.
A column counts as filled only when at least three pixels meet the red-channel threshold. The
detector fails closed if the frame size changes or the fill is no longer left-anchored beyond
the configured stray-column tolerance.

## Live read-only check

Keep WonderBane focused, then run:

```powershell
cd "$env:USERPROFILE\shadowbane-lab"
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-target `
    --client-profile .\configs\wonderbane.local.json `
    --observation-profile .\configs\wonderbane-1920x955.observation.json `
    --wait-seconds 10 `
    --json
```

Switch to WonderBane during the wait. The command validates the executable, title, foreground
state, client dimensions, DPI, paired profile identifiers, screenshot dimensions, red threshold,
and fill continuity before returning target presence and health. `live_input_enabled` can and
should remain `false`.

## Native combat stream

`NativeMessageHudReader` reads the client-owned UTF-16 message stream directly. On attachment it
guards the exact executable hash, scans only the calibrated private/read-write address range,
resolves one structurally valid `{begin, end, capacity}` string owner, and suppresses existing HUD
history. Normal polls reread that small owner and its bounded payload, verify stable metadata
before and after the read, retain an incomplete final message, and emit only records appended
after the previous snapshot. Rolling HUD history is reconciled through exact record overlap;
ambiguous owners, torn reads, unrelated replacement, and build drift fail closed.

The verified `MessageHUD2` stream contains both native Combat and Powers channel markers. It
provides exact damage, miss, kill, experience, cast, and effect text without requiring the HUD's
per-session file-logging switch. Bounded PvE uses this source by default when `--combat-log` is
omitted:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client run-pve `
    --client-profile .\configs\wonderbane-pve.local.json `
    --combat-source hud `
    --live
```

Shadowbane's built-in text-HUD logger remains a supported offline and compatibility source. Open
the properties control on the combat message HUD, choose `Log`, enable `Log Messages`, and provide
a filename. The client appends `.txt` and writes the stream under its `Logs` directory, for
example:

```text
Logs\shadowbane-combat.log.txt
```

The live file contains complete timestamped records even when the in-game pane wraps them across
several rendered lines. For example:

```text
(4:52:46) The Frost Walker misses YOU!
```

Read a snapshot without focusing or capturing the client:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client read-combat-log `
    .\Logs\shadowbane-combat.log.txt `
    --json
```

Use `--combat-source log --combat-log <path>` to select it for a live PvE run.
`NativeCombatLogReader` also supports incremental attachment at the beginning or current end of
the file. It retains incomplete writes until the native blank-record separator arrives, preserves
continuation lines, detects truncation or replacement, and emits a monotonic typed sequence for
the overlay and recorder.

## Arcane HUD datafields

The default skin binds HUD controls directly to semantic datafields. The inspected selection HUD
uses `8006` for the selected name, `8007` for the selected health bar, and `8009` for selected
health text. The status HUD similarly uses `8010`, `8011`, and `8012` for player health, mana, and
stamina. These bindings identify the upstream state seam for the structured health bridge.

## Overlay boundary

The overlay consumes semantic observations rather than screenshots. Combat and power messages
come from the native message HUD, and exact selected health comes from the build-guarded native
reader. The calibrated geometry/color reader remains an independent cross-check, not the primary
source. Both native producers feed the same typed stream so overlay presentation cannot diverge
from differential recording or PvE-control feedback.
