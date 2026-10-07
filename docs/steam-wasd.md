# Steam WASD add-on

Development branch: `codex/steam-wasd`, based on main `acb1ba7`.
Integration destination: `main` through a reviewed PR. This lane is independent of
WonderBane host .75/native .52 and must not replace its x86 runtime.

## Qualification status

The user confirmed basic movement but found W pointing approximately screen-left
and inconsistent behavior with auto-track. The attached `418bd22` runtime used a
yaw assumption that does not represent the final rendered view. Its live status
recorded 143 move calls and 43 stop completions without a native fault; this does
not qualify camera orientation, chat, or focus behavior.

The 0.1.1 camera correction derives forward and screen-right from the actual
inverse screen-to-world matrix and eye used by native screen picking. It follows
auto-track/orbit changes and removes the yaw/character-heading assumption. All
three local suites pass: 2,160 camera combinations, 216 rays compared against
native Steam unprojection, 12,800 native queue erases, and input-boundary tests.
The correction is installed from source `60f7305` after the client exited.
Next: relaunch and retest camera-relative W/A/S/D
with auto-track on and off, plus release/chat/focus behavior.
[Draft PR #88](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/88)
targets main; live acceptance is still pending.

## Exact client boundary

Steam app 4371680, build 25499060, `SBOnlinex64.exe` (AMD64), displayed version
1.2.1300/protocol 5.39.1300. Reviewed SHA-256:
`0e1ba847d03c7f471601d0139c0769cb13f89b0a6a085955a9d09e7545d1e27a`.
Reject other files and modified executable sections. ASLR changes the image base;
all source profile addresses are RVAs. Do not reuse the WonderBane x86 patch set.

The profile was derived from local disassembly and read-only in-world inspection.
The frame callback is the offset-8 ArcWindowGame interface's slot 2, RVA e29cf0,
pointing at a1e820 (`this = primary window + 8`, double frame interval). Movement
uses 10dc80 with a 32-byte ground target; message ownership is consumed by 5a56e0.
The actor's state object is at f60, path vector at 1118/1120/1128 (24-byte elements),
identity at 18, position holder at 668, and pose coordinates at 60.

Stop removes both active and scheduled movement ownership. Native 304170 clears
the active world map at 148; the scheduled map at 1a0 requires native tree detach
330490 followed by the native sized allocator release c975e0 (56-byte node).
The detach function updates map size and sentinel links itself. Its exact machine
code passed 12,800 randomized erases including singleton, root, internal and leaf
removal using a matching MSVC map, without calling any live game operation.
Native d7770 destroys path references; 196660 updates destination; 10abd0 changes
moving state 7 to idle 5 and creates the native message. Other states must remain
unchanged. Retain/release the actor through 326ac0, never a raw pointer lifetime.

Typing is identified by df800 and 9f1090/focused kind 698 (5, 6, 14). Modal state,
input inhibition, foreground, native window mode, actor identity and parent frame
must all gate input. Losing a gate stops owned movement and requires released keys
before rearming. Steam settings and SCREEN bindings remain user-owned.

## Build and local validation

```powershell
cmake -S native/steam_wasd -B artifacts/steam-wasd/build -G 'Visual Studio 17 2022' -A x64 -DSTEAM_CLIENT='C:/Program Files (x86)/Steam/steamapps/common/Shadowbane/SBOnlinex64.exe'
cmake --build artifacts/steam-wasd/build --config Release
ctest --test-dir artifacts/steam-wasd/build -C Release --output-on-failure
```

The optional image test requires the official local executable and never uploads
it. Private disassembly/live observations and generated binaries stay ignored
under `artifacts/steam-wasd`. Follow [deployment policy](deployment-policy.md):
no retained deployment rollback copies; recover from committed source.

## Runtime and use

`steam_wasd_launcher.exe --attach [PID]` attaches with movement disabled.
`--status`, `--enable`, and `--disable` report/control the same exact process
creation. With no arguments, the launcher starts Steam app 4371680 if necessary,
attaches, and enables WASD. Keep `steam_wasd.dll` beside the launcher.
Ctrl+Alt+F10 toggles movement; always release the keys once after enabling.
W/S move forward/backward and A/D move left/right relative to the camera.
Opposing directions cancel; diagonal directions have unit length.

The add-on is currently limited to open ground (no parent-local coordinate
frame). It yields while typing, using modifiers, inactive/minimized, in modal UI,
or outside idle/moving states. A mouse click stops owned WASD movement before
normal native click handling. Native movement preserves game collision and speed.
It has no route playback, bot workflow, or packet construction.

Status gate codes: 0 available, 1 disabled, 2 not foreground, 3 parent frame,
4 modal/native window blocked, 5 modifiers/input inhibition, 6 typing,
7 actor state/restriction, 8 no active world scene, 9 fault, 10 invalid camera basis.
A fault disables further native operations. Restart the game before trying a
rebuilt DLL; uncertain operations are not replayed. Disabling leaves the pinned
callback loaded until exit. The original executable and client settings are not
patched on disk, and the launcher never terminates the game.

## Local installation receipt

Current candidate: `E:\Projects\shadowbane\artifacts\steam-wasd\runtime`.
Exact runtime source: `60f7305514d3b01784a5954c9f5c69b71d1b7057` (0.1.1).
DLL SHA-256: `445a3c4ae2cc8b220ab6ed75197c5838a61a9b1c9d305cd3390626b35450fcbd`.
The local `receipt.json` records the full source and launcher hash. No Steam files
or settings were replaced and no rollback deployment was retained. Private live
status evidence is in the worktree's `artifacts/steam-wasd/live-status.log`.
CI builds the standalone x64 targets and runs input tests; exact-image tests
remain a local qualification requirement because the game executable is private.

## Camera profile and regression boundary

Native screen-ray routine a25d40 reads eye XYZ at 105a904/105a908/105a90c and
passes the matrix at 105aa70 to 191880. The public native unprojection wrapper is
235df0. Matrix element accessor c62160 proves column-major indexing; native rays
perform homogeneous division before subtracting the eye. The movement basis now
uses these exact renderer inputs, independent of actor heading and yaw settings.

Screen-right and screen-down rays define the view plane; their normal is oriented
away from the camera eye and projected to the ground. Screen-right fixes the
handedness. The exactly overhead case uses projected screen-up. Double precision
scratch avoids cancellation at large world coordinates. Invalid/degenerate views
stop owned movement and require a fresh key release before resuming. No camera
setting is changed. Parent-local coordinate frames remain outside qualification.
