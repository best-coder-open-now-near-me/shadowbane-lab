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
