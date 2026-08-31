# Persistent WonderBane client extension

The extension project is isolated from simulator behavior, live automation, and the failed
world-map sidecar experiment. It began with a deliberately inert milestone: a reviewed client
copy loads one versioned x86 DLL, invokes its exported initializer outside the Windows loader
lock, and records a heartbeat. The current milestone adds a build-guarded world-map destination
event boundary for the bounded watched test; it still does not claim route acceptance or movement.

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

The 2026-08-31 patch produced source SHA-256
`55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc`. A preserved vanilla-to-
vanilla comparison found identical PE headers and section layouts, 544 changed bytes across 29
ranges in `.text` and `.data`, and no intersection with 47 calibrated anchors. All seven bootstrap
sites independently resolved at their reviewed RVAs. It is therefore represented by its own exact
bootstrap profile and produces patched SHA-256
`a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8`; unknown hashes still fail
closed.

When the official patcher replaces a packaged `sb.exe`, the old package marker and extension DLL
remain on disk but are no longer loaded. With every client closed, retire those stale artifacts to
a receipt-bearing, recoverable Local App Data quarantine before freezing the new vanilla baseline:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\retire-wonderbane-client-extension.ps1
```

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
For an extension upgrade, pass a new versioned `-DestinationDirectory`, a new `-ManifestPath`, and
the artifact's explicit `-ExtensionVersion`; existing immutable client copies are never rewritten.
After an official patch, pass the newly captured vanilla directory through
`-FrozenBaselineDirectory`; this keeps the prior evidence-directory layout compatible while letting
the same wrapper package an independently timestamped baseline.

The v1 x86 DLL exports `WonderBaneExtensionInitialize` and
`WonderBaneExtensionGetStatus`. Initialization is idempotent and publishes one process-lifetime
heartbeat atomically beneath `%LOCALAPPDATA%\ShadowbaneLab\client-extension`. On the exact reviewed
client, initialization also pins the extension module for the remaining process lifetime before
starting its hook thread. A process-lifetime hook must not outlive its DLL code; the native probe
releases the caller's load reference and verifies that the pinned module remains resident.
WonderBane build, it also observes a uniquely identified open world map and exposes a bounded
process-lifetime event channel. A fresh, exclusive consumer lease is required before the hook will
suppress a qualifying click and publish its projected LT/LG destination. Ordinary injected input,
lower-integrity injected input, stale map snapshots, background windows, ambiguous map objects,
and absent consumers pass through without publication or suppression. The watched acceptance path
uses one dedicated tagged `SendInput` right-click; the tag is an admission marker, not proof of
success. The harness still requires one exact native event and acknowledges it only after every
identity, pixel, button, snapshot, and coordinate field matches.

This milestone intentionally stops at destination capture. It suppresses the captured down/up pair
instead of forwarding it to the original map handler, and no extension code accepts a route or
moves the character. The node-level manager listener is the downstream API boundary: its exclusive
consumer validates the exact process lifetime and window, then submits deterministic stop/travel
operations to that client's existing worker. If the listener is absent, stale, or cannot renew its
lease, physical clicks pass through to the original client instead of being swallowed. The status ABI continues to report the
heartbeat path, ABI/version, process ID, initialization state, and Win32 result.
`verify-heartbeat <heartbeat.json>` strictly checks the schema and binds the file name to the PID
plus process-creation FILETIME.
