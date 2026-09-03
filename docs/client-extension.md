# Persistent WonderBane client extension

The extension project is isolated from simulator behavior, live automation, and the failed
world-map sidecar experiment. Its first milestone is deliberately inert: a reviewed client copy
loads one versioned x86 DLL, invokes its exported initializer outside the Windows loader lock,
and records a heartbeat without changing game behavior.

The implementation order is strict:

1. freeze and verify an untouched official client tree;
2. resolve every patch operation from a hash-pinned manifest without writing;
3. build and verify the no-op extension artifact;
4. apply the complete plan atomically to a disposable client copy;
5. launch, exit, relaunch, verify the heartbeat, and verify ordinary game behavior;
6. roll back the disposable copy and confirm the frozen baseline is unchanged; and
7. only then add map behavior to the extension.

The official client directory and frozen baseline are never patch targets. The patcher accepts
only a separately created working copy and refuses unknown executable hashes, changed original
bytes, missing sites, ambiguous signatures, output overwrites, or extension artifact drift.

## Freeze the client baseline

The patcher's displayed version is not treated as a client build identifier. Every frozen client
is tracked by its complete executable and canonical tree SHA-256 values. The wrapper reports a
compact content build such as `wb-55fbad5f-4b602995`; the full hashes remain authoritative in
`client-baseline.json`. To verify and display the ID again without trusting a folder name, run
`python -m shadowbane_lab.client_extension identify-baseline <frozen-client> --pretty`.

For the isolated 55fb graphics line, one wrapper verifies the frozen content ID, authors only the
reviewed loader manifest, runs the complete no-write package check, checks local free space, then
publishes and rereads a versioned graphics-only client:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\publish-wonderbane-graphics-baseline.ps1
```

The wrapper sets `PYTHONPATH` to the `codexrepo` convergence share and never starts the control center, listener,
manager, map capture, movement, combat, or automation paths. Graphics package 1.5.0 also applies the
hash-pinned restrained-cel atlas manifest while the copy is still unpublished; the patched cache and
its texture evidence are included in the package inventory before atomic publication.

After publication succeeds, launch that exact verified package for graphics testing with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\launch-wonderbane-graphics-baseline.ps1
```

The launcher rechecks the publication receipt, executable and extension hashes, and complete package
inventory before starting `sb.exe`. It supplies the reviewed software-rendering environment only to
the child process and restores the calling PowerShell environment immediately afterward. It does not
start the control center, listener, manager, movement, combat, or other automation components.
The llvmpipe worker pool is capped at three threads so rendering cannot consume every testing-VM
vCPU and starve Windows, Guest Additions, or the VirtualBox display path.

Inside the WonderBane VM, with the official client closed, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\freeze-wonderbane-client-baseline.ps1
```

The script copies the current client directory into a new timestamped folder beneath
`\\VBOXSVR\codexdiag\client-baselines`. It does not open the source for writing. The published
`client-baseline.json` contains:

- SHA-256 and size for every regular client file;
- a canonical tree digest;
- the executable's PE structure and SHA-256;
- the repository revision that produced the evidence; and
- the source and frozen directory paths.

Capture refuses existing output, nested source/destination trees, links and reparse points,
oversized inventories, missing or ambiguous executable paths, and malformed PE input. It copies
into a temporary sibling, rereads the copy, writes evidence with create-new semantics, and only
then atomically publishes the frozen directory.

Keep the baseline and executable private because they are local game artifacts. Do not commit
either one.

## Build and probe the x86 extension

On the development host with Visual Studio 2022's Win32 C++ toolchain installed:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  .\scripts\build-wonderbane-client-extension.ps1 -RunProbe
```

The build is pinned to the Visual Studio 2022 generator and refuses non-x86 configuration. Release
compilation treats warnings as errors and enables ASLR, NX, control-flow guard, reproducible linking,
and static runtime linkage. The probe is itself x86: it loads the artifact by exact path with safe
DLL search flags, resolves both public exports, calls initialization twice to prove idempotence,
reads the v1 status structure, verifies the heartbeat is a regular file, and unloads the DLL. The
probe intentionally leaves that small heartbeat under Local App Data as test evidence. Build output
is ignored by Git; the reviewed artifact hash belongs in the real patch manifest.

