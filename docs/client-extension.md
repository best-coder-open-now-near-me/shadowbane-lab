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
  --dry-run --pretty
```

Without `--dry-run`, it builds beneath a temporary sibling and atomically publishes a new working
directory only after rereading the baseline, patched executable, extension, and full output
inventory. `verify-copy <new-working-copy>` repeats that check. The explicit
`discard-copy <new-working-copy> <receipt.json>` command refuses a changed copy, verifies the
frozen baseline again, deletes only the marker-bound disposable directory, and publishes a
rollback receipt outside it.

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
heartbeat atomically beneath `%LOCALAPPDATA%\ShadowbaneLab\client-extension`; it does not read or
write game state. The status ABI reports the same heartbeat path, ABI/version, process ID,
initialization state, and Win32 result. `verify-heartbeat <heartbeat.json>` strictly checks the
schema and binds the file name to the PID plus process-creation FILETIME.

## Renderer-boundary diagnostic

Extension 1.3.0 first tested the exact reviewed client's `OPENGL32.dll!glShadeModel` import by
forcing every request to `GL_FLAT`. Live validation proved the extension initialized successfully,
but that state change was not visually distinguishable in the low-poly client. This graphics-only
runtime contains no map, movement, combat, manager, or automation hooks.

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

Extension 1.4.3 removes the persistent wireframe state and keeps `GL_FLAT` as the conservative
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

Orthographic UI/map rendering, points, lines, and array draws outside the reviewed element-count
bound remain single-pass. Immediate-mode geometry remains filled and flat-shaded because replaying
an arbitrary `glBegin`/`glEnd` stream would require intercepting every vertex and state mutation.
Any missing or ambiguous required import or OpenGL helper still rejects initialization before the
first IAT mutation; partial hook installation retains the existing rollback behavior.
