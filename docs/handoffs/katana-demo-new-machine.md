# Continue the katana demo on another Windows computer

## Start here

The katana demo has moved from the slow test VM to a hardware PC accessed through
**Chrome Remote Desktop**. The destination chat qualified its NVIDIA rendering
path and installed selected-character controls; see the
[hardware-PC acceptance record](../mod-pack-pc-20261008.md). Machine paths and
private receipts remain local to that computer. Do not assume an RDP policy or
a remote shell.

Fetch `origin` and use **`codex/katana-moonfire`**, targeting `main` through
[draft PR #106](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/106).
The VM fire source is **0f80838**; the hardware-PC selected-character native
source is **8dce403**. This integration branch now includes the hardware-PC tip
**ab53a09** and main **85e3194** (reviewed bot recovery PR #111, host 0.3.79),
combined at **9146542**. Main does not contain the katana feature yet. Preserve
an existing checkout's user changes; use a separate
checkout if it is already owned by another task. Read the applicable AGENTS.md,
[deployment policy](../deployment-policy.md), [branch map](../git-branch-map.md)
and [demo record](../katana-moonfire.md) before deployment.

## What already works

The actual Archon katana model replaces a selected stand-in item locally. The
native extension identifies the chosen character's two owned katana render
instances and transforms each at the existing hand-grip origin. The panel offers
**My character** and **Selected character**. Missing selection suppresses the
effect rather than applying it to self; ownership is rechecked before each draw.
The user chose
**80% overall length**; width is unchanged. Both blades now show native moon-fire:
a sparse white diamond chain, staggered pulses, a slower hilt diamond, a narrow
collar and additive blade ribbon. Graphics Lab's **Katana** tab controls it live.

Preserve the approved starting values:

| Control | Value |
| --- | ---: |
| Overall length | 80% |
| Moon-fire | On |
| Square size | 100% |
| Spacing | 80% |
| Pulse | 35% |
| Hilt diamond size | 125% |
| Glow strength | 111% |
| Glow width | 86% |

These are compiled defaults in the current source. The process-specific control
channel is schema 3; install the panel and DLL from the same feature revision.
Combined source reports host 0.3.79/native 1.8.54, so version labels alone are
insufficient: record the exact Git revision and artifact digests.

VM acceptance: both owned weapons and both fire draws were observed in game,
with zero native error/suppression and a visually inspected capture. Installation
preserved all 47 settings files. Full build, 238 required native tests, 48 focused
host tests and the real Tk panel/layout check passed. Three private-image entries
skip without explicit inputs; the unchanged image/binding paths were qualified
at the preceding length checkpoint. Real OpenGL tests cover pixels, pulse,
occlusion, clipping, stencil/depth preservation, mirrored scale and state restore.
Arbitrary translucent-scene ordering and every possible animation remain
unqualified. This is a local cosmetic demo, not a server equipment change.

## Destination setup

1. Inspect the destination's existing Wonderbane installation, launcher, renderer
   DLLs and exact executable/cache identities before changing anything. The
   tested source supports the reviewed official 1.3.38.15 client; use the source's
   identity/binding checks, not the displayed version alone. Preserve settings,
   saves and jobs in place. An unknown executable requires new qualification.
2. Build the **full**, Win32 extension from this feature branch. Existing build
   entry point: `scripts/build-wonderbane-client-extension.ps1 -Profile full`.
   It uses CMake and Visual Studio 2022 C++ tools. Output is normally
   `build/wonderbane-client-extension/Release/wonderbane-extension.dll`.
   Do not substitute a main-branch DLL or the diagnostics-only profile.
3. Create a Python 3.11+ environment with Tk support and install this checkout
   (`python -m pip install -e ".[client-extension]"`; add `[test]` for host checks).
   Graphics Lab starts with `python -m shadowbane_lab.graphics_lab`. Its source
   and defaults are complete in the repository; no VM share is required.
4. Use the existing `client_extension.bootstrap_author`, `resolver` and `package`
   APIs/CLI to author and verify the destination's exact bootstrap/package. See
   `python -m shadowbane_lab.client_extension --help`. The VM installer was bound
   to that VM's paths and inventories and is not a portable installer. Author new
   local receipts; do not transplant its package.json or launcher pins. Keep the
   official source read-only and use an independently needed prepared client.
5. Recreate the item appearance override from the destination's local caches
   using `client_extension.item_appearance.build_item_appearance_cache`. Resolve
   the user's actual stand-in item and Archon's Blade there. The donor render
   expected by this demo is 0:9996101, with mesh 0:29243 and texture 0:8029210.
   Inspect donor dependencies, primary/alternate renders and attachment before
   changing a reference. If the item already points to the donor, verify it
   instead of rebuilding a second override. Preserve native compression: storing
   the CObjects replacement raw previously passed offline decoding but crashed
   the native loader. The builder now tests direct stored-byte decompression.
6. Install only after the game and panel close, using exact source/artifact checks
   and atomic replacement. Update launcher pins and package inventory for the
   authorized changes; verify the complete runtime package and preserved user
   settings afterward. Do not create retained rollback copies. Log in through
   the destination's verified launcher, attach Graphics Lab and select Katana.

Source ownership:

- `native/wonderbane_extension/weapon_appearance.*`: ownership, length, channel,
  per-weapon draw scope and deduplication.
- `native/wonderbane_extension/moonfire.*`: native fire and supported-state checks.
- `native/wonderbane_extension/selected_cue_runtime.cpp` and `cel_shading.cpp`:
  existing callback integration. The global late-composition gate stays closed.
- `src/shadowbane_lab/graphics_lab/katana.py`: panel, defaults and channel client.
- `src/shadowbane_lab/client_extension/item_appearance.py`: verified appearance
  candidate builder. It does not install or supply private game assets.
- `scripts/weapon-preview/`: browser study, not the in-game renderer.

## Frame-rate acceptance

The test VM launcher explicitly forces `LIBGL_ALWAYS_SOFTWARE=true` and
`GALLIUM_DRIVER=llvmpipe`; historical graphics launchers also cap its worker pool.
Those are VM-specific choices. Do not copy the VM launcher or blindly inherit
that software profile on the destination. Inspect any local OpenGL wrapper and
its ownership before changing it; do not delete an official or unrelated DLL to
force a renderer switch. Verify the **actual game renderer and loaded module**,
not merely the GPU model listed by Windows. Hardware rendering and the effect
were verified on the destination; a measured before/after frame-rate comparison
is not recorded.

Measure actual game frame timing (existing `diagnostics.frame_timing` support is
available), separately from the remote viewer's apparent smoothness. Compare
fire on/off at the same resolution, scene and camera with other graphics settings
held fixed. Coordinate that short comparison with the user so an automatic write
does not fight their sliders. Check both hands and a few movement/attack poses,
then restore their selected values. Do not promise that Chrome Remote Desktop
or a different GPU alone guarantees a particular frame rate.

## Next todos

The hardware-PC installation and selected-character acceptance are complete.
Active source integration targets PR #106; follow the branch map for its latest
validation and inclusion status. No runtime is changed by the source merge.
Next demo work is a measured fire-on/off frame-rate comparison and final capture.
Keep the general Visual Inspector (self/selected-object
render tree, mesh/texture/effect references, equipment mapping and door picking)
**after** the katana demo. Do not expand the current task into that tool yet.

GitHub contains the source and this handoff. Original game binaries, caches,
extracted textures, generated asset previews, credentials and private captures
are intentionally not included; obtain game assets from the destination's
legitimate official client. The new chat should build/install locally and keep
its fresh diagnostic receipts private.
