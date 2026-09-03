# WonderBane texture tools

Deterministic, offline helpers for conservative Shadowbane/WonderBane texture experiments.
The flare and sculpting tools operate on extracted image files only. Cache access is split between
an explicitly confirmed mutation tool and a separate read-only original-texture exporter.

## Tools

### `wonderbane_texture_flare.py`

Adds broad-form lighting, relief, palette variation, optional grime/moss, and foliage volume
without resizing the canvas or moving UV-compatible regions. The `subtle` preset is intended
for the first in-client repaint experiment.

Safety features include:

- exact input dimensions retained;
- source alpha retained for RGBA output;
- exact black or inferred border color-key output;
- optional same-size grayscale safety mask;
- deterministic output from a fixed seed;
- JSON report with hashes and pixel-change statistics.

Example:

```powershell
py wonderbane_texture_flare.py original_tree.png tree_flared.png `
  --mode bark --preset subtle `
  --preview tree_flared_preview.png `
  --report tree_flared.report.json
```

Black-key foliage:

```powershell
py wonderbane_texture_flare.py leaves.png leaves_flared.png `
  --mode foliage --preset subtle --key black --output-mode black-key
```

For a mixed atlas, pass a grayscale mask matching the texture dimensions exactly:
white pixels may change; black pixels remain byte-for-byte unchanged.

### `wonderbane_texture_sculptor.py`

Reduces high-frequency source art into broader legacy-friendly shapes. It resizes first,
then simplifies palette/detail and produces common foliage representations.

```powershell
py wonderbane_texture_sculptor.py bark.png sculpted `
  --mode bark --sizes 256 128 --strength medium

py wonderbane_texture_sculptor.py leaves.png sculpted `
  --mode foliage --sizes 256 128 --strength medium
```

Foliage output includes:

- `*_rgba.png` — soft alpha;
- `*_black_key.png` — pure-black color key;
- `*_mask.png` — hard monochrome mask.

### `wonderbane_texture_export.py`

Lists and losslessly exports original resources from `Textures.cache` without opening the source
for writing. The exporter reuses the existing read-only `CacheArchive` and verified 26-byte texture
payload parser. It checks the source size, SHA-256, and modification time before and after every
operation.

List valid texture resources and retain skip reasons for nontexture entries:

```powershell
py wonderbane_texture_export.py list C:\WonderBane\cache\Textures.cache `
  --output .artifacts\texture-export\texture-index.json --pretty
```

Export one exact original texture plus its provenance sidecar:

```powershell
py wonderbane_texture_export.py export C:\WonderBane\cache\Textures.cache `
  0:5000190 .artifacts\texture-export\0-5000190.png --pretty
```

Export a deterministic candidate set and labeled contact sheet:

```powershell
py wonderbane_texture_export.py samples C:\WonderBane\cache\Textures.cache `
  .artifacts\texture-export\sample --limit 64 --min-width 128 --min-height 128 --pretty
```

Depths `1`, `3`, and `4` remain `L`, `RGB`, and `RGBA` respectively. Alpha is preserved exactly,
and cache bottom-up pixels are flipped to normal top-down PNG orientation. Bulk output is local-only
and ignored by Git. Anonymous cache entries are called texture candidates until visually reviewed;
the exporter does not invent terrain, foliage, creature, armor, or building labels.

See `docs/texture-cache-export.md` for the complete contract and output layout.

### `wonderbane_texture_cache.py`

Safely installs same-dimension PNG replacements into selected `Textures.cache` resources.
It preserves each resource's original 26-byte texture header and pixel depth, validates the
complete archive layout, and writes a compact rollback archive containing the exact original
directory records and compressed resource bytes. The client must be closed for install or restore.

Always inspect the plan first:

```powershell
py wonderbane_texture_cache.py plan C:\WonderBane\cache\Textures.cache `
  460131=wreck_460131.png 460132=wreck_460132.png
```

Install after closing the client:

```powershell
py wonderbane_texture_cache.py install C:\WonderBane\cache\Textures.cache `
  460131=wreck_460131.png 460132=wreck_460132.png `
  --backup C:\WonderBane\cache\wreck-textures.wbt-backup.zip `
  --confirm-client-closed
```

Restore the exact original resource bytes and archive size:

```powershell
py wonderbane_texture_cache.py restore `
  C:\WonderBane\cache\wreck-textures.wbt-backup.zip `
  --confirm-client-closed
```

## Windows setup

Run `install_dependencies.bat` once. The included drag-and-drop launchers cover the safest
initial bark and foliage workflows. Generated files are written beside the source image or to
a sibling `sculpted` directory; they are not intended for source control.

## Self-test

```powershell
run_self_tests.bat
```

or:

```powershell
py selftest.py
```

The self-test checks deterministic output, dimension preservation, safety-mask isolation,
alpha preservation, black-key preservation, and sculptor output modes/sizes. The repository test
suite separately covers lossless cache export, vertical orientation, source immutability, duplicate
resource rejection, deterministic sampling, and the exported-PNG round trip through the existing
cache importer.

## First live-test rule

Before processing an extracted game texture, record its resource ID, dimensions, image mode,
transparency behavior, and SHA-256. Keep the generated `.wbt-backup.zip` available for immediate
rollback. Change only the intended resources in a staging client.
