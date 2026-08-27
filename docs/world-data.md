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

`TerrainAlpha` is deliberately modeled as a neutral raster. Its class and cache names suggest
surface alpha/blend data, while the stitched images are strongly terrain-shaped. It must not be
treated as authoritative height or walkability until correlated with the terrain generator and
live altitude samples.

The archive format is a 16-byte header, a directory of 20-byte resource records, optional
directory padding, and raw or zlib-compressed payloads. Resource IDs are not globally unique.
Terrain raster IDs pack an eight-bit map ID and a decimal tile position: the low 24 bits encode
`tile_x * 1000 + tile_y + 1`. The additional directory group ID is part of the map identity.

## Read-only inspection

The `world_data` package validates archive sizes and bounds, inflates selected resources,
indexes all terrain maps without loading every raster, decodes individual raster tiles, and
parses the nested `WorldDef` placement tree.

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

## Native pathfinding status

`ArcanePref.cfg` contains `PATHFINDING= FALSE`, documented by the binary as toggling
pathfinding for the character. The legacy `/path on` chat command is not registered in this
WonderBane build and returns `Unknown Command`; do not depend on it. A prior attempt to enable
the preference also produced an error during launch. Keep the preference disabled unless that
startup failure is first isolated in a disposable configuration with captured logs; live travel
must not depend on the dormant native pathfinder.

The next correlation boundary is the live `ArcGameZone`: identify its active CZone template and
terrain-map identity, then compare local collision/path results with player LT/LG/altitude and
server movement-correction events. The harness can then plan from decoded geometry while treating
server movement corrections as authoritative feedback.

Format cross-check: [ShadowbaneCacheExporter](https://github.com/blinkdog/ShadowbaneCacheExporter)
documents the archive directory, zlib payloads, terrain raster header, and mesh layout. The local
reader keeps its own implementation and calls undecoded fields by neutral names.
