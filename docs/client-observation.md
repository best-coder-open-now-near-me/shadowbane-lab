# Client observation

The client-observation adapter reads calibrated pixels from an already-guarded foreground
WonderBane client. It never sends keyboard or mouse input. Recognition output is typed and
renderer-independent so the same stream can feed an overlay, a differential trace, or a policy
adapter.

WonderBane also exposes structured state through the original Arcane HUD layer. Native message
logging and numeric HUD datafields are preferred over interpreting rendered text.

## Measured target-health contract

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
come from the native HUD log. Health should move from the current validated geometry/color reader
to the Arcane datafield bridge once that read-only mapping is fully calibrated. Both producers
feed the same typed stream so overlay presentation cannot diverge from differential recording.
