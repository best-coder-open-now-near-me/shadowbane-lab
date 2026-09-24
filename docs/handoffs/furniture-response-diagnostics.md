# Furniture request and response diagnostics

## Purpose and delivery

The selected Bench drag refreshes the furniture window and retains its deed, but
leaves both placed-scene collections empty. "Done Loading" marks a refresh, not
placement success. A missing response record and client asset-creation failure
can produce that same result. See the
[discovery review](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/36).

`codex/furniture-response-diagnostics` targets `main` and provides the next passive
evidence boundary in [draft PR #37](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/37).
Native version 1.8.28 and host 0.3.48 passed complete package validation at source
`c764e22d1bd94fe3a84fd53a31d42d4c959d8a20`. The combined preview/recorder
1.8.30 / 0.3.50 corrected candidate is now installed; corrected live preview
acceptance remains pending.
See the combined package and deployment record below.
The independent real-time preview remains in
[draft PR #35](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/35).

## Reviewed boundaries

Only prepared client 1.3.38.11 SHA-256
`7f283cdbeb691d65ef3073d32e4ea7bc0cfcb31e1bb205e460573f23d0a7758f`
is admitted, together with the reviewed loaded-image checks and original vtable
slots. Furniture message table RVA `0x115be38` has destructor slot +4
(`0x1fcb7`), processor +0x14 (`0xeb4c`), decoder +0x1c (`0x27791`) and serializer
+0x20 (`0x1942a`). Decoder return `0x3625bc` and active socket identity qualify
incoming decoding. Shared writer return `0x362919` qualifies only serialization.
**Serialization is not proof of transmission, server acceptance or placement.**

The observer conditionally replaces those data slots, calls each original through
an immutable retained pointer, and preserves results, errors and native exception
behavior. It adds no placement command and modifies no message contents. Code and
call-through remain process-pinned for callbacks already in flight. Startup failure
rolls back partial installation; stopping clears publication and lineage tickets.
The optional recorder cannot disable an otherwise working client.

## Copied evidence

Operation 2 responses and operation 3 placement serialization are in scope;
other operations pass through without being treated as malformed responses.
Each event includes process creation identity, monotonic sequence/time, thread,
stage, native caller and available scene epoch/local actor identity. Decode tickets
link processing only to matching complete copied fields in the same current scene;
destructor, decode replacement, stop and lost lifetime invalidate that lineage.

Both operations contain building/context keys and two pointer vectors whose exact
record class is ArcFurnitureInfo (`0x117b364`). Copied rows contain all three keys,
XYZ, rotation, floor, raw +0x34 word and raw +0x38 byte. The second vector is
serialized by the client even though this furniture UI handler does not consume
it. Operation 2 additionally has raw refresh byte and consumed-deed keys;
operation 3 has the deed key, requested position, rotation and floor.

Each vector is bounded to 64 copied elements. Reported counts and separate
truncation flags retain the distinction between empty and truncated. Invalid
vectors, wrong record types and nonfinite coordinates are rejected. No native
pointer is published. Returned events retain pre-processing copies because the
native handler consumes scene records. None of these stages certifies placement.

Schema 1 uses mapping `Local\ShadowbaneLab.Extension.Furniture.v1.<pid>.<creation>`:
64-byte storage header, 32 records of 7,832 bytes, total 250,688 bytes. Each record
has a 56-byte event header and 7,776-byte payload: 96-byte payload header, two
64-row arrays of 56-byte records, then 64 two-word consumed-deed keys. Unused and
reserved fields are zero. The host validates identity, canonical fields, stable
publication, sequence gaps, ticket drops, malformed captures and closure. Any
truncation or evidence loss is explicitly incomplete; no automatic replay occurs.

## Source checkpoint validation

The full-profile DLL and native recorder harness compile under the reviewed Win32
MSVC toolchain. Five focused native cases pass, including all four partial-install
rollback points. The harness exercises malformed and truncated data, both record
vectors, native ABI/error/result/exception forwarding, process mutation after
capture, lost lineage, shared-memory reading and stop with callbacks in flight.
Independent read-only review matched the layouts and callbacks to the executable.

Host validation passes 147 focused furniture/workflow/Condemn tests and 193
package-gate tests. Repository Ruff and whitespace checks pass. Both build profiles
must include this observer exactly once, exclude its test harness, and execute all
five native tests before packaging.

The exact-source package `artifacts/f28/dd4fb06e/navigation-inspector-acceptance.zip`
passed all required gates (`acceptance_eligible: true`, no known failed gates).
Its SHA-256 is `01833840aafaf05c5f757dda8e98108f41650ffb6153b634ca67f2bf4a7b7784`.
Full-profile DLL SHA-256:
`a9310b43ef5b911385f2147328266418e92cd1a52382b54e5a4292ba80442a95`.
Host wheel SHA-256:
`f7f01e9b2b9c9b0a51ff924102f375fb6e6cf71191f728e56ac5e869bc46a9be`.
The receipt and logs remain in that private artifact directory.

Full host validation: 3,508 passed, 19 skipped. The additional environment skip is
`test_replay_does_not_publish_and_return_live_rebinds_controls` because Tk reported
no display. Each native profile passed 174 executed tests; three private-image
probes skipped in the generic suite were separately checked against the reviewed
client. Each profile also passed all 63 required movement IPC tests without skips.
Actual client binding checks, wheel installation and installed entry points passed.
Both profiles reproduced the two already documented transparency diagnostic
failures; existing package policy retains these deferred findings. They do not
establish complete graphics acceptance. Installation and live acceptance remain
separate gates. Earlier failed package attempts are superseded by `dd4fb06e`.

## VM preparation

At 2026-09-24 13:58 UTC, the exact package was staged alongside the current host.
Guest preparation returned `prepared_not_applied`; read-only validation returned
`update_verified_not_applied`, verified 431 installed module files and inventoried
9,424 retained files. The prepared executable and active game remain unchanged.
Private receipts are retained under the VM diagnostics share in
`furniture-response-20260924/guest-prepare.json` and `guest-validation.json`.
Applying the DLL, activating the new host and verifying shortcuts still require
normal game closure. The user can continue other activities with Bart meanwhile.

## Preview package coordination

The combined native 1.8.29 / host 0.3.49 candidate is published in
[draft PR #35](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/35)
from exact package source `0193dd74662eb368c4961a2ab8d9db6826fb70b4` on
`codex/furnishing-preview`. Its ancestry includes recorder source `c764e22`; the
native recorder and host reader remain unchanged. Workflow capture additionally
supports `--furnishings` for read-only selection/model observations.

The package reports all required gates passed: 3,811 host tests (18 skipped),
198 native tests and 63 movement IPC tests in each profile, actual client binding
checks and installed-wheel checks. The same two deferred transparency findings
remain recorded for each profile. ZIP SHA-256:
`9ca0fe2e669677f83335a3f6ba8b62c5af270b2e23bc9fbe23d24936b68e67e4`.
Full DLL SHA-256:
`33cdf5f8bf656766ad944a1bc06ad76b60ebcb5b8cd4728cabebf7fdc9163365`.
Wheel SHA-256:
`07c74cc5ec944f996f5255df80d618d2707b7067ff5c4ba58c3c169fc0732010`.
The final package and receipt are retained privately in the preview worktree at
`artifacts/p29/fc7b8466`. These checks qualify a live-test candidate, not visual
acceptance.

At 2026-09-24 15:52 UTC, combined VM preparation returned
`prepared_not_applied` and `update_verified_not_applied`. It verified 434 installed
module files and inventoried 9,426 retained files. All 61 package artifacts, ZIP
integrity, internal source/version identities and unchanged prepared-executable
bytes were independently verified before staging. Private receipts are in the
VM diagnostics share under `furnishing-preview-20260924/guest-prepare.json` and
`guest-validation.json`; the new guest upgrade directory is
`upgrades/furnishing-preview-1.8.29`.

After the user confirmed normal game closure, combined 1.8.29 / 0.3.49 was
installed and activated from exact source `0193dd7`. It supersedes the staged,
never-activated recorder-only 1.8.28 / 0.3.48 candidate. The prepared executable
remains unchanged; only the DLL entry changed in the client inventory. Five
runtime files have verified rollback backups in the combined upgrade directory.
All 9,426 retained files matched through application; manager activation then
changed only the expected revoked, unbound `dispatch.permit` (9,425 unchanged).
Crafting journals and saved settings were preserved.

All five existing desktop shortcuts and the non-launching launcher preflight
passed. Manager PID 9408 / parent 9256 was verified against the actual
`host-0.3.49/Scripts/python.exe`; its API was healthy, unbound, with no slots and
no running game. The initial immediate shutdown check preceded process exit;
a fresh read confirmed the old manager and port absent before application.
Private deployment receipts are retained under the VM diagnostics share in
`furnishing-preview-20260924/guest-*.json`. The user was directed to launch the
existing **WonderBane Vendor Test** shortcut, log in as Bart and wait for recorder
arming before any preview or placement action. Live process/mapping verification
and visual acceptance are still pending.
PR #35 documentation head is `d70da4ce298d91f251ceb70b2e8bbd4b017ea7ef`;
the packaged runtime remains `0193dd7`. Its ancestry includes PR #37 through
`5beb192`, but later staging/coordination docs from this branch must be preserved
when integrating the two reviews into `main`.

Use the existing Vendor Test shortcut and log in as
Bart with the Bench contract retained. Arm `--furniture-responses --furnishings`
before live testing. In the occupied building, select the loaded Bench in
Furniture Placement, choose Preview, move over the floor plan, click to hold,
rotate, and Cancel or Esc. Verify appearance, texture, scale, height, cancellation
and absence of placement serialization. Only after cancelling the preview should
the user make one ordinary placement attempt for the original carpenter issue.
The native preview currently admits only qualified preloaded static mesh /
ColorTexture / ArcImage trees and uniform positive building scale; unsupported
resources show unavailable. Preview does not establish valid placement or server
acceptance. The preview task retains its detailed runtime/live-acceptance handoff.

## First live evidence - September 24

The user launched the combined candidate as Bart. Exact process lifetime
`7708 / 134347448189563515` matched the reviewed prepared executable. The launcher
receipt and 32-bit module enumeration confirmed native 1.8.29.0 and the qualified
DLL hash. The first 64-bit module query saw only WOW64 loader modules; it was not
evidence that the extension was absent. The exact-process graphics receipt also
reports an active full renderer.

Continuous read-only capture started at 17:37:19 UTC for 30 minutes at 100 ms,
with `--furniture-responses --furnishings`. It was healthy with no gaps, rejected
snapshots or lost tickets. This finite capture must be rechecked before a later
live test; it does not automatically follow a replacement process.

Retained history includes a normal Bench drag, explicitly confirmed by the user.
Operation 3 serialized the Bench deed/building, finite requested coordinates and
floor zero. Operation 2 decoded 47 ms later and processed/returned 93 ms after
serialization. Its primary scene vector is empty, and the complete payload is
identical to the pre-drag response. Its secondary/consumed key describes a
different already-present item. For this reproduction there was no returned
primary Bench record for the client to instantiate; failure during creation of a
returned Bench model cannot explain that empty response. Serialization and timing
do not prove server receipt, acceptance/rejection or persistence. Recorder
`status_raw = 0` is not a server success code.

The outgoing zero structure field matches the original client's constructor and
normal drop handler; do not alter it speculatively. No server Furniture handler
was found in this repository. A server investigation needs its operation-3 parser/
handler and operation-2 response builder or logs, including deed resolution,
validation outcome and the primary/secondary/consumed lists it emitted.

Preview acceptance separately exposed a missing controls bar: the user correctly
single-clicked the Bench, the read-only selection shows it selected, and the HUD
matches the building occupied by the actor at floor zero. No preview appearance
or input acceptance is claimed. The preview task is investigating native
admission/presentation; more dragging is unnecessary. Private source evidence is
under `carpenter-investigation/preview-1.8.29/7708-134347448189563515` in the guest
and the host diagnostics share's `furnishing-preview-20260924/live-*` files.

## Confirmed preview startup defect

The missing bar is a startup collision, not an incorrect user selection. Exact
live DLL globals show an allocated preview runtime, renderer-ready true, but no
preview push/pop slots or owner/renderer/context callbacks installed. The game's
matrix imports point to the existing renderer's wrappers (DLL RVAs `0x41b00` and
`0x41a40`), while preview startup requires the raw OpenGL targets. The renderer
starts first, so that requirement rejects the normal production startup path.
No preview child window exists. A separate read-only comparison of the native
selection gates passed all observable conditions and reverse-validated 122
memory blocks. The exact package objects were relinked privately to recover
symbol addresses; the reconstructed DLL hash matched the installed DLL exactly.

The preview task owns the fix: the existing renderer remains the sole matrix
import owner and publishes bounded events to preview, preserving native
forwarding, display-list behavior, exact main-drain identity, stop/context and
in-flight cleanup. Native 1.8.30 / host 0.3.50 are reserved for its corrected
combined package. Regression coverage must run renderer-first startup; the old
isolated runtime fixture used raw imports and did not expose this collision.
No corrected source or package is claimed by this evidence checkpoint.

The passive capture was explicitly stopped at 17:48:25 UTC after 5,450 samples;
its 17 furniture events include the two normal-drag serialization observations
at sequences 4 and 14, with no gaps, overwrites, rejected snapshots or lost tickets.
Final private evidence is retained as `live-workflow-copy.jsonl`,
`live-preview-globals.json`, `live-selection-gates.json` and
`live-child-windows.json` in the diagnostics share. The user can use Bart normally
while the corrected package is developed. Re-arm capture against a fresh verified
process before the next live test; the current recorder is no longer running.

## Corrected startup candidate - 1.8.30 / 0.3.50

The qualified corrected combined package is built from exact pushed source
`8ba181868fca7ca113f94361b61118ce74a9d4a1` on `codex/furnishing-preview`
([PR #35](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/35)).
The renderer now remains the sole persistent matrix-import owner and publishes
bounded preview events after the original GL call. Preview no longer tries to
replace imports already owned by the renderer. Tests execute renderer-first
startup and actual wrappers, including in-flight Stop/re-enable, foreign hooks/
callers, display lists and context loss.

Exact private package root is the preview worktree's `artifacts/p30/b8690f3e`.
ZIP SHA-256: `befcb3d987d91fa8979e4a1217aa889fd950636315c8a84c0d24f25f85e94136`.
Full DLL SHA-256: `3d8680c50eb708061027863620381702a8a0d2461ebedce9dfcc2a87cacd6817`.
Wheel SHA-256: `c6ceeb9661907c61c4a6803389e8d7dd609f51fd04751be37061d966cb7d36c3`.
All 61 recorded artifacts, ZIP integrity/hash, internal wheel identity and native
version were independently checked. The seven reviewed bootstrap writes reproduce
the same prepared executable bytes. Rejected package attempts are excluded.

Required validation passes: 3,823 host tests (18 skipped), 200 native cases in
each profile plus separately verified private-image probes, all 63 movement IPC
tests per profile, and installed-wheel/panel/contract checks. The two pre-existing
transparency stretch findings remain separately recorded per profile. Corrected
live preview acceptance is not established by these checks.

At 18:11 UTC, VM preparation returned `prepared_not_applied` and read-only
validation returned `update_verified_not_applied`: 434 installed modules verified,
9,426 retained files inventoried, executable and active game unchanged. Private
receipts are in the diagnostics share under `furnishing-preview-fix-20260924/
guest-prepare.json` and `guest-validation.json`.

The user closed the game window, but the exact old process remained alive with
no HWND. After explicit authorization, only that lifetime was stopped. The
updater then installed and verified source `8ba1818`, native 1.8.30 / host 0.3.50.
The executable remains unchanged and only the DLL inventory entry changed.
All 9,426 retained files matched through application; manager activation refreshed
only its expected revoked/unbound dispatch permit (9,425 unchanged). Five runtime
files are backed up under `upgrades/furnishing-preview-1.8.30/rollback`.

All five existing shortcuts and non-launching preflight passed. Actual manager
PID 9132 / parent 6628 uses `host-0.3.50/Scripts/python.exe`; its API is healthy,
unbound, with no slots. No game was running at verification. Private activation
receipts are retained under the same corrected diagnostics-share directory.
The user was directed to open Vendor Test and log in as Bart, holding furniture
actions until startup registration and panel creation are checked read-only.
Corrected live acceptance and normal process exit still need verification.

The separate update was prepared from the prior installed source `0193dd7`
(native 1.8.29 / host 0.3.49), with new private helpers and payload under
`artifacts/furnishing-preview-fix-20260924`. Earlier payloads remain intact.
Plan SHA-256: `f068a0c0a658a545a553e43c24cb33127baaa163f91f1d354eab72ea7a9897a4`.
The next live check will inspect qualified corrected-DLL registration and panel
creation before asking the user to repeat selection/preview actions. The corrected
symbol manifest is retained privately; all inspections remain read-only.

## Capture and next todos

Use the existing workflow recorder with `--furniture-responses`, pinned to the
fresh exact process ID and creation time. This option is off by default. Retained
history is labeled separately from newly drained events. Start capture before a
supervised normal Bench placement and retain the read-only HUD before/after
observations alongside it. Do not infer success from a returned handler or generic
loading text. Private captures and client binaries stay in local artifact storage.

1. Complete: exact committed package, full host/native validation in both profiles
   and installed-wheel checks.
2. Complete: combined candidate installed after normal game closure; backups,
   retained files, shortcuts, launcher preflight and actual new manager verified.
3. Complete: fresh client and recorder verified; normal placement response and
   the missing-preview-controls startup cause captured without input automation.
4. Active: after launch/login, verify actual corrected startup registration and
   panel creation, then conduct fresh preview acceptance with passive capture.
   Corrected installation and manager/launcher checks are complete.
5. Obtain the server Furniture handler/response-builder evidence for the ordinary
   placement finding; resume guard/Condemn and vendor live checks in the serialized
   client queue. The private developer finding is prepared, not sent.