## Patch manifest and alignment evidence

Schema version 1 pins the source executable by file name, length, PE machine, pointer size, and
SHA-256. It separately pins the x86 extension artifact and the predicted patched executable hash.
Each canonically ordered patch site records its PE section, reviewed RVA, exact original and
replacement bytes, and a bounded masked signature. Signatures must wildcard any bytes the patch
changes, so an already-patched output can be verified without trusting its file hash alone.
The reserved `headers` region identifies reviewed bytes inside `SizeOfHeaders`; it lets the same
resolver safely verify section-header changes without pretending those bytes belong to a mapped
section.

Site alignment is evidence, not write authority. It reports exact, uniquely relocated, missing,
ambiguous, missing-section, and architecture-mismatch results for a candidate PE. A compatible
candidate is still rejected by the patch planner unless its complete SHA-256 is the manifest's
reviewed source hash. The planner also rejects overlapping writes, changed precondition bytes, and
any in-memory result whose SHA-256 differs from the manifest's predicted output.

The package command first supports a no-write dry run:

```powershell
python -m shadowbane_lab.client_extension prepare-copy `
  <frozen-client> <new-working-copy> <reviewed-manifest.json> <versioned-extension.dll> `
  --texture-patch-manifest <reviewed-textures.json> `
  --texture-artifact-directory <reviewed-atlases> `
  --dry-run --pretty
```

Without `--dry-run`, it builds beneath a temporary sibling and atomically publishes a new working
directory only after rereading the baseline, patched executable, extension, and full output
inventory. `verify-copy <new-working-copy>` repeats that check. The explicit
`discard-copy <new-working-copy> <receipt.json>` command refuses a changed copy, verifies the
frozen baseline again, deletes only the marker-bound disposable directory, and publishes a
rollback receipt outside it.

Texture overlays are optional for the generic command but fail closed as a pair: a manifest requires
an artifact directory and vice versa. The manifest pins the complete source cache, every source
resource payload, every PNG, dimensions/depth, and every encoded result payload. A write plan is
built against the frozen cache before copying. Overlays are applied only inside the unpublished
temporary package, post-write resources are reread, and `texture-patches.json` becomes part of the
ordinary package inventory. An already-published client is never modified in place.

After a disposable client has run, `audit-copy` reports exact added, missing, and changed paths
against its signed package inventory. `discard-runtime-drifted-copy` accepts only a caller-reviewed
actual tree digest, rejects every added file and every non-runtime changed or missing path, archives
the surviving runtime-written files with their hashes, records recognized runtime deletions in a
schema-v2 receipt, reverifies the frozen baseline, and only then retires the disposable directory.

Immutable verification and runtime verification now consume the same single-pass package audit.
The reviewed runtime-mutable path policy lives separately from package inventory and retirement,
so adding a client-written file requires an explicit policy review instead of another verifier.
`verify-launchable-copy` remains a compatibility alias for canonical `verify-runtime-copy`.

## Loader boundary

The extension DLL's `DllMain` remains minimal. Initialization and heartbeat work happen through
an explicit exported function invoked after `LoadLibrary` returns. This follows Microsoft's
loader-lock guidance and gives later map functionality a normal initialization boundary:

- [Dynamic-Link Library Best Practices](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-best-practices)
- [PE Format](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format)
- [Dynamic-Link Library Security](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-security)

The bootstrap strategy is not guessed. The baseline executable's imports, section capacity,
entry path, and candidate patch bytes must be inspected before a real manifest is reviewed.
Synthetic PE fixtures exercise the patch engine first; no fixture result authorizes a real client
patch.

