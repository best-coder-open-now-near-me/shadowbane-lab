# Text-fixed VM rendering performance

Current state: the test VM has eight vCPUs and virtual 3D enabled. The game still
uses its working Mesa software text fix with a six-worker limit and maximum
graphics. The requested combat translation candidate is installed in the same
client. Next are fresh in-world FPS and numeric/newline acceptance; the accelerated
driver failed three visual checks and is not approved for the real game.

The October 16 investigation keeps the Mesa invisible-text compatibility path:
`LIBGL_ALWAYS_SOFTWARE=true`, `GALLIUM_DRIVER=llvmpipe`, extension ceiling 2001,
and no GL/GLSL version overrides. Do not remove those settings as a performance
shortcut. Vendor rolling remains stopped during this investigation.

The active test VM has four vCPUs, 128 MB graphics memory, VBoxSVGA and hardware
3D disabled. Its game loads the packaged Mesa OpenGL libraries. A live CPU sample
showed the game consuming almost all four vCPUs, with additional manager/worker
load. Memory had roughly 4 GB available.

A reversible twenty-second effects A/B/A observation measured 1.91, 1.95 and
1.50 FPS. The animated combat scene was not controlled, so these are diagnostic
observations rather than a benchmark. Disabling the optional graphics flags did
not show a substantial improvement; the exact original parameters were restored.
Private captures and detailed measurements remain under the local October 16
client-alignment artifacts and are not published with source.

The reviewed launcher omitted the `LP_NUM_THREADS=3` limit already used by the
graphics baseline and navigation inspector launchers. It now applies the same
limit so Mesa does not use every virtual CPU for rendering. All text-fix settings,
the client and native extension remain unchanged. This setting takes effect at
the next game launch. It does not resize the game or change its saved settings.

The existing executable launch regression suite passes 35 assertions. The updated
launcher was installed by exact old/new hash and the same Vendor Test shortcut
relaunched. Read-only inspection of the fresh process confirmed all text-fix
variables and `LP_NUM_THREADS=3`; client and extension hashes are unchanged.
The user reports performance considerably better and approximately back to its
previous level. A fresh thirty-second in-world sample measured 6.64 FPS, median
141.93 ms and 95th-percentile 264.30 ms. The before/after scenes were not controlled;
these observations do not establish a precise speedup or adequate performance.

A ten-second CPU sample attributed 4.95 CPU seconds to the main game thread,
4.28/4.27/4.22 seconds to the three Mesa workers, and 1.89 seconds to a native
extension thread. Thread start modules identify ownership, not sampled call stacks.
There was over 4 GB guest memory available. The host has a 20-core Core Ultra 7
265K and an RTX 5060 Ti. VirtualBox logs confirm the Windows hypervisor backend;
host virtualization-based security is active. These facts are diagnostic evidence,
not authorization to disable host security or proof of its performance cost.

The user requires maximum graphics quality because this client also tests mod-pack
visual changes. The proposed lower-shadow/terrain experiment was cancelled before
any settings were written. Verified current values remain projected shadows 2,
terrain detail 4, texture detail 2 and particle density 1.0; window, resolution,
draw distance and visual effects are unchanged. Future performance acceptance must
use those settings and preserve readable text.

Next: evaluate more VM CPU capacity and accelerated rendering without lowering
quality. Merely enabling virtual 3D will not accelerate a child process still
forced to llvmpipe. Any hardware-rendering path requires separate font and mod-pack
visual verification before replacing the working text fix. Historical cel-profile
environment documentation is not evidence of a supported switch in the installed
renderer; the current native renderer does not read that variable.

After the user shut the test VM down normally, its exact identity and powered-off
state were checked. CPU count was raised from four to eight and virtual 3D enabled.
The VM restarted successfully; Windows detects eight logical processors and Guest
Additions remains 7.2.4. RAM (8,954 MB), VRAM (128 MB), VBoxSVGA and all verified
maximum-detail preferences are unchanged. The launcher still has the proven
three-worker Mesa limit, so the first measurement will isolate additional VM
capacity before changing that limit. Interactive Windows sign-in, fresh-game FPS
and separate system-OpenGL capability probing remain pending. No acceleration or
performance benefit from the new VM settings is claimed yet.

The fresh eight-core game is verified with a healthy idle manager/worker. Its
thirty-second sample measured 3.92 FPS, median 195.47 ms and 95th-percentile
473.47 ms. Windows/VirtualBox automatically changed the desktop after reboot and
the fullscreen viewport is now 1920x976 rather than 1280x960, about 53% more
pixels. No game detail settings were lowered or manual resolution change made.
The samples therefore cannot establish a CPU-count performance regression or
improvement. Preserve the current window size for subsequent comparisons.

The x86 system-OpenGL probe succeeds on the virtual GPU: SVGA3D, OpenGL 4.1
compatibility profile, Mesa 24.0.2. Its initial invalid-pixel-format error was
resolved by loading OpenGL before selecting the pixel format. The current
qualified native graphics executables were then run separately on that driver:
banded-lighting and depth-edge checks passed; sky, moon-fire and selected-cue
visible-pixel checks failed. Those failures are retained and not waived. They
do not distinguish virtual-driver limitations from hidden-window test behavior,
and this hardware rendering profile is not qualified for mod-pack testing.
The real game remains on Mesa 26.1.7 software rendering with the working text fix.

The next launcher candidate scales the software-worker limit with available
CPUs: three on four vCPUs and six on eight or more, with a minimum of one worker
and maximum of six. It preserves the established four-core limit while using
more of the enlarged VM and leaving capacity for the game and observers. All
41 executable launcher assertions pass. The six-worker launcher and nine combat
translation values were installed together after the game was already closed.
The public runtime-copy verifier passed; exactly one immutable client asset
changed, its package inventory was refreshed, and all 17 settings/layout files
were preserved. Host .122, native .75 and the prepared .22 executable are unchanged.
Fresh-launch maximum-quality FPS acceptance for six workers remains pending and
no benefit is claimed yet.

The user also authorized combining the combat-channel translation candidate from
`eb871ae8d8a1968254717a14afc4316f10a951fa` with the next vendor test composition.
Its nine display-value changes are now installed for the requested combined test,
and still require numeric substitution and newline rendering acceptance. The
compiler is included in this branch by cherry-pick `6a4eb314`. That candidate does
not fix self-drain semantics or implement bold/underline. Keep one owner for the
combined runtime installation.

The source components are recorded separately: native/host
`cae3008549b7f4d00b45fed1dd28a83941d844b8`, launcher
`36e17977cea88d51dc08f6cd146e21ed664c60a5`, and translation compiler
`eb871ae8d8a1968254717a14afc4316f10a951fa`. The base native package provenance is
unchanged; the separate installation receipt records the compiled translation
component. Launcher SHA-256 is
`5ce6ea08fdd5d0353a50d4a04152fcd8f002383257e7abc5f2c19468b6366ba9` and
translation SHA-256 is
`4b21d60fc382d4b5047561a60bcdcdf088b46a750a2f10b533faefa6db01a9aa`.
The pinned installation plan is
`46682253736366dcde5b169ac22452cfc77d4fdf39e9124d567803a95a10b12a`.

The user's official-patch reminder was checked before installation. A fresh
cache-bypassed October 16 14:54 UTC feed response still has manifest SHA-256
`e8d285a29d0f9a8f9ac7d96378b2f50d4a873073030ce01eda5f6d51e92e4939`,
the same exact .22 executable and zero changed assets. The separate official
client matches; no unnecessary official-client rewrite was performed.
