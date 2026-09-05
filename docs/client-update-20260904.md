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
