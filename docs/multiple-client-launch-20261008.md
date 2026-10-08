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

Use the existing 32-bit PowerShell shortcut. Each invocation starts one new
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
both the new source and DLL hash. Installation/live concurrency remain pending.
