# Multiple reviewed client launches

The Vendor Test, Modded Client and Inspector shortcuts previously shared a
private deployment launcher that rejected any running `sb.exe`. This was our
launcher restriction, not evidence of a client singleton. Native mappings and
registry identities already distinguish PID plus process creation time.

`scripts/launch-wonderbane-reviewed-client.ps1` is the maintained launcher source.
Install it as `launch-reviewed.ps1` beside a `reviewed-launch.json` configuration:

```json
{
  "schema_version": 1,
  "source_revision": "<qualified runtime source SHA>",
  "prepared_source_revision": "<optional original base SHA when an installed overlay is active>",
  "client_sha256": "<prepared executable SHA-256>",
  "extension_sha256": "<qualified DLL SHA-256>",
  "official_executable": "<absolute official sb.exe path>",
  "official_sha256": "<official executable SHA-256>",
  "baseline_guard_sha256": "<reviewed check-vendor-client-baseline.ps1 SHA-256>"
}
```

Installed shortcuts use 32-bit PowerShell with an explicit `-RuntimeRoot`
argument naming the deployed runtime folder. Always retain that argument when
recreating a shortcut or invoking this launcher from another script; the
implicit script-root default did not resolve under Windows PowerShell 5.1.
The same explicit argument was used in the successful live launch. Each invocation starts one new
visible client after existing package, DLL, official-client and settings checks.
A short filesystem lock serializes startup bookkeeping, not running clients.
There is no global process-count restriction, process selection by enumeration,
window size requirement, or automatic bot dispatch.

Each successful launch writes `launches/<pid>-<creation>/launch-receipt.json`.
The root legacy receipt stays byte-for-byte unchanged while its exact client
lifetime is live. An old root receipt is retained as compact historical evidence
before advancing a positively ended lifetime. PID reuse cannot inherit the old
binding. Ambiguous identity inspection fails without retargeting. HWND refresh
within an existing lifetime does not rewrite its immutable original launch record.
Simultaneous launch attempts cannot overwrite each other's records. Failed
startup leaves its process ID and diagnostic evidence; it does not kill other clients.

Consumers must choose an explicit process/lifetime receipt for another client;
launching it does not rebind existing automation. The manager may need an available
configured slot before a second bot worker can attach. Shared game settings remain
in place; this change does not duplicate client assets or create rollback runtimes.

## Delivery

Branch `codex/multiple-client-launch-20261008` starts from refreshed main
`500fe40` and targets `main`. The deployed .78/.54 runtime source remains `6c8ea10`;
this change updates launcher source/configuration only. PR #108 merged the launcher after all 15 hosted checks passed on `4a6da9f`;
29 executable assertions passed under both 32-bit and 64-bit Windows PowerShell.
Installation detected a concurrently installed katana overlay before any writes.
The follow-up `codex/multiple-client-overlay-20261008` retains that update by
separating the prepared base source from the extension/receipt source. When the
optional prepared source is present, its installed overlay receipt must match
both the new source and DLL hash. PR #109 merged after all 15 hosted checks passed on `bac2ec3`. Independent
review and all 35 receipt/source-identity assertions passed in 32-bit PowerShell.
The installed launcher/configuration now retain the later moon-fire overlay
`0f808385d83c731306021b38109e623bde265be1` on prepared base `6c8ea10`.
No client binary, cosmetic asset, saved setting or active game was replaced.

## Verified installation and concurrent launch

Installed launcher SHA-256:
`b2a397777d28a31eb7e2f7011151bd7a7f9b349b27f63e7697d92a3bf8a9b86a`.
Configuration SHA-256:
`26e3764b1c61e0a1048623649100c446b406e3bf6ab2b5bdc8609f806d7c6399`.
Current overlay DLL:
`e6dcdef161abac62b91c5275b3334c07f0a77d6755ef48c7dd950fa21689a2c7`.

At 19:55 UTC on October 8, both game windows were visible and non-minimized:

| Instance | PID | Creation FILETIME | HWND |
| --- | --- | --- | --- |
| Existing client | 264 | 134359626477012528 | 1049484 |
| Additional client | 4100 | 134359627798514406 | 329000 |

Both have separate lifetime receipts. The existing root receipt remained byte
exact at `9f66fb1a58ae2f75d7eb307d3c7bfd4bde9d2f66ccdd8c8560c30de330b43c97`.
No gameplay actions were sent. Vendor Test, Modded Client and Inspector shortcuts
were updated and reread to verify their explicit runtime argument; dashboard
shortcuts were unchanged. No retained rollback files were created.

Private installation, window and shortcut evidence stays under local
`artifacts/multiple-client-launch-20261008` and the corresponding diagnostics
share. Initial installation attempts rejected newer cosmetic-launcher identities
before writing; those newer versions were inspected and preserved. The first
implicit-root invocation failed before launch; the explicit-root invocation
successfully started the additional client and is now the installed shortcut
configuration. Future updates should update `reviewed-launch.json` pins rather
than replace this maintained launcher with an old generated singleton script.

The operational multiple-launch fix is complete. Future bot validation must
identify the intended character and select its explicit process/lifetime;
launching a second client is not evidence of multi-worker combat acceptance.