With every `sb.exe` process closed, the first real-client evidence pass is one VM command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\collect-wonderbane-client-extension-evidence.ps1
```

It freezes a fresh complete baseline and writes `bootstrap-inspection.json` beside it beneath a new
timestamped `\\VBOXSVR\codexdiag\client-extension-evidence` directory. Inspection is read-only and
labels itself `evidence_only_no_patch_authority`. It records exact imports and IAT RVAs, 128 entry
bytes with bounded x86 instruction boundaries, PE header slack, and only executable padding beyond
a section's declared virtual size. Keep the evidence private because it contains a short byte
window from the executable. A real manifest is authored only after manual review of that output.

The reviewed WonderBane 1.0.5 profile pins source SHA-256
`e358237c458ddfe2fc7a86e478f165a8fd067655ab1a8ada5731f790c6995d96`. Its author refuses every
other executable, rechecks the exact entry prefix, section layouts, import directories, KERNEL32
thunks, zero padding, and extension export, then independently rebuilds the complete patch plan.
The generated loader is position independent. It extends the existing KERNEL32 lookup and address
tables with `GetProcAddress`, loads `wonderbane-extension.dll`, calls
`WonderBaneExtensionInitialize`, restores the entry state, replays the five displaced bytes, and
continues at the original entry path. Author a create-new private manifest with:

The 2026-08-31 patch produced source SHA-256
`55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc`. A preserved vanilla-to-
vanilla comparison found identical PE headers and section layouts, 544 changed bytes across 29
ranges in `.text` and `.data`, and no intersection with 47 calibrated anchors. All seven bootstrap
sites independently resolved at their reviewed RVAs. It is therefore represented by its own exact
bootstrap profile and produces patched SHA-256
`a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8`; unknown hashes still fail
closed.

```powershell
python -m shadowbane_lab.client_extension author-bootstrap `
  <frozen-client>\sb.exe <versioned-extension.dll> <new-private-manifest.json> --pretty
```

The patch remains seven bounded writes: the entry jump, the loader stub, two import terminators,
one hint/name record, and the `.text`/`.idata` virtual-size fields. No import table is relocated and
the executable length does not change.

