# Client observation

The client-observation adapter reads calibrated pixels from an already-guarded foreground
WonderBane client. It never sends keyboard or mouse input. Recognition output is typed and
renderer-independent so the same stream can feed an overlay, a differential trace, or a policy
adapter.

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

## Overlay and combat stream boundary

The overlay should consume semantic observations rather than screenshots. Target health is a
geometry/color observation. Combat events should first be sourced from a stable client log if
WonderBane writes one; OCR of the fixed combat pane is the fallback. Either producer must emit a
deduplicated event stream before overlay rendering so the recorder and overlay see identical
events.
