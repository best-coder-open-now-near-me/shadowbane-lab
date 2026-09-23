# Native movement and camera controls

Native controls, transport, manager and standalone automation ownership are integrated
through `codex/native-lifecycle-hardening`. This document describes their settings
and behavior. The integration owner verifies the exact combined package and supplies
its acceptance record. Connected movement behavior remains pending that focused
acceptance; source tests and installed control checks do not establish live success.

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
chord is reserved. Text/chat owns keyboard movement and drag steering. Controller
movement and camera remain usable during text entry and never inject typing. Real
modals, inventory dragging, native input inhibition and failed UI queries stop all
controls. After text entry ends, release movement keys before a fresh press.

Controller slots 1–4 map explicitly to XInput indices 0–3. Devices must expose
XInput gamepad axes; unsupported device types and missing XInput are unavailable.
There is no automatic first-connected selection or DirectInput emulation. The
left stick controls movement direction; the right stick controls the native camera.
Analog direction is retained; speed follows the game's own movement rules.
Movement/camera dead zones, camera radians per second and both camera inversions
are configurable. The native mouse-camera gesture has priority over controller
camera input. Camera-only input does not take over navigation.

Only the bound foreground game instance reads movement input. After focus loss,
controller disconnect/reconnect, global UI inhibition or a scene change, release movement
keys/buttons and center both sticks before re-arming. Holding a stick while
switching clients does not start the newly focused client moving.

## Controller action profile

The native settings panel includes editable action rows. Defaults are **left stick
move**, **right stick look**, and **B cancel movement/navigation**. Movement and look
can use either stick. Cancel can use a gamepad button or trigger; triggers activate
above 20 percent. Cancel uses native stop once and retires the previous movement
owner. Holding it does not repeat. Release all buttons/triggers and center both
sticks before moving again; a cancelled route needs an explicit new request.

Select a row, change its action/control/shoulder combination, and choose **Add /
replace row**. With no row selected, this adds a binding. **Unbind row** removes it;
**Reset defaults** restores the three default rows. Editing changes a draft until
**Apply and save** validates and activates the whole profile. Conflicts leave the
active settings unchanged. All-unbound profiles are valid. Up to 24 rows are saved.

A base row applies unless that control has a row for the exact held shoulder
combination (left, right or both). Both shoulders use the both-shoulders row or
base; they do not choose between separate left/right rows. A shoulder used as a
modifier cannot also trigger an action. One physical control resolves to one
action; two sticks cannot drive the same vector action in one combination.
Profiles preserve analog direction, dead zones and camera sensitivity/inversion.
Applying changes, focus/device loss and real global UI inhibition require physical
neutral; an unbound control is not treated as proof of neutral. Chat behavior is
unchanged: controller movement/look/cancel remain native and typing stays in chat.

Only these verified native actions are currently offered. Hotbar powers, targeting
and interaction remain unfinished; no key macro or unwired action choice substitutes
for a verified client adapter. This profile subset does not complete combat controls.

The profile requires the matching native/Python package (action-channel schema 3,
saved settings format 2). Older automation clients and incompatible producers are
rejected before command/lease mutation. Existing saved movement settings migrate
with the default controller rows. Product versions and installation remain under
the integration owner's combined package process.

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

Standalone live `client go` and `client run-pve` also require the native extension.
Each command owns one exact-client operation and renews its lease every 250ms
while the planner runs. Exiting performs native terminal stop and releases the
lease. Missing bindings produce an error; there is no mouse-movement fallback.
After manual takeover, explicitly issue a new route or PvE command to resume.


## Focused connected acceptance sequence

Use the integration owner's frozen, installed combined package and shared
acceptance record. Record its source SHA, DLL/wheel/package identities, selected
controller slot and control settings before starting. Use the already accepted
zone navigation scenario and representative obstacles; do not repeat navigation
research. A supported XInput gamepad and a second client are needed for the device
and isolation cases. Each observation below remains pending until performed.

| Step | Action and expected result |
| --- | --- |
| Disabled baseline | Launch normally with manual controls disabled. Check ordinary selection, native mouse camera, inventory drag and world map. No manual keys or buttons are consumed. |
| WASD and remapping | Enable, release all input to arm, rotate the camera, then press each direction, opposing pairs and diagonals. Movement follows camera-relative ground direction, opposing pairs cancel and diagonals do not increase native speed. Remap a key and check its original action is suppressed only while controls own it. Release stops through the native path. |
| Controller | Select the intended XInput slot. Test left-stick direction above/below the configured dead zone and right-stick sensitivity/inversions. Analog direction is preserved at the game's normal permitted speed. Neutral stops. Looking around during /go preserves the route; dead-zone noise cannot take it over. |
| Terrain and mouse drag | Hold the configured X1 default over valid world terrain and cross the six-pixel threshold; steer over sloped terrain and around an obstacle. Release stops. A below-threshold click retains its native click behavior. Invalid terrain does not invent a destination. Check normal selection, inventory, map and right-button camera interactions remain usable. |
| Text entry | Open chat while using controller movement/camera: sticks keep working and release stops. Type movement-bound keys: text receives them and keyboard movement stays blocked. Close chat while a key is held: movement requires neutral then a fresh press. Text cancels an existing navigation route; closing text never resumes it. |
| UI and focus | While moving, open a real modal or inventory drag, lose focus, lose capture or leave the client. Movement stops. Return with input still held: nothing restarts until neutral and deliberate input. |
| Device and instance | Disconnect during stick movement. Reconnect while held: nothing restarts until neutral. Switch focus between two clients: only the intended foreground instance receives movement/camera input; the previous instance stops. |
| Ownership race | Start /go, then deliberately move manually. Release: route stays cancelled. Repeat with /pve and confirm attack dispatch also stops. Correlate diagnostics with the existing automated delayed-command/stale-stop regressions; old ownership cannot resume movement or stop a newer owner. Explicitly issue a new route to resume. |
| Native constraints and lifecycle | Exercise an obstacle and a normal movement restriction, confirm native collision/animation/server behavior, then transition character/scene and disable/re-enable. No old input, destination or stop affects the new scene. Quit cleanly. |

Collect failures with expected/observed behavior and package identity in the shared
record. Developer native tests already cover delayed processing and 20/30/60/144/240
Hz camera integration; during acceptance compare available frame-rate conditions
without changing the accepted source or introducing alternate movement writers.
