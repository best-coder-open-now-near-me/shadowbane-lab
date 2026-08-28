# Local multi-client manager

The first manager slice is a read-only inventory of every matching visible Shadowbane
client on one Windows PC. It does not focus a window, send input, launch a client, or stop a
process. Its output is the attachment boundary for later lifecycle supervision and per-client
workers.

## Inspect one PC

Give each PC a stable operator-chosen node ID and run:

```powershell
python -m shadowbane_lab.cli manager inspect `
  --node-id gaming-pc-east `
  --process-directory 'C:\Games\Wonderbane' `
  --json
```

The executable name defaults to `sb.exe`. Repeat `--executable-name` when an installation
uses reviewed alternate names:

```powershell
python -m shadowbane_lab.cli manager inspect `
  --node-id gaming-pc-east `
  --executable-name sb.exe `
  --executable-name Shadowbane.exe `
  --json
```

An attachable client requires all of the following from the same Win32 snapshot:

- process ID;
- process creation time from `GetProcessTimes`;
- top-level window handle;
- executable name and path; and
- visible client bounds and DPI.

The lifetime-stable `instance_id` is derived from the node ID, process ID, process creation
time, and window handle. Window movement, title changes, or foreground changes do not change
it. Process restart, PID reuse, window recreation, or moving the client to another PC does.
Matching windows with incomplete lifetime identity are listed under `rejected` instead of
being attached by guesswork. Duplicate process or window identities fail the complete
inspection.

Zero clients is a successful inventory snapshot. This lets a future supervisor distinguish
an idle node from an inspection failure.

## Multi-PC boundary

Each PC owns its local window manager and local client workers. `node_id` is operational
provenance for identities, evidence, and diagnostics; it is not a tactical owner and does not
bind a character role to a particular PC.

Workers on every PC will derive local role tactics from the same in-game group composition.
The operator retains macro movement and push control through Shadowbane's existing group-control
mechanic; automated formation travel is not a dependency of the manager.

One explicitly designated bot character will summarize the tactic emerging from the group state
as concise group-chat calls for the operator and other humans. Chat is therefore a guarded output
of the caller, not the bots' tactical command bus. The caller must use exactly-one ownership,
priority and expiry rules, deduplication, rate limits, and the same foreground/process guard as
other live input. Other workers must not emit duplicate calls when they observe the same state.
Individual characters continue role-appropriate survival, support, targeting, and combat
behavior whether or not a chat call can be emitted.

Networked central strategy is therefore not required. A later dashboard may aggregate node
snapshots for convenience without becoming a dependency of live squad behavior.

## Next lifecycle slice

The next manager step is an explicit instance manifest and a supervisor that can launch,
attach, tile, pause, and request graceful shutdown for exact registered instances. Forceful
termination remains a separate guarded operation and must revalidate node, PID, creation time,
and window handle immediately before acting.
