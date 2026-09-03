# Active character configuration binding

The character profile is selected from the logged-in local player's **name and server**,
not the number, ordering, age, or hotbar contents of saved CFG files. The process executable
directory owns the `Config` root, including isolated client copies. Explicit profile paths
must match that same identity and root; they are not an identity-guard bypass.

The shared binding owns a read-only process handle, PID, creation FILETIME, executable
SHA-256, local-player instance, character/server names, exact CFG path, and content SHA-256.
Reads are bounded to 64 bytes per native operation. Two complete identity observations must
agree. Missing profiles, unreviewed builds, malformed strings, redirected paths, and identity
changes fail closed. No memory writes, name scans, keyboard probes, or filename guessing occur.

Each new operation resolves again. An active operation's binding is checked before each
input, and becomes permanently revoked on a failed check. It never silently switches
characters during combat. Reinitialize after relogging or changing the saved profile.

This selects the **saved CFG**, not an in-memory mirror of unsaved hotbar changes. Save hotbar
changes before starting an operation. Power/action verification remains necessary: selecting
the right character does not automatically make that character compatible with proc-Assassin.

## Mapping provenance (2026-09-02)

Exact executable: `sb.exe`, SHA-256
`55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc`.
Source: frozen testing-client baseline `wonderbane-20260831T023921516Z`.
The executable was inspected offline, not run or patched. Addresses below are RVAs;
the inspected image base was `0x00400000`.

| Source | Observed behavior |
| --- | --- |
| `0x795DA0` load path | Reads local player at `0x16A2D98`; requires nonzero character-config flag at `0x16A7C60`; formats `Config/SCREEN_%s_%s_%s.cfg`. |
| `0x7963E0` save path | Independently uses the same player/flag/name/server fields and filename format. |
| player + `0xC48` | Character name passed through the filename encoder. |
| player + `0xC90` | Server name passed directly to the string conversion. |
| `0x128240` thunk target | Passes the character string to the encoder through `0x41BADB` (VA). |
| `0x1485B0` encoder | Iterates UTF-16 code units, masks to 16 bits, formats each with `%0.4hX`, and concatenates. |
| `0x114165C` | Existing reviewed ArcCharacter vtable, checked on the local-player object. |

Both fields use the existing Core::String UTF-16LE layout: begin/end/capacity pointers at
`+4/+8/+12`, trailing NUL. This reader additionally requires nonempty bounded strings and
filename-safe values. Its flag check accepts only canonical boolean `1`.

Offline byte-range fingerprints (SHA-256):

- RVA `0x795DA0`, 267 bytes: `b74f5cd96d56f0aef7885539e0cef9f3592c8243fd98781711a4f3ae6289cab6`
- RVA `0x7963E0`, 243 bytes: `f443f45191496f1342b9b52a5a3152357a2e6a9ece77284b3271e9d89890f703`
- RVA `0x1485B0`, 288 bytes: `376d5e3bdf37364d01e228514091b6f5b2b7c29ef33e46e8c9c19176fe5c885b`

The older ef43784b native-layout compatibility family does **not** authorize these new
fields. A patched executable needs its own review before adding it to
`REVIEWED_CHARACTER_CONFIG_LAYOUTS`. Do not weaken the hash guard or guess drift offsets.

## Validation status

Inside the testing VM, with a character logged in (PowerShell may stay foreground):

```powershell
$env:PYTHONPATH = '\\VBOXSVR\codexrepo\src'
& "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe" -m shadowbane_lab.cli client inspect-active-profile --json
```

With multiple clients, add `--process-id` with the intended client's PID. Inspection sends
no input. Compare `character_name`, `server_name`, and `config_path` with the active client.
`active_slots` reports the saved hotbar's assigned powers.

`run-pve`, the `/pve` listener route, and manager workers resolve the CFG during each PvE
initialization. Omit `-HotbarConfig` / `--hotbar-config`; an explicit override must still match.
The selection appears as `character_config` in final evidence and continuous journal metadata.
The basic policy does not use hotbar powers and does not require a character CFG.

Synthetic-memory tests cover five saved profiles, exact character/server/client-root matching,
process-lifetime metadata, missing files, wrong builds, corrupt/torn strings, relogging, and
revocation before input. The operator has now reported a successful live read-only inspection:
automatic selection returned success and the saved hotbar exposed the expected power binding.
This records only a non-identifying success summary; machine-specific diagnostic output is not
included. Live character switching and a completed PvE encounter have not yet been verified.

Combined checkpoint validation (including upstream PvE work through `9553531`):

- Python: 1,318 passed, 6 skipped; 211 subtests passed.
- Ruff: clean (also corrected an import-order-only error in the merged action-trace test).
- Native full and diagnostics-only: Win32 Release builds succeeded; 11/11 CTest checks each.
- Both changed PowerShell launchers parsed successfully without execution.
- Python wheel built successfully with isolated declared build dependencies.
- No native DLL deployment, game launch, memory write, or character CFG edit was performed.
