# Local multi-client manager

The manager owns local process and window lifecycle on each Windows PC. It does not own
character strategy. The command line exposes read-only inventory and preflight plus an explicit
live, localhost-only dashboard. The persistent session supports exact attach, shell-free launch
correlation, dispatch pause/resume, non-activating tiling, detach, and graceful close requests.

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
already-open window belongs to which logical slot. On a fresh start, the supervisor launches
slots sequentially and binds only a single new instance whose exact PID and creation-time
lifetime is either the reviewed launch process or a verified live descendant. An unowned
baseline client, a racing unrelated client, incomplete identity, or unprovable launcher lineage
fails closed to explicit attach instead of being assigned by timing.

The manifest is local operational topology only. It accepts a direct executable, a strictly
allowlisted operational argument grammar, a working directory, expected process directory and
executable names, and an optional unique window rectangle. Commands are passed directly with
`shell=False`. Unknown fields, duplicate JSON keys, relative paths, duplicate slot IDs,
duplicate rectangles, credentials, character identities, and tactical/caller roles are rejected.
Put login handling and character configuration behind separate guarded boundaries rather than
embedding either in this file.

`launch.environment` is optional and intentionally narrower than a general process environment.
It accepts only the reviewed Mesa variables used by the WonderBane invisible-text compatibility
launcher: software rendering through `llvmpipe`, the `2001` extension ceiling, and explicit
removal of the GL/GLSL version overrides. PATH changes, credentials, arbitrary renderer settings,
and every other variable are rejected. The manager merges accepted settings into a fresh copy of
its own environment immediately before the direct launch.

`launch.arguments` is a JSON array of separate tokens, but it is not an arbitrary command-line
escape hatch. The complete accepted grammar is:

- `-windowed` or its reviewed alias `--windowed`, at most one of the two;
- `--client`, at most once, for a launcher that needs the reviewed client-mode marker; and
- `-resolution` followed immediately by canonical `WIDTHxHEIGHT`, at most once. Width and height
  are base-10 integers without signs or leading zeroes, each from `1` through `16384`.

These options may appear in any order, and the array may be empty. Tokens are passed exactly as
written, so case variants, combined forms such as `-resolution=1920x1080`, positional values,
unknown options, duplicates, and unreviewed aliases all fail closed. Supporting another
operational launcher flag requires a code-reviewed allowlist and test update; credentials or
tactical identity must never be introduced as arguments.

## Run the local manager app

Run preflight first, then start the per-PC dashboard:

```powershell
python -m shadowbane_lab.cli manager app `
  'C:\path\to\client-manager.json' `
  --live
```

For the standard WonderBane VM, the supported logon installer generates the one-client manifest,
retains the Mesa text fix, starts the command listener, and opens this dashboard without requiring
an interactive terminal. See [VM setup](vm-setup.md#install-the-vm-control-center-at-logon).

`--live` is mandatory because reviewed dashboard actions can launch, tile, or request a graceful
close. Opening the app never starts a client automatically. The terminal prints a per-run URL
and normally opens it in the default browser; use `--no-browser` to print it only. The control
token lives in the URL fragment, is removed from the visible address after page load, is kept
only in page memory, and is required as a bearer token for every status or action request.

The server binds only to IPv4 loopback (`127.0.0.1`), does not enable CORS, rejects unreviewed
routes and request shapes, caps action bodies, bounds concurrent request workers, enforces short
header/body deadlines, suppresses request logging, and sends restrictive CSP, frame, cache,
content-type, and referrer headers. It is intentionally not a cross-PC control plane. Run one app
on each PC.

The dashboard shows manifest slots, exact bindings, and unbound matching instances. If clients
are already open after a manager restart, attach each exact instance to a slot before launching
more. Group start is sequential and fail-fast, and it refuses to run while an unbound matching
instance or incomplete matching identity needs review. This prevents a later launch from being
silently assigned to the wrong logical slot.

Available controls are start one/all, refresh, tile one/all, exact attach, pause/resume dispatch,
detach, and graceful close. Start-all and close require browser confirmation. Closing the
dashboard with Ctrl+C stops only the manager UI; game clients remain open. If a remembered
binding is absent from the current window inventory, native window actions remain disabled while
Detach stays available so the operator can deliberately forget the stale identity and attach a
replacement.

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
launch root's PID and creation time are retained as a provenance anchor: automatic attachment
requires the game process to be that exact lifetime or a verified live descendant. A graceful
close is complete only after the exact bound PID/creation-time lifetime is verified exited;
window disappearance, enumeration failure, or process-query failure retains the binding with
dispatch disabled.

## Next manager boundary

The next manager slice is worker supervision and operational health: bind one bot worker to each
exact session slot, surface heartbeat/evidence/emergency-stop state, and gate dispatch through the
session's verified `dispatch_enabled` result. A later read-only overview may aggregate status from
several PCs, but live squad behavior and the designated bot caller must not depend on that
overview or on a central tactical service.