The reviewed VM evidence and artifact can be dry-run or published through one wrapper. It first
authors the create-new manifest when absent, always runs the complete no-write package validation,
and only then atomically publishes a new destination unless `-DryRunOnly` is supplied:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\prepare-wonderbane-client-extension-copy.ps1 -DryRunOnly
```

Omit `-DryRunOnly` only after the dry run passes. The wrapper refuses an existing destination and
inherits the package verifier's exact frozen-directory binding, inventory, hash, and reread checks.

The v1 x86 DLL exports `WonderBaneExtensionInitialize` and
`WonderBaneExtensionGetStatus`. Initialization is idempotent and publishes one process-lifetime
heartbeat atomically beneath `%LOCALAPPDATA%\ShadowbaneLab\client-extension`. It pins the extension
module before starting any process-lifetime hook so those hooks cannot outlive their DLL code. The
status ABI reports the same heartbeat path, ABI/version, process ID, initialization state, and Win32
result. `verify-heartbeat <heartbeat.json>` strictly checks the schema and binds the file name to the
PID plus process-creation FILETIME.

On the exact reviewed WonderBane build, initialization also observes a uniquely identified open
world map and exposes a bounded process-lifetime event channel. A fresh, exclusive consumer lease is
required before the hook suppresses a qualifying click and publishes its projected LT/LG
destination. Ordinary injected input, lower-integrity injected input, stale map snapshots,
background windows, ambiguous map objects, and absent consumers pass through without publication or
suppression. The watched acceptance path uses one dedicated tagged `SendInput` right-click; the tag
is an admission marker, not proof of success. The harness requires one exact native event and
acknowledges it only after every identity, pixel, button, snapshot, and coordinate field matches.

This event milestone stops at destination capture. It suppresses the captured down/up pair instead
of forwarding it to the original map handler, and no extension code accepts a route or moves the
character. The manager listener validates the exact process lifetime and window before submitting
deterministic stop/travel operations to the existing worker. If the listener is absent, stale, or
cannot renew its lease, physical clicks pass through to the original client.

## Renderer-boundary diagnostic

Extension 1.3.0 first tested the exact reviewed client's `OPENGL32.dll!glShadeModel` import by
forcing every request to `GL_FLAT`. Live validation proved the extension initialized successfully,
but that state change was not visually distinguishable in the low-poly client. This graphics-only
runtime contains no map, movement, combat, manager, or automation hooks.

The native console probe is deliberately not named `sb.exe`, so it exercises only the exported
ABI and atomic heartbeat writer. Any process named `sb.exe` takes the renderer path and must pass
the complete OpenGL import preflight before the extension reports initialized.

Extension 1.3.1 therefore strengthens the same fail-closed diagnostic. Initialization resolves and
preflights the executable's unique `glShadeModel`, `glBegin`, `glDrawArrays`, and `glDrawElements`
IAT slots before changing any of them. It also resolves `glPolygonMode` from the loaded OpenGL
implementation. The four IAT replacements are installed transactionally; partial failure rolls
back installed slots while retaining safe original targets if an external race prevents rollback.
Every immediate-mode or array draw forces `GL_FRONT_AND_BACK` to `GL_LINE`, while shade-model
requests still force `GL_FLAT`. Unknown executables, missing or ambiguous imports, changed IAT
state, and protection failures reject initialization instead of guessing.

This is deliberately an unmistakable diagnostic, not the final restrained cel treatment. Its
purpose is to prove which fixed-function draw boundaries own the live renderer. Once confirmed,
the production pass can replace wireframe with bounded lighting bands and silhouette handling.

Live validation on the reviewed 55fb client produced an unmistakable full-scene wireframe while
the manager independently reported extension 1.3.1 initialized, the exact client attached, and its
worker dispatch-ready. That closes the renderer-boundary diagnostic: the executable import path,
extension lifetime, and scene draw ownership are all proven together.

## Restrained cel treatment

Extension 1.4.5 removes the persistent wireframe state and keeps `GL_FLAT` as the conservative
fixed-function lighting treatment. It adds the reviewed client's unique `glCallList` import to the
same transactional IAT plan, allowing replayable display-list geometry to receive a bounded
silhouette pass. Perspective display lists and polygonal array draws render all polygon boundaries
as fixed-width lines first, followed by the client's ordinary filled draw. The fill covers interior
edges while the exterior half of silhouette edges remains, including on open and one-sided meshes.
The outline pass uses `GL_CLEAR` color logic so captured display-list colors cannot leak white or
textured pixels into the border, and it disables line smoothing and dithering for stable coverage.
This keeps outline width independent of object size and distance and avoids the directional bias
caused by scaling meshes around off-center model pivots. The pass saves and restores all server
attributes, writes no depth, and confines its state changes to the outline draw.

The silhouette is further limited to depth-writing draws whose affine model-view origin is within
4096 camera-space units. This excludes sky passes and world-origin terrain draws that otherwise
turn the distant horizon into a fixed-width black stroke, while retaining locally transformed
characters, props, and nearby structure pieces.

Outline width is derived from camera-space depth, the live perspective projection, and viewport
height, corresponding to a constant 0.5-unit world-space thickness. It is clamped to 1–4 raster
pixels and omitted when its projected width falls below 0.75 pixel. Nearby models therefore receive
the strongest stroke, while distant models taper naturally instead of appearing over-inked.

The reviewed client's `glNewList`, `glEndList`, `glVertex3f`, and `glDeleteLists` imports now maintain
a bounded local-space extent for each compiled display list. Tracked lists use a front-face-culled
dark hull expanded around the captured bounds center by the same 0.5-unit
world-space thickness. This restores separation between independently compiled body, armor, and
prop pieces without scaling around the often off-center model pivot. Lists without trustworthy
bounds retain the line silhouette, and deleted list IDs invalidate their captured bounds. Each
outlined draw remains two-pass: centered hull or line fallback, then the client's ordinary fill.

The extension also tracks `glViewport` and `glMatrixMode` at the client's existing state-change
calls. This removes synchronous integer state reads from every outlined draw while preserving the
distance rule and ensuring the centered hull runs only against the model-view stack.

`GL_FLAT` remains interpolation control rather than true toon-light quantization. A separate
lighting-state audit is required before introducing discrete diffuse bands; version 1.4.5 does not
claim or synthesize lighting bands.

Extension 1.4.6 tested a post-fill polygon-line replay for interior accents. Live validation rejected
that design because its depth-biased triangle edges visibly separated from animated surfaces and
read as wireframe beneath the skin. The rejected pass remains documented so it is not reintroduced.

Extension 1.4.7 replaces polygon-line replay with geometry-aware feature edges captured once while
each display list is compiled. It reconstructs triangle, strip, fan, quad, quad-strip, and polygon
faces, merges shared edges by exact local-space vertex identity, removes coplanar triangle seams,
and retains only open boundaries, non-manifold boundaries, and edges whose adjacent face normals
cross the reviewed crease threshold. A hard vertex and retained-edge budget rejects pathological
lists rather than creating an unbounded renderer cost. The retained segments draw after the normal
fill at the same depth, without polygon offset or depth writes, so they cannot protrude from the
surface like the 1.4.6 diagnostic. The approved world-scaled exterior silhouette remains unchanged.

Extension 1.4.8 extends the same feature-edge policy to character and prop geometry submitted through
the client's fixed-function vertex-array path. Transactional hooks track `glVertexPointer`,
`glEnableClientState`, and `glDisableClientState`; eligible `glDrawArrays` and `glDrawElements` calls
then reconstruct only their bounded float vertex stream and supported byte, short, or integer index
stream. Memory ranges, arithmetic, primitive counts, and retained-edge counts are validated before
reading. Array geometry uses the identical open-boundary, non-manifold, and dihedral-crease selector
as display lists, so broader character coverage does not lower the threshold or restore triangle
wireframe. The array range is validated once per draw rather than once per vertex.

Extension 1.4.9 makes contour treatment respect alpha-cutout geometry. When the source draw has alpha
testing enabled, the exterior replay preserves the bound texture and alpha-test state so transparent
texels reject the hidden support polygon instead of outlining its rectangular or triangular extent.
Explicit geometry-only feature segments are omitted for those draws because they do not carry the
texture coordinates required to follow the visible alpha boundary. Solid character, armor, building,
and ship meshes retain the geometry-aware feature-edge pass.

Extension 1.4.10 restores feature segmentation on alpha-tested vertex-array meshes without regressing
cutout silhouettes. The extension tracks the fixed-function texture-coordinate array alongside the
vertex array, carries endpoint UVs into retained feature edges, and submits those UVs while preserving
the source texture and alpha test. Edges without trustworthy UVs remain omitted on alpha-tested draws.

Extension 1.4.11 scopes flat interpolation to contour-eligible draws. The extension forwards the
client's requested shade model for ordinary rendering and immediate-mode scenery. Only a draw that has
already passed the perspective, local-model, visible-width, and depth-write gates is temporarily filled
with `GL_FLAT`, after which the exact source shade model is restored. Scenery that cannot receive the
complete cel treatment retains its original lighting depth instead of becoming uniformly flat.

Extension 1.5.0 replaces that diagnostic `GL_FLAT` fill with the recovered `RESTRAINED CEL`
lighting target. A fragment-only GLSL 1.20 compatibility program leaves the client's fixed-function
vertex path active, preserving animated transforms, original normals, and smooth interpolated
lighting. It quantizes lighting into the target's exact four bands at `0.22`, `0.43`, and `0.66`,
modulates the existing texture/alpha, and explicitly reproduces linear, exponential, and squared
exponential fog. The program is limited to the already-reviewed contour-eligible draw boundary and
requires fixed-function lighting, texture unit zero, a modulate texture environment, and no
preexisting shader program. Unsupported or failed shader state receives the client's untouched
original fill rather than a degraded approximation.

The package pairs that lighting with the two reviewed target atlases for texture resources
`1706002` and `5000190`. Their source cache, source payloads, PNGs, encoded results, and final cache
are verified by the immutable texture-patch path described above. The Blender reference's per-model
preview exposure is intentionally not reproduced in gameplay; it was presentation setup rather than
a material or lighting primitive. The golden target, source-generator/report hashes, palette,
outline settings, sample identities, and runtime translation live in
`evidence/graphics/restrained-cel-v1/target.json`.

The fragment-only behavior follows the fixed-function/program interaction defined by the
[OpenGL 2.0 specification](https://registry.khronos.org/OpenGL/specs/gl/glspec20.pdf) and the
compatibility built-ins defined by the
[GLSL 1.20 specification](https://registry.khronos.org/OpenGL/specs/gl/GLSLangSpec.1.20.pdf).

Orthographic UI/map rendering, points, lines, and array draws outside the reviewed element-count
bound remain single-pass. Immediate-mode geometry retains the client's original fill because replaying
an arbitrary `glBegin`/`glEnd` stream would require intercepting every vertex and state mutation.
Any missing or ambiguous required import or OpenGL helper still rejects initialization before the
first IAT mutation; partial hook installation retains the existing rollback behavior.

Extension 1.5.4 adds identity-bound graphics-present diagnostics for the reviewed client. The
extension hooks the exact `GDI32.dll!SwapBuffers` import at IAT RVA `23789964`, counts observed
presents, and publishes an atomic status document under
`%LOCALAPPDATA%\ShadowbaneLab\client-extension`. The filename binds the record to the process ID and
process-creation FILETIME; the document also records the executable path and SHA-256 so a diagnostic
consumer can reject stale records, PID reuse, and a different client binary.

The present hook performs no hashing or filesystem I/O. It samples a newly observed OpenGL context
once, increments an in-memory counter, and signals a background publisher. The status reports the GL
and GLSL versions, depth-buffer precision, viewport, depth-texture capability, and framebuffer-object
capability. A screen-space depth-edge pass remains explicitly `not-implemented` until a live capture
confirms those prerequisites. Missing, mismatched, or stale runtime evidence therefore blocks the
dependent decoder instead of silently selecting an unverified rendering path.

Extension 1.5.5 extends that same identity-bound producer with exact present timing. Each successful
present observation receives a monotonic sequence number and a Windows Query Performance Counter
timestamp. The status schema publishes a bounded 1,024-sample ring plus the counter frequency, a
snapshot QPC/UTC FILETIME anchor, oldest and latest available sequences, capacity, sample count, and
timing-query failure count.

The hook remains memory-only: it performs one QPC query, updates the bounded ring under the existing
state lock, and signals the publisher. The background thread formats and atomically replaces the
status document. A continuously polling diagnostic consumer must deduplicate by present sequence and
record a gap whenever the producer's oldest available sequence overtakes the next sequence expected
by the consumer. This allows captures longer than the ring's residence window without making the
hook retain unbounded history. Exact per-present records, producer overwrite gaps, query failures,
and clock anchors must be sealed before offline FPS, percentile frame-time, and hitch analysis is
considered complete.

Extension 1.5.6 makes passive renderer diagnostics a compile-time profile instead of a side effect
of the cel renderer. A diagnostics-only artifact starts the atomic graphics-status publisher and
installs only the reviewed GDI32.dll!SwapBuffers observer. It does not initialize the extension
event channel, world-map capture, draw-call hooks, banded lighting, outline replay, texture
replacement, or a software-renderer override. The native probe requires the profile's event mapping
to be absent.

The status document records runtime_profile as either diagnostics-only or full-renderer, and the
capture consumer rejects missing or unrecognized values. Diagnostics publication copies the
reviewed source client into a separate package, verifies the package and extension identities, then
removes its transient full baseline payload while retaining the baseline manifest. The known-good
source directory is never patched in place. The diagnostics launcher uses the normal inherited
graphics environment and waits for an identity-bound diagnostics-only status before reporting a
successful launch. The bounded wait is owned by the client-extension command rather than by
PowerShell polling:

```powershell
python -m shadowbane_lab.client_extension wait-graphics-status <status-directory> `
  --process-id <pid> --process-creation-filetime-utc <filetime> `
  --executable <sb.exe> --executable-sha256 <sha256> `
  --runtime-profile diagnostics-only --timeout-seconds 20
```

