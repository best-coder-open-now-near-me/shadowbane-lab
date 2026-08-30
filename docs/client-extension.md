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

The v1 x86 DLL exports `WonderBaneExtensionInitialize` and
`WonderBaneExtensionGetStatus`. Initialization is idempotent and publishes one process-lifetime
heartbeat atomically beneath `%LOCALAPPDATA%\ShadowbaneLab\client-extension`; it does not read or
write game state. The status ABI reports the same heartbeat path, ABI/version, process ID,
initialization state, and Win32 result. `verify-heartbeat <heartbeat.json>` strictly checks the
schema and binds the file name to the PID plus process-creation FILETIME.
