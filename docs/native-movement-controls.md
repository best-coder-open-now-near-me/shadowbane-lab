# Native movement and camera controls

Source implementation is in progress on `codex/native-movement-controls`, integrated
through `codex/native-lifecycle-hardening`. This document describes the settings
and controls in that source. Native transport and the movement adapter are implemented;
combined manager integration, installed package verification and connected acceptance
remain pending.

## Settings

Select the intended client in **Graphics Lab**, then choose **Movement controls**.
In the game, **Ctrl+Alt+F10** opens the same native panel when text or modal UI does
not own input. These entry points open settings; they do not acquire an automation
host lease. No Python automation worker is needed for manual controls.

Enable controls for the current client, select each input method, and choose
**Apply and save**. Changes affect only that client. Saved preferences become the
defaults for future client processes. Current settings windows carry an exact
client/scene/ownership/revision ticket: if those change while editing, close and
reopen settings before applying. Disabled controls preserve ordinary native mouse
and key actions. Unsupported bindings are unavailable; there is no macro fallback.

## Keyboard and controller

WASD is camera-relative: forward follows the camera's ground direction, with
left/right perpendicular to it. Opposing keys cancel; diagonal movement is
normalized. Four distinct single keys can be remapped in the panel. The settings
chord is reserved. Text/chat and modal ownership inhibit movement.

Controller slots 1–4 map explicitly to XInput indices 0–3. Devices must expose
XInput gamepad axes; unsupported device types and missing XInput are unavailable.
There is no automatic first-connected selection or DirectInput emulation. The
left stick controls movement direction; the right stick controls the native camera.
Analog direction is retained; speed follows the game's own movement rules.
Movement/camera dead zones, camera radians per second and both camera inversions
are configurable. The native mouse-camera gesture has priority over controller
camera input. Camera-only input does not take over navigation.

Only the bound foreground game instance reads movement input. After focus loss,
controller disconnect/reconnect, UI ownership or a scene change, release movement
keys/buttons and center both sticks before re-arming. Holding a stick while
switching clients does not start the newly focused client moving.

## Hold-and-drag

The default is mouse button 4 (XBUTTON1), with a six-pixel threshold. Left, middle,
mouse 4 and mouse 5 are selectable. Right mouse remains the game's camera gesture.
A normal click below the threshold keeps its original click behavior. A qualified
drag follows the current native terrain pick; invalid ground stops movement.
Releasing stops through native cancellation. UI/inventory/map interactions retain
their native input. Leaving the window, losing capture or changing scene/UI cancels
the gesture; a buffered click is never replayed into a replacement scene.

## Navigation ownership and acceptance

Deliberate manual movement takes over the current native movement owner immediately.
Old-generation movement and stop commands cannot affect the new owner. Releasing
manual input never resumes a route. Resume requires an explicit new `/go` or `/pve`
request after manual controls are neutral. The complete combined package must pass connected acceptance before this behavior
can be certified in the client.

The combined acceptance pass must use the integration owner's exact source and
installed package. Exercise all three input methods and camera-only control;
try an obstacle and native movement restriction; verify each release stops; enter
chat/modal/inventory/map UI; disconnect/reconnect the selected controller; lose
focus/capture and switch clients while input is held; then take over an active
navigation run and verify delayed old moves/stops cannot resume or cancel manual
movement. Confirm explicit route restart works after release. Developer-controlled
native/window tests are evidence for the implementation, not a substitute for this
connected engine/server pass.


Automation uses the same native owner even while manual controls are disabled.
Enabling controls requires neutral input before manual takeover. Travel and PvE
retain their existing planner and bounded destinations; native terrain picking
resolves the destination height. An approach pause stops movement while retaining
that operation's grant; ending the operation releases it. Manual takeover revokes
the grant, and neither release of the keys nor a previous route heartbeat resumes
it. The operation worker renews its live lease separately from dashboard updates.
