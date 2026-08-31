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

For the standard WonderBane VM, the supported logon installer generates the local manifest,
retains the Mesa text fix, starts the command listener, and opens this dashboard without requiring
an interactive terminal. See [VM setup](vm-setup.md#install-the-vm-control-center-at-logon).

The dashboard presents running instances rather than exposing its internal slot capacity. Use
**Add client** to launch another instance; the manager expands its hidden capacity transactionally
when no free internal slot remains. The reviewed configurator remains available for an explicit
offline capacity/layout change:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\configure-wonderbane-client-count.ps1 `
  -ClientCount 4 `
  -Restart
```

This only expands; it never silently deletes slots. Existing launch/process configuration is
preserved, new slots clone the first reviewed launch configuration, all slots receive unique grid
tiles, and the original JSON is retained beside the manifest as a timestamped backup. Re-running
the VM installer preserves the existing manifest unless `-ClientCount` is explicitly supplied.

When an immutable reviewed client build replaces the launch directory, retarget every existing
slot atomically instead of editing JSON or copying binaries over the installed client. With every
game client closed, verify the published package immediately before retargeting it:

```powershell
$env:PYTHONPATH = "\\VBOXSVR\codexrepo\src"
& "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe" `
  -m shadowbane_lab.client_extension verify-copy `
  "\\VBOXSVR\codexdiag\client-extension-working\wonderbane-1.0.5-world-map-click-v1" `
  --pretty

& "$env:USERPROFILE\shadowbane-lab\.venv\Scripts\python.exe" `
  -m shadowbane_lab.cli manager configure-build `
  "$env:LOCALAPPDATA\ShadowbaneLab\client-manager.json" `
  "\\VBOXSVR\codexdiag\client-extension-working\wonderbane-1.0.5-world-map-click-v1" `
  --apply --json
```

The command verifies `sb.exe` before replacing the manifest, preserves slot IDs, tiles, launch
arguments, and reviewed renderer environment, and writes a timestamped backup. Restart the control
center afterward so both the dashboard and node listener load the new immutable configuration.

`--live` is mandatory because reviewed dashboard actions can launch, tile, or request a graceful
close. Opening the app never starts a client automatically. The standard VM runner binds the
dashboard to fixed loopback port `52739` and keeps one random 256-bit token in
`%LOCALAPPDATA%\ShadowbaneLab\dashboard.token`. The token is inherited from the current user's
local profile rather than exposed as a process argument. It enters the browser in the URL
fragment, is removed from the visible address after page load, remains only in page memory there,
and is required as a bearer token for every status or action request.

The stable loopback origin and token let an already-open dashboard reconnect after a guarded
manager restart. While the listener is absent, the page visibly disables every operation and
continues read-only status polling; controls return only after the current manager answers. Running
the standard control-center launcher while its exact manager is already alive opens another
authenticated view of that same runtime. `--no-browser` suppresses browser launch.

The server binds only to IPv4 loopback (`127.0.0.1`), does not enable CORS, rejects unreviewed
routes and request shapes, caps action bodies, bounds concurrent request workers, enforces short
header/body deadlines, suppresses request logging, and sends restrictive CSP, frame, cache,
content-type, and referrer headers. It is intentionally not a cross-PC control plane. Run one app
on each PC.

The same `/api/v1/status` response includes an `extension` record for every slot. It resolves only
the heartbeat whose PID and process-creation FILETIME match the current exact client binding;
heartbeats from earlier launches are ignored. `initialized` is the only ready state. Missing,
malformed, mismatched, unbound, and unconfigured states remain explicit and do not become native
capability authority.

The dashboard shows open instances, exact bindings, and worker health. It refreshes health every
two seconds while visible, adopts safely identified clients that were already open, and archives
their internal bindings after exact process exit is verified.

Available visible controls are Add client, refresh, pause/resume dispatch, and graceful close.
The legacy native tiling operation remains an internal manager primitive, but it is intentionally
not exposed in the dashboard: Shadowbane keeps its launch-time render surface when Win32 resizes
the outer window, which clips the game instead of scaling it. A future multibox display feature
must choose a compatible per-client `-resolution` before launch and handle restarts explicitly.
Close requires browser confirmation. Closing the
dashboard with Ctrl+C stops only the manager UI; game clients remain open. If a remembered
binding is absent from the current window inventory, native window actions remain disabled while
Detach stays available so the operator can deliberately forget the stale identity and attach a
replacement.

## Per-slot worker supervision

The app reads durable worker heartbeats from the node-local control-center state root by default.
This remains local even if an operator temporarily reads the manager manifest from a VirtualBox
share:

```text
%LOCALAPPDATA%\ShadowbaneLab\workers\<node_id>\<client_id>\
├── worker-<id>.json
├── dispatch.permit
└── stop.worker-<id>
```

Use `manager app --worker-state-directory ABSOLUTE_LOCAL_PATH` only when a different node-local
state root is intentional. UNC roots are rejected. The heartbeat directory is local operational
state; it is not a shared tactical bus and should not be placed on `codexrepo` or `codexdiag`.

Start, attach, and resume now ensure one exact worker runtime exists for the bound slot. The
manager launches that runtime directly with separate argument tokens and local stdout/stderr logs;
it does not use a shell. The worker independently re-enumerates the configured client and keeps
publishing only while the assigned PID, process creation time, HWND, and derived `instance_id`
remain the same. Losing or replacing any part of that identity latches emergency stop and exits.

Each runtime creates a fresh `WorkerHeartbeatPublisher` for one manifest `client_id`, one exact
manager `instance_id`, and its own verified PID/creation-time lifetime. It publishes once per
second while active; the manager's default expiry is five seconds. The permanent worker boundary
has this shape:

```python
import os
from pathlib import Path

from shadowbane_lab.manager import (
    ProcessLifetimeSnapshot,
    Win32ProcessLifetimeInspector,
    WorkerHeartbeatLedger,
    WorkerHeartbeatPublisher,
    WorkerRuntimeState,
    load_manager_manifest,
)

manifest = load_manager_manifest(manifest_path)
inspector = Win32ProcessLifetimeInspector()
process = inspector.inspect(os.getpid())
if not isinstance(process, ProcessLifetimeSnapshot):
    raise RuntimeError("worker process lifetime could not be verified")

publisher = WorkerHeartbeatPublisher(
    WorkerHeartbeatLedger(
        manifest,
        Path(os.environ["LOCALAPPDATA"]) / "ShadowbaneLab" / "workers",
    ),
    node_id=manifest.node_id,
    client_id=client_id,
    instance_id=instance_id,
    process=process,
)
publisher.publish(WorkerRuntimeState.STARTING)
# Publish RUNNING with dispatch_ready=True only after all worker guards are ready.
dispatch_gate = publisher.dispatch_gate()
# Pass dispatch_gate into the live input stop-signal chain and check it before every action.
```

The shipped exact worker host performs this setup automatically. A healthy host means the exact
identity, heartbeat, and guarded-dispatch boundary are ready; it does not mean a travel or combat
strategy is actively emitting input. Strategy services are composed behind this host and must use
its dispatch gate before every live action.

The publisher sequences atomic records and latches emergency stop for the lifetime of that worker.
After an emergency trip, the same worker identity cannot re-enable dispatch; create a new worker
process after operator review. `evidence_sequence` is an optional non-negative cursor for liveness
diagnostics, not a path or tactical payload. Call `publisher.close()` on orderly shutdown.

Effective `dispatch_enabled` is deliberately stricter than client attachment. It is true only when
the exact game process/window binding is current, lifecycle dispatch is resumed, exactly one fresh
worker owns that exact instance, the worker PID/creation time is still live, its runtime is healthy,
and its own guarded dispatch is ready. Missing, stale, corrupt, duplicated, mismatched, stopped,
failed, degraded, or emergency-tripped workers all fail closed and remain visible in the dashboard.
`lifecycle_dispatch_enabled` remains separately visible so an operator can distinguish a manual
pause from a worker-health block.

The manager continuously writes an atomic `dispatch.permit` beside each slot's heartbeat records.
An allow permit names the exact game instance, worker ID, worker PID/creation time, and last verified
heartbeat, and expires after two seconds. `pause`, `detach`, `close`, a new launch/attach, and orderly
manager shutdown write a denial synchronously; a crashed or unreachable manager simply stops
renewing the allow permit. `publisher.dispatch_gate()` implements the live input `StopSignal`
contract and must be included in every worker's guarded-input stop chain. Treating the dashboard
field as informational without consuming this permit is not a valid worker integration.

Pause keeps the exact worker alive but synchronously denies dispatch. Detach and graceful close
both deny dispatch and write an exact stop request naming the worker ID plus its PID/creation-time
lifetime. A request for another worker or a reused PID is ignored and fails closed. Reattaching the
same live client reuses its healthy worker; replacing the bound client stops the old worker before
launching the new exact host.

The existing `/go` and `/pve` chat listener is a node-level guarded operator service, not a per-slot
worker. It keeps separate singleton ownership because physical chat input belongs to whichever game
window is foreground. It must not be duplicated once per client. The listener also owns one
renewable extension-event consumer lease per visible exact client lifetime. A current world-map
destination event is converted into deterministic stop and travel operations for that event's PID,
process-creation FILETIME, and HWND even if focus changes after capture. Reused PIDs, rebound HWNDs,
stale events, unavailable workers, and competing consumers fail closed; an event is acknowledged
only after its immutable operations are accepted by the node-local ledger. Operation state and the
worker receipt remain visible through the same `/api/v1/status` response as chat-originated work.

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

The next manager slice is the local operation channel between the node-level `/go` and `/pve`
listener and the exact per-client worker host. Commands must carry the foreground client's immutable
identity, expire quickly, deduplicate, and receive bounded acknowledgement; the worker then runs the
existing travel or PvE engine with its manager dispatch gate in every live-input stop chain. A later
read-only overview may aggregate status from several PCs, but live squad behavior and the designated
bot caller must not depend on that overview or on a central tactical service.