It rechecks the live PID/creation-time pair on every poll and accepts only the derived status
filename, schema, producer, profile, executable path, and executable SHA-256.

Extension 1.6.1 converges the passive diagnostic producer with the live graphics laboratory. The
full profile owns the reviewed event channel, world-map capture, live graphics-control mapping,
strong cel renderer, depth-edge composite, and optional performance telemetry. The diagnostics-only
profile owns only identity publication, atomic graphics status, and passive present observation; it
does not create the event channel, graphics-control mapping, world-map capture, renderer mutations,
or performance telemetry.

The status schema now publishes the bounded present-timing ring, depth-edge state and composite
count, and live-control revision state in one atomic document. The depth pass is owned once per
frame at the perspective-to-overlay boundary so UI and text remain outside the composite. Control
changes cross the process boundary through the versioned shared mapping and are applied by the
render thread at a reviewed frame boundary.

Extension 1.6.2 adds the bounded camera-state producer without giving diagnostics ownership of
rendering. The full profile publishes from its existing classified world-draw path. The
diagnostics-only profile starts a separate pass-through observer for the exact `glBegin`,
`glCallList`, `glDrawArrays`, and `glDrawElements` imports. Candidate state must be perspective,
depth-writing, affine and orthonormal, and observed at base model-view stack depth; every candidate
within one present must agree or that frame is counted as a producer drop. Both paths stage one
accepted sample against the next present sequence and publish QPC time, position, normalized
forward/up, projection zoom, vertical FOV, complete view/projection matrices, and viewport.

