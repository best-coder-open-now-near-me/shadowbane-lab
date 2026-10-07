# Steam WASD add-on

Development branch: `codex/steam-wasd`, based on main `acb1ba7`.
Integration destination: `main` through a reviewed PR. This lane is independent of
WonderBane host .75/native .52 and must not replace its x86 runtime.

## Qualification status

The input policy and exact-image native queue tests pass. Runtime integration
and live movement validation are unfinished; there is not yet an installed pack.
Next: connect the game-thread hook, qualify stop/scene/input boundaries, and test
WASD with the user in the Steam client before describing it as usable.

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
