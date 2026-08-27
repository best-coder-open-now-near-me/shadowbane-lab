# Client world data

Shadowbane does not delegate all geometry to the server. The WonderBane client contains a
local terrain generator, mesh resources, a spatial cell tree, collision objects, waypoint
tracking, and a character pathfinder. It also contains `MoveCorrection`,
`MoveRequestCorrection`, and `ForceMove` messages, which establish the complementary server
authority boundary: the client predicts and collides locally while the server can correct an
invalid or divergent result.

## Shipped inputs

The inspected client has a 2.38 GB resource set. The navigation-relevant portion is:

- `Config/WorldDef.cfg`: nested world and zone placements, including zone template IDs,
  centers, rotations, altitude offsets, radii, and optional zone-load filenames;
- `cache/CZone.cache`: compiled zone templates and terrain-generator configuration;
- `cache/CObjects.cache`: compiled static-object definitions and collision metadata;
- `cache/Mesh.cache`: polygon meshes used by terrain and placed objects;
- `cache/TerrainAlpha.cache`: 20,912 spatial 128-by-128 byte rasters;
- `cache/Tile.cache`: nine large tile resources; and
- `cache/Render.cache`: render-resource records associated with object templates.

`CZone` references each terrain tile's rasters in semantic layer order. The first complete map is
the zone height field; the remaining maps are material-alpha layers. This agrees with the
open-source emulator's [HeightMap implementation](https://repo.magicbane.com/MagicBane/Server/src/commit/a7bc1d5a6afad4ebc7b953e8277a9380f7846e11/src/engine/InterestManagement/HeightMap.java),
including bottom-left origin, `(width - 1)` interpolation buckets, and byte-height scaling.
Material layers remain neutral until their surface meanings are decoded. Height alone is not an
authoritative walkability flag, so water is classified only when the same `CZone` explicitly
declares a water plane and a zone-local sea level. Object-population layers are independently
joined through `CObjects`, `Render`, and `Mesh`, preserving the distinction between terrain
material and collision-bearing geometry.

The archive format is a 16-byte header, a directory of 20-byte resource records, optional
directory padding, and raw or zlib-compressed payloads. Resource IDs are not globally unique.
Terrain raster IDs pack an eight-bit map ID and a decimal tile position: the low 24 bits encode
`tile_x * 1000 + tile_y + 1`. The additional directory group ID is part of the map identity.

## Read-only inspection

The `world_data` package validates archive sizes and bounds, inflates selected resources,
indexes all terrain maps without loading every raster, decodes individual raster tiles, and
parses the nested `WorldDef` placement tree. The parser preserves client-shipped placement
display names even though they are encoded as `ZONE_#NAME` comments.

Run it directly against a client installation:

```powershell
python -m shadowbane_lab.cli client inspect-world-data `
  'C:\path\to\Wonderbane\cache' `
  --world-def 'C:\path\to\Wonderbane\Config\WorldDef.cfg' `
  --json
```

The verified WonderBane resource set contains 105 complete terrain maps with shapes from 1x1
through 16x16 tiles. Its stock `WorldDef` identifies Aerynth world 1 with 70 nested placements,
49 zone template IDs, and 26 named zone-load configurations.

The active-zone loader uses the client-resolved `CZone` key and native placement geometry to
project the first referenced map into a bounded local window of global LT/LG cells. Large
within-cell height changes become hard A* exclusions and smaller changes become traversal costs.
A bounds-checked `CZone` prefix parser also resolves explicit water presence, sea-level coordinate
space, and image-terrain minimum/maximum height. When the sea level is zone-local, the loader maps
it into the same byte-height scale and assigns underwater cells a high but traversable cost. For
example, Tainted Swamp template `0:3033` declares water at local height `152` over image terrain
`0..200`, yielding a raw sample threshold of `194.56`; this is cache data, not a darkness
heuristic. Parent/world-relative water remains neutral until its vertical transform is proven.
The same template parser resolves object populations and their density-layer indices. The loader
follows each object resource's render graph, accepts only explicit collision-bearing mesh nodes,
derives a conservative horizontal mesh radius, and uses the associated population raster as a
soft A* density cost. For Tainted Swamp, this resolves four colliding families on population
layer 1 with a declared capacity of 70 and a maximum mesh radius of about 13.4 units. Population
rasters are distributions rather than exact instance placements, so runtime stalls continue to
learn precise obstacle cells.

## Native pathfinding status

`ArcanePref.cfg` contains `PATHFINDING= FALSE`, documented by the binary as toggling
pathfinding for the character. The legacy `/path on` chat command is not registered in this
WonderBane build and returns `Unknown Command`; do not depend on it. A prior attempt to enable
the preference also produced an error during launch. Keep the preference disabled unless that
startup failure is first isolated in a disposable configuration with captured logs; live travel
must not depend on the dormant native pathfinder.

The live `ArcGameZone` is read directly from the local player and supplies the same resolved name
used by the HUD zone banner. Its inherited `ArcCacheObj` key identifies the exact active
`CZone.cache` template. Each template is then joined to the complete `(group ID, map ID)`
identities embedded as `TerrainAlpha` resource keys in its payload. The active parent chain is
retained because a small camp or building zone can inherit its surrounding terrain from an
ancestor. Local collision/path results can now be compared with player LT/LG/altitude and server
movement-correction events while keeping server corrections authoritative.

Format cross-check: [ShadowbaneCacheExporter](https://github.com/blinkdog/ShadowbaneCacheExporter)
documents the archive directory, zlib payloads, terrain raster header, and mesh layout. The local
reader keeps its own implementation and calls undecoded fields by neutral names.