The passive observer does not alter OpenGL state or write client data. It installs only validated
IAT redirections whose original targets match the reviewed OpenGL exports, rolls them back
transactionally on failure, and uses no guessed client offsets.

Startup remains transactional. Exact process identity and client executable checks precede native
services; failure unwinds performance telemetry, renderer or passive observation, graphics control,
status publication, world-map capture, and the event channel in reverse ownership order. Both full
and diagnostics-only Win32 profiles are built and tested as release gates.

Extension 1.6.4 establishes the first compatibility-era deferred-renderer substrate. Every hooked
submission is classified from mirrored fixed-function state as unknown, opaque world,
alpha-tested world, translucent world, depthless world overlay, or UI overlay. A typed frame state
owns one world-to-UI transition; the scene composite runs before that first UI draw, and any later
world-shaped submissions are rendered by the original client unchanged while being counted as a
boundary violation. This replaces the previous scattered orthographic/planar checks with one
auditable policy used by immediate, display-list, array, and indexed draws.

At that boundary the renderer performs one GPU-to-GPU depth copy and one GPU-to-GPU scene-color
copy. The outline shader samples the captured world pixel, derives local luminance and hue, uses
dark ink on bright surfaces, and uses a restrained chromatic rim on dark surfaces. UI and text draw
after the composite and are therefore absent from both the captured scene and the effect. No pixel
readback, per-draw framebuffer copy, or CPU image processing is permitted. Texture storage is
reused until resize, bounded by the reported maximum texture size, tied to the current OpenGL
context, and explicitly released on a same-context renderer reset. Any scene-color copy failure
falls back to the previous depth-outline blend without blocking the original renderer.

