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
1.8.29 / 0.3.49 candidate is now installed; live capture remains pending.
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
3. Active: after the user's launch/login, verify the fresh process lifetime and
   mapping, arm capture and conduct preview acceptance followed by one separate
   ordinary placement attempt. Separate outgoing serialization, incoming records
   and resulting HUD collections; fix the proven client boundary or provide the
   dev a precise server finding.
4. Resume serialized guard/Condemn and vendor live checks when carpenter testing
   releases the client. Preview live findings remain coordinated with its task.
