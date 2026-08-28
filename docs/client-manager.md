# Local multi-client manager

The manager owns local process and window lifecycle on each Windows PC. It does not own
character strategy. The current command line exposes read-only inventory and lifecycle
preflight; the reusable supervisor layer supports exact attach, shell-free launch correlation,
dispatch pause/resume, non-activating tiling, detach, and graceful close requests.

No manager command currently performs a live lifecycle mutation. That remains behind the
supervisor boundary until the persistent manager application can present reviewed per-client
actions and durable status.

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

## Define and preflight a local group

Copy [the example manifest](examples/client-manager.manifest.example.json), assign this PC a
stable `node_id`, and define one operational client slot per window. Then run:

```powershell
python -m shadowbane_lab.cli manager preflight `
  'C:\path\to\client-manager.json' `
  --json
```

Preflight validates the strict schema, checks the configured executable and directories, and
inspects matching windows without launching, focusing, moving, closing, or sending input. A
valid report returns one binding status per slot:

- `ready_to_launch`: no matching client is open;
- `attachable`: one slot and one matching immutable instance;
- `selection_required`: multiple slots or instances share the filter, so an exact
  `instance_id` must be selected; or
- `unsafe_identity`: at least one matching window lacks a complete process lifetime identity.

Identical client filters are inspected once. Preflight deliberately does not guess which
already-open window belongs to which logical slot. On a fresh start, the supervisor instead
launches slots sequentially and binds only the single new instance found relative to each
launch baseline.

The manifest is local operational topology only. It accepts direct executable and argument
tokens, a working directory, expected process directory and executable names, and an optional
unique window rectangle. Commands are passed directly with `shell=False`. Unknown fields,
duplicate JSON keys, relative paths, duplicate slot IDs, duplicate rectangles, credentials,
character identities, and tactical/caller roles are rejected. Put login handling and character
configuration behind separate guarded boundaries rather than embedding either in this file.

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

## Lifecycle safety contract

Pause and resume change only whether the manager may dispatch work for a binding; they never
suspend the Windows process. Detach forgets a binding without changing the client. Tiling uses
`SetWindowPos` with `SWP_NOACTIVATE` and no Z-order change. Graceful close posts `WM_CLOSE` only.
There is no force-kill path in this slice.

Every tile or close request refreshes the registry and revalidates node ID, deterministic
instance ID, PID, process creation time, and HWND immediately before the native action. Missing,
restarted, reused, duplicated, or ambiguous identities disable dispatch and fail closed. The
launcher PID is retained only as audit information because a launcher may create a different
game process; attachment is based on the new registered game-window identity instead.

## Persistent manager application

The next presentation slice should wrap this core in one local background manager per PC with a
small dashboard or tray UI. It can load the manifest, launch each slot sequentially, show exact
bindings and health, tile all reviewed bindings, and expose pause, detach, and graceful-close
buttons. A later overview may aggregate status from several PCs, but live squad behavior and
the designated bot caller must not depend on that overview or on a central tactical service.
