# Read-only WonderBane texture export

The texture patcher already knew how to enumerate and inflate Shadowbane cache resources and how
to validate the 26-byte texture payload header. This tool adds the missing reverse surface: original
cache pixels can now be listed, previewed, and exported to PNG without opening `Textures.cache` for
writing.

## Safety boundary

Every operation uses the existing memory-mapped `CacheArchive` with read-only access. It records the
source file size, SHA-256, and modification time before work, rereads those values after work, and
fails if they changed. The exporter never calls texture-plan apply, install, backup restore, profile
activation, or cache mutation code.

Bulk output belongs in a local artifact directory and must not be committed. Keep the WonderBane
client and patcher closed while taking a stable export.

## Commands

From the repository root, install the client/test dependencies once:

```powershell
py -m pip install -e ".[test]"
```

List all resources that satisfy the currently verified texture contract. Unsupported and nontexture
entries remain in the JSON report with concise skip reasons:

```powershell
py -m shadowbane_lab.client_extension.texture_export list `
  "C:\WonderBane\cache\Textures.cache" `
  --output ".artifacts\texture-export\texture-index.json" `
  --pretty
```

Export one exact resource. A missing group prefix means group `0`:

```powershell
py -m shadowbane_lab.client_extension.texture_export export `
  "C:\WonderBane\cache\Textures.cache" `
  0:5000190 `
  ".artifacts\texture-export\known-originals\0-5000190.png" `
  --metadata ".artifacts\texture-export\known-originals\0-5000190.json" `
  --pretty
```

Export a deterministic anonymous candidate set and contact sheet:

```powershell
py -m shadowbane_lab.client_extension.texture_export samples `
  "C:\WonderBane\cache\Textures.cache" `
  ".artifacts\texture-export\sample" `
  --limit 64 `
  --min-width 128 `
  --min-height 128 `
  --pretty
```

The equivalent repository script is:

```powershell
py scripts\wonderbane-textures\wonderbane_texture_export.py <command> ...
```

## Output contract

Exact exports retain source dimensions and channel mode: depth `1` remains `L`, depth `3` remains
`RGB`, and depth `4` remains `RGBA`. Alpha bytes are not synthesized or discarded. Cache pixels are
stored bottom-up, so PNG export applies the inverse vertical flip used by the existing PNG importer.
The sidecar records this as `cache-bottom-up-to-png-top-down`.

Each sidecar contains the source cache name, size, SHA-256, directory index, group/resource IDs,
compression state, stored and inflated sizes, original payload SHA-256, dimensions, depth, mode,
PNG filename, and PNG SHA-256. It intentionally contains no timestamp or absolute client path, so
repeated exports of the same source are deterministic and portable.

A sample directory also contains:

- `texture-index.json` — complete valid/skip inventory;
- `sample-manifest.json` — selected resources, hashes, and inexpensive ranking metrics;
- `run-receipt.json` — before/after source identity and the immutability assertion;
- `contact-sheet.png` — aspect-correct labeled thumbnails with checkerboards used only for display;
- `textures/` — untouched PNG exports; and
- `metadata/` — one provenance sidecar per PNG.

Candidate ranking uses image size, entropy, variance, edge density, alpha coverage, dimension
variety, and duplicate-thumbnail suppression. These entries are deliberately called *candidates*;
the cache does not provide trustworthy semantic filenames, so the tool does not claim that an
anonymous resource is terrain, bark, foliage, armor, a creature, or a building until reviewed.

## Lossless round trip

The synthetic acceptance test proves:

```text
cache payload -> exported PNG -> existing PNG importer -> identical payload SHA-256
```

The existing importer preserves the original 26-byte header and performs the opposite vertical
flip. This makes an exported original a safe baseline for later programmatic edits and reviewed
texture-patch authoring.

The first useful real-client check is to export known resources `0:5000190` and `0:1706002`, then
compare them with the already tracked restrained-cel replacements. Their presence is not assumed;
missing or ambiguous keys fail rather than selecting a nearby ID.
