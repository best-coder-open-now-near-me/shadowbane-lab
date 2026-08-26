# Client observation

The client-observation adapter reads calibrated pixels from an already-guarded foreground
WonderBane client. It never sends keyboard or mouse input. Recognition output is typed and
renderer-independent so the same stream can feed an overlay, a differential trace, or a policy
adapter.

WonderBane also exposes structured state through the original Arcane HUD layer. Native message
logging and numeric HUD datafields are preferred over interpreting rendered text.

## Native player vitals

The build-guarded player reader follows the local-player pointer at image-relative
`0x16A2D98`. The verified player object stores health at offsets `0x5CC`/`0x5D0`, mana at
`0xCD0`/`0xCD4`, and stamina at `0xCD8`/`0xCDC`. A live cross-check returned native values
`1075.375/1075.375`, `53.75/53.75`, and `324/324`; the HUD rounded those to `1075/1075`,
`53/53`, and `324/324` respectively.

Read all three resources without focusing or capturing the game:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-player --json
```

The reader verifies the same executable hash and 32-bit address bounds as selected-target
health, requires a non-null aligned player pointer, performs stable pointer-before/value/
pointer-after reads, and validates every current/maximum pair. The bounded PvE controller
requires this observation and stops before further input when health reaches 50 percent.

## Native selected-target health

The preferred health source reads the same selected-object values that feed Arcane datafields
`8007` and `8009`. Live calibration against the current WonderBane build established:

- selected-object pointer: image-relative `0x16A2DA4`;
- current health: selected object offset `0x5CC`; and
- maximum health: selected object offset `0x5D0`.

During validation, a Frost Walker's current value regenerated continuously from `8.55689` to
`10.0` while maximum health remained exactly `10.0`; the selected pointer cleared on death. The
bundled native profile is locked to SHA-256
`0889b39a6f065f2ddf696bad01455e0b691892077105fe27e35de94bfdf59ebc`.

Read it without focusing or capturing the game:

```powershell
.\.venv\Scripts\python.exe -m shadowbane_lab.cli client observe-native-target --json
```

The reader opens `sb.exe` with query and read rights only. It verifies the executable hash,
32-bit pointer size, image-relative pointer slot, user-address range, stable selection pointer,
finite health values, and current/maximum bounds. A changed build, ambiguous process, selection
race, partial read, or implausible value fails closed.

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

Shadowbane text HUDs have a built-in lossless logger. Open the properties control on the combat
message HUD, choose `Log`, enable `Log Messages`, and provide a filename. The client appends
`.txt` and writes the stream under its `Logs` directory. The validated VM configuration writes:

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

`NativeCombatLogReader` also supports incremental attachment at the beginning or current end of
the file. It retains incomplete writes until the native blank-record separator arrives, preserves
continuation lines, detects truncation or replacement, and emits a monotonic typed sequence for
the overlay and recorder.

## Arcane HUD datafields

The default skin binds HUD controls directly to semantic datafields. The inspected selection HUD
uses `8006` for the selected name, `8007` for the selected health bar, and `8009` for selected
health text. The status HUD similarly uses `8010`, `8011`, and `8012` for player health, mana, and
stamina. These bindings identify the upstream state seam for the structured health bridge; they
are not OCR targets.

## Overlay boundary

The overlay consumes semantic observations rather than screenshots. Combat and power messages
come from the native HUD log, and exact selected health comes from the build-guarded native
reader. The calibrated geometry/color reader remains an independent cross-check, not the primary
source. Both native producers feed the same typed stream so overlay presentation cannot diverge
from differential recording or PvE-control feedback.
