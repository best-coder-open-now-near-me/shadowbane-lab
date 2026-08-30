# WonderBane texture tools

Deterministic, offline helpers for conservative Shadowbane/WonderBane texture experiments.
They operate on extracted image files only. They **do not** open, modify, repack, or deploy
Shadowbane `.cache` archives.

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
alpha preservation, black-key preservation, and sculptor output modes/sizes.

## First live-test rule

Before processing an extracted game texture, record its resource ID, dimensions, image mode,
transparency behavior, and SHA-256. Keep the original asset and rebuilt cache available for
immediate rollback. Change one resource only in a staging client.
