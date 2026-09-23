# Client update: September 4, 2026

The regular testing-VM client was updated to version 1.3.38.6 while the prepared
inspector still used 1.3.38.5. The TextFix launcher verified package integrity but
did not establish that the package matched the server's current client version.

The entire 21,143,613-byte official executable differs from the August 31 frozen
baseline at exactly file offset/RVA 19,775,883: ASCII `5` becomes `6` in the
`1.3.38.5` version string in `.data`. PE headers, section layouts and all other
bytes are identical. Offline alignment checks 16 profiles and 49 anchors, with
zero intersections. The complete scene-rendering code also retains its reviewed
hash, including checks under relocated image bases.

- Previous official SHA-256: `55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc`.
- Updated official SHA-256: `feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff`.
- Updated bootstrapped SHA-256: `bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87`.

Bootstrap authoring against the actual updated executable resolves all seven
existing sites and reproduces the predicted output hash. Both updated identities
join the reviewed native-layout and scene-renderer families. Unknown hashes remain
rejected. The renderer passes the actual matched identity to terrain refresh and
trace instead of labeling every non-baseline build with an older patched hash.

Private evidence remains in `artifacts/navigation-inspector/game-update-alignment.json`
and the testing VM diagnostics `navigation-inspector-3534418/resume-20260904-1915/refinement-e8b24b5`:
`game-update-diff.json` and `updated-official-sb.exe`. Client binaries remain private.

Validation before the source checkpoint: focused bootstrap/layout tests (12 passed),
Ruff, full-profile native build and CTest (18 passed), and the scene-boundary test
against the actual updated executable. Exact committed package validation and VM
replacement follow this checkpoint. Delivery uses `codex/navigation-inspector`, PR
#27 into `codex/integrate-current-development`, then main. Next todo: deploy the
verified current-version package, reconnect the client, then retry the tree detour.

## Verified deployment

Committed source `f0bad0ec561bb3a693676e77f5180b27264005fc` passed the exact package
pipeline: 1,684 Python tests, seven expected skips, 211 subtests; Ruff; both VS2022
Win32 profiles and 18 CTest cases per profile; wheel installation, entry point and
Tk panel. Package `28331e60` archive SHA-256 is
`8f2a4e8f6a7fbfba2331968e1eb31de31355a10baa4de66195652d90d382baad`.
The deployed DLL SHA-256 is
`65c67e8e05397b8acab5f3e01a4e566a1f7c75fcec99250c5a7bcb77ffee8fd2`.

Freezing the current official client also identified updated `cache/CObjects.cache`
and `Config/Config.wpak`. The prepared replacement includes both game-data changes
and the existing restrained texture treatment. Four changed files and package
metadata were backed up before offline replacement. The package's destination
metadata records its actual installed path; the complete runtime inventory was
reverified there, preserving reviewed mutable settings. No navigation state or
calibration was replaced. The frozen source and verified staging package remain in
private host storage because the VM staging drive has limited free space.

The installed runtime remains `S:/ShadowbaneLab-Guided/20260904-inspector-3534418`.
Its existing TextFix desktop shortcut now launches the updated prepared client.
Live verification matched source, executable, loaded DLL, creation identity and
inspector channel for PID 1940, creation FILETIME `134330468660427387`. Panel 1956,
listener 7820 and recorder 2832 were reconnected. Duplicate-launch protection and
helper health checks pass. Login and the refined tree run remain pending.

Private rollback and deployment receipts are retained beneath the same VM diagnostics
folder: `before-current-game-update`, `current-version-deployment.json`,
`current-deployment-plan.json`, `current-game-baseline`, and `prepared-current-client`.
This supersedes the earlier e8b24b5/a9a59004 runtime identities, not the retained
historical acceptance captures. PR #27 still awaits integration; the normal checkout
remains on main. Next todo: login, then the refined tree detour and remaining PvE/
overlay acceptance. Keep the rollback until the current client passes live acceptance.