The graphics status document carries versioned `scene_color_capture` and `draw_classification`
blocks. They report capture/fallback state, latest and cumulative layer counts, the exact reason
counts behind each classification, world-to-UI boundaries, and excluded late-world draws. The
diagnostics collector preserves and validates both blocks and separately assesses whether true
scene color and world/UI separation were observed.

Semantic actor, terrain, building, water, and particle identities are deliberately not guessed from
the current fixed-function state. The 1.6.4 classes are reliable rendering-policy layers; the next
renderer ownership slice will bind bounded texture/display-list provenance to semantic class masks,
using these diagnostics to review the mapping before normals, AO, or material-specific effects rely
on it.

Extension 1.6.5 removes synchronous Boolean-state queries from the immediate, display-list, and
array draw hot paths. The renderer takes one fixed-function snapshot at the first classified draw
of an ordinary frame, then mirrors the reviewed client imports for `glEnable`, `glDisable`, and
`glDepthMask`. Renderer-owned transient state changes continue to call the original OpenGL
functions directly and therefore cannot corrupt the client mirror. The frame diagnostics expose
the refresh count and reject more than one ordinary-frame refresh, making a return to per-draw
driver synchronization observable before another live release.

The 1.6.5 graphics publication scripts are sealed to the probed full-renderer artifact and the
patched executable derived from the frozen 55fb baseline. Publication creates a fresh 1.6.5
package and receipt before the launcher will execute it.

