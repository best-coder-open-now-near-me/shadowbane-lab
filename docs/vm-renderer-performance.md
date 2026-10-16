# Text-fixed VM rendering performance

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

The existing executable launch regression suite passes 35 assertions. A fresh
game launch, text-readability check and frame measurement remain required before
claiming a performance improvement. If that is insufficient, the next step is
profiling the remaining software-rendering cost and evaluating VM acceleration
while explicitly verifying text readability. Historical cel-profile environment
documentation is not evidence of a supported switch in the installed renderer;
the current native renderer does not read that variable.
