# WonderBane client-input harness

The client adapter consumes the same `DecisionMessage` as the simulator. Coordinates,
keybinds, target acquisition, and camera mechanics remain deployment details; policy code
never emits a `pyautogui` call.

The public WonderBane client values have not been guessed. Start from
`configs/wonderbane.template.json`, keep `live_input_enabled` set to `false`, and replace
every placeholder from the locally installed, approved client.

## Safety boundary

Every click, drag, key press, and hotkey is serialized and immediately preceded by checks
for all of the following:

- the independent emergency stop is not set;
- the expected executable owns the foreground window;
- the foreground title matches the calibrated regular expression;
- the window is visible;
- client width, height, and DPI remain within the calibrated tolerance;
- the minimum input interval has elapsed.

PyAutoGUI's corner fail-safe is enabled. The live backend is also rejected unless the loaded
profile has `live_input_enabled: true`. Automated tests use only the recording backend or an
in-memory fake PyAutoGUI module, so tests cannot generate desktop input.

## Capture the local window identity

Put the running WonderBane client in the exact mode used for automation—windowed or
borderless, resolution fixed—bring it to the foreground, and inspect it without sending
input:

```powershell
$env:PYTHONPATH = "src"
@'
from shadowbane_lab.client_input import WindowsForegroundWindowInspector

print(WindowsForegroundWindowInspector().inspect())
'@ | .\.venv\Scripts\python.exe -
```

Copy `executable_name`, the stable portion of `title`, `client_bounds.width`,
`client_bounds.height`, and `dpi_scale` into a local copy of the template. Keep tolerances
tight enough that a resized or DPI-shifted window fails closed.

## Calibrate points and bindings

Absolute screen points are stored as normalized client coordinates. For a client rectangle
`(left, top, width, height)`, the conversion is:

```text
x_normalized = (x_screen - left) / (width - 1)
y_normalized = (y_screen - top)  / (height - 1)
```

`WindowBounds.normalize()` and `WindowBounds.resolve()` implement the round trip. Record:

- the actual key or hotbar click for every semantic action key;
- whether an entity target must be clicked before or after activation;
- a safe movement center and horizontal/vertical click radius;
- a safe camera anchor, maximum drag deltas, button, and duration.

Entity clicks are resolved from the current observation by a `BindingPointResolver`; they
are not fixed in the profile. Camera drags are acquisition operations owned by the adapter,
not alternate policy actions.

## Dry-run the complete route

Use the real foreground-window inspector with `RecordingInputBackend`. This exercises the
semantic compiler, target resolver, focus guard, coordinate resolution, waits, and rate
limits, while only recording `ClickInvocation`, `DragInvocation`, `KeyPressInvocation`, or
`HotkeyInvocation` objects.

```python
from shadowbane_lab.client_input import (
    ClientInputAdapter,
    DecisionInputCompiler,
    EventEmergencyStop,
    ForegroundWindowGuard,
    GuardedInputExecutor,
    RecordingInputBackend,
    StaticBindingPointResolver,
    WindowsForegroundWindowInspector,
    load_calibration,
)

profile = load_calibration("configs/wonderbane.local.json")
backend = RecordingInputBackend()
compiler = DecisionInputCompiler(profile, StaticBindingPointResolver())
executor = GuardedInputExecutor(
    guard=ForegroundWindowGuard(profile, WindowsForegroundWindowInspector()),
    backend=backend,
    stop_signal=EventEmergencyStop(),
)
adapter = ClientInputAdapter(compiler, executor)
```

Supply observed entity points to the resolver before testing targeted decisions. Review
`backend.invocations` and `adapter.audits`. A rejected dispatch includes its fail-closed
reason, and a partially interrupted plan records the number of commands completed.

## Enable an approved live session

Only after the dry-run invocations match the client should the local profile be changed to
`live_input_enabled: true`. Do not commit the local profile if it contains machine-specific
details. Replace the recording backend with `PyAutoGuiBackend` and use the independent
Ctrl+Shift+F12 stop listener:

```python
from shadowbane_lab.client_input import PyAutoGuiBackend, WindowsHotkeyEmergencyStop

with WindowsHotkeyEmergencyStop() as emergency_stop:
    executor = GuardedInputExecutor(
        guard=ForegroundWindowGuard(profile, WindowsForegroundWindowInspector()),
        backend=PyAutoGuiBackend(),
        stop_signal=emergency_stop,
    )
    adapter = ClientInputAdapter(compiler, executor)
    # The behavior loop dispatches the same validated DecisionMessage used by the simulator.
```

Moving the pointer to a PyAutoGUI fail-safe corner or pressing Ctrl+Shift+F12 stops further
commands. Once the emergency stop trips, construct a new reviewed session rather than
resetting it in place.