Extension 1.6.6 corrects the scene-frame ordering assumption exposed by the live WonderBane
client. Orthographic draws that occur before the first positively classified world draw are now
treated as a prelude rather than a permanent world/UI boundary. Positively classified world draws
remain eligible for per-draw cel lighting and feature accents even when they occur after an
observed UI boundary; the late ordering remains counted diagnostically and does not request a
second scene composite. This preserves original UI draws while preventing an early orthographic
submission from disabling world effects for the entire frame.

Extension 1.6.7 corrects the remaining premature-boundary case observed in the live 1.6.6 frame
diagnostics. A single perspective planar overlay appeared before 1,104 subsequent world draws and
was incorrectly allowed to seal the scene, so the depth-edge composite contained almost no world
geometry even though its counters reported success. Planar overlays are now excluded from cel
processing without changing the scene phase; the later orthographic transition owns the one
pre-UI composite. Diagnostics require exactly one boundary and zero late-world draws before they
claim that world/UI separation was observed.

Extension 1.6.8 restores the composite ownership that produced the known-good 1.5.6 through 1.6.1
screen-space contours. The earlier scaling defect was not a texture-atlas defect: the old exterior
pass enlarged each mesh, converted a desired pixel width into world-space scale, and suppressed the
result below an estimated 0.75-pixel threshold. Commit `78a5942` replaced that path with a true
one-screen-pixel depth discontinuity, and that fixed-pixel implementation remains intact.

The later scene-classifier refactor regressed when that intact depth pass ran. It let the first
UI-shaped classification permanently own the frame boundary even when the depth pass had no pending
world geometry. Live 1.6.7 evidence then disproved the remaining assumption that the first
orthographic draw was a trustworthy boundary. In 1.6.8 orthographic and planar draws are retryable
composite candidates, while the idempotent depth pass alone accepts and seals the boundary after a
world draw has armed it. A rejected candidate leaves the scene in its current phase so later world
draws remain part of the capture; an accepted attempt consumes the sole composite for that frame.

The status document now preserves a bounded ordered journal for every completed frame: total and
world draw counts, candidate and rejected-candidate counts, and the ordinals of the first world,
first candidate, accepted boundary, first late world, and last world draws. The diagnostics consumer
reconciles those milestones with the layer totals and refuses to claim world/UI separation unless
the last world draw precedes the accepted boundary. This records the ordering evidence that the
1.6.6 and 1.6.7 aggregate counters could not preserve.

### 1.6.9: reviewed main-scene boundary recovery

Live 1.6.8 ordering evidence disproved the armed-depth heuristic: preliminary
geometry and early overlays could still consume the scene before the main clear.
The renderer now uses the reviewed client's main-clear and `done3D` UI setup
call sites, guarded by exact executable identity and a relocation-normalized hash
of the complete owning routine. It keeps one GPU-only capture/composite before
UI, preserves the main projection, and reports latest-frame composite success.
Unknown mappings keep original rendering; no guessed boundary is substituted.

The durable evidence, mapping, regression cases, artifact pins and outstanding
live acceptance are in [the recovery journal](investigations/renderer-scene-boundary.md).
