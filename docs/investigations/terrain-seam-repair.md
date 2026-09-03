# Stock terrain seam repair investigation

Latest checkpoint: resident-alpha capture succeeded (see final section). Six
source masks retained; four archive-backed masks match the archive exactly.
No visual seam fix is claimed. Next: attribute the visible boundary to mask
coordinates and final layer composition, using the saved evidence first.

## Request and current outcome — 2026-09-03

The user reports that the visible tile seams remain a stock terrain issue, not
an added-outline regression. They authorized implementing the seam fix and
judging its appearance afterward, explicitly skipping another live capture.

This checkpoint is **investigation, not a visual repair**. No renderer, cache,
client configuration, or VM setting was modified. Do not publish the current
build as a seam-blending fix. Existing body outlines and the 1.6.11 transparency
fix remain unchanged.

Source examined: `codex/client-convergence-v2@875f839`, including the unchanged
1.6.11 renderer from `a1f8a77`. The inspected frozen vanilla executable has
SHA-256 `55fbad5f0110cd99b4085af72d1e8fddb782ccdec1491478492c18158f5c61bc`.

## Completed offline evidence

The integrated terrain audit ran against the preserved baseline's
`TerrainAlpha.cache` and `CZone.cache`, without modifying either archive.
Source hashes are recorded in the locally retained report. No new VM capture
or remote upload was performed.

- 105 complete maps, 20,912 tiles.
- 39,000 neighboring borders and 18,193 four-tile junctions.
- 861 zone templates scanned; 707 complete map references.
- The largest reported border p95 is 255; the largest diagnostic score is 483.
  Neither number is a visual-defect classification.
- The report lists seven height-role maps and 99 material-role maps. These
  counts overlap: map `3953:34` has both roles across its template uses.
- All 105 per-map detail files were generated; heatmap generation was disabled.

The local report SHA-256 is
`8498ac9d622b9ddc06289a32c50bc3ad1bc60ce0b3f6cdafad828d89fc1a4e5c`.
Reports and client data are local artifacts, not repository content.

## Why the audit cannot authorize a cache repair

The audit assigns `height` to the first complete referenced map and `material`
to subsequent maps. This is reference-order evidence, not a render-use proof.
The real decoded metadata supplies a concrete counterexample to treating every
`material` map as a purely visual blend weight:

- Tainted Swamp template `0:3033` declares image terrain (type 7).
- Its height map is `13936588:1`.
- Its first subsequent map is `1173:214`, layer 1.
- The decoded object-population metadata also selects layer 1, and the existing
  navigation loader uses it as object-density evidence.

Separately, City of Trilius template `0:553` uses `3953:34` as height, while the
audit finds that same map in subsequent-layer positions in other templates.
Global map mutation cannot be scoped safely from the word `material` alone.

Border differences can also be the expected interval between adjacent samples,
not duplicated samples that should have equal values. A height delta, gradient
delta, or high corner score does not establish the client's stitching convention
or attribute the user's visible seam.

## Static renderer findings

The frozen client already requests edge clamping for non-repeating textures:

- VA `0x00591073` onward selects `0x812f` for S/T/R texture wrapping.
- The alternate float-parameter path at VA `0x0059247e` selects the corresponding
  float representation of `0x812f` for S/T.
- Repeating textures retain the separate `0x2901` path.

These are static call-site observations, not proof of the affected texture's
live state. A blanket replacement of legacy clamp with edge clamp is not a
supported repair: the inspected paths already use edge clamp.

RTTI/vtable tracing located `ArcShaderCustomTexturedTerrain` and its setup/draw
methods (preferred-image VAs `0x008f14f0`, `0x008f1660`, `0x008f1950`). The draw
method sets up multiple texture units and per-tile mask transforms. The terrain
image builder was also located at VA `0x00954750`. These are candidates for
further review, **not approved hooks or newly trusted runtime mappings**.

The reviewed restrained-cel texture package replaces only resources `0:1706002`
and `0:5000190` (beast and wreck). It does not replace the terrain atlas or
TerrainAlpha maps. The saved all-live-effects-off screenshot remains useful as
appearance evidence, but does not identify the seam's terrain draw or texture.

## Remaining work / delivery gate

1. COMPLETE: offline whole-archive audit and static sampler/terrain-path review.
2. ACTIVE: establish reviewed terrain draw-to-texture ownership for the affected
   path. Existing saved graphics status does not supply this attribution. A
   narrowly bounded observer and a runtime evidence sample would close that gap;
   a new capture was not authorized in this request and was not performed.
3. Select and implement the visual repair from that evidence, preserving height,
   population, collision, other materials, UI, and the transparency fixes.
4. Validate both native profiles, Python/package boundaries, fail-safe behavior,
   and frame cost; then produce a verified test package for the user's judgment.

No global blur, global wrap-mode override, inferred terrain mask, raster-border
averaging, height mutation, or visual-fix claim is part of this checkpoint.

Validation: terrain seam, world-data, and terrain-navigation tests: **29 passed**.
Native source is unchanged, so this checkpoint does not claim a new native build
or live visual/performance acceptance.

## Follow-up authorization and tracing checkpoint — 2026-09-03

The user subsequently approved the narrow prerequisite capture: one unattended
local terrain draw/texture trace on the testing VM, with no game input,
screenshots, or upload. This supersedes the earlier no-new-capture constraint for
that specific observer only. It does not authorize the previously blocked full
diagnostic export or GitHub push.

The native observer landed locally at `bf2a87d`. The 1.6.12 release adds a
PID/creation-time-bound local collector, idle/concurrency gate, and explicit
launch-only opt-in. See [the trace contract](../diagnostics/terrain-draw-trace.md)
for record limits, exact boundary ownership, state scope, and exclusions.
No seam blending is implemented or claimed.

Validation of the release source: 1,459 Python tests and 211 subtests passed;
seven environment/privilege-related tests skipped; Ruff passed. Both full and
diagnostics-only native builds passed all 14 CTests, including observer-off,
unsafe-query, context/thread, missing-boundary, capacity/time/unit-limit,
active-unit restoration, and JSON tests.

Release DLL identities:

- Full: `39ee563be8e32353d60c6f9e3ebb801b8db1bffddb6dcb734fbd4f66b2285114`.
- Diagnostics-only: `e6a46c13f951e0e5b2f910be498c4bf99dd15e34a00888a33441631b6717cf2d`.

Sequence at the release checkpoint (superseded by the live result below):

1. COMPLETE: implement and validate the bounded observer and local collector.
2. ACTIVE: prepare the frozen 1.6.12 bundle, then publish/launch on testing after
   a normal client exit and fresh user handoff. The plain VM stays untouched.
3. Capture once after the user restores the affected view; inspect limitations
   before attributing terrain ownership. No live trace or VM acceptance yet.
4. Implement the evidence-supported seam repair and let the user judge it.

The working source and build artifacts are local; push remains held by the
earlier approval restriction. The old published 1.6.11 package is retained.

## Live attribution checkpoint — 2026-09-03

The frozen 1.6.12 package was published and launched on testing after normal
client exit. Preferences were backed up and restored; the plain VM and prior
packages remain untouched. One exact PID/creation-time-bound trace was captured
after the user positioned the view. The source trace remains guest-local; it was
not copied or uploaded. Subsequent user authorization allowed screen inspection.

The reviewed interval completed: 1,506 submissions observed, 1,505 retained,
303 unit/binding pairs. One unsafe submission was skipped and units 4–7 were
outside the four-unit observer. There were no capacity or query-budget skips.
The 3.5223 ms query total is observer accounting, not a frame-performance result.
All retained entries reported successful active-unit restoration.

Exact patched executable SHA-256:
`a9a59004b36f9331bb85f85e7853a02a5d5f07bda9acb9ea4a8affbf169a54b8`.
Within the statically identified terrain draw method, return RVAs `0x4f1772`
and `0x4f1864` attribute 25 base passes and 29 masked layer passes respectively.
They use the indexed-triangle submitter at RVA `0x1a0765`. The additive,
depth-write-disabled strip family was separately inspected and ruled out.

All 29 layer masks were enabled on texture unit 1, used edge clamping on both
axes, and used linear magnification. Their sampled matrices were identity.
Mask dimensions were 64×64 or 128×128, paired with 256×256 color textures.
The observed seam therefore does not justify a blanket wrap-mode override.

The user reported one disturbed water frame during collection and then confirmed
that it immediately cleared. Live-control sequence remained 2/2, with no rejected
updates or control errors. Record this as a transient observer concern; active-unit
restoration alone does not prove absence of all rendering disturbance. No second
capture was requested.

The repeatable, offline [terrain trace analyzer](../diagnostics/terrain-trace-analysis.md)
now packages the reviewed attribution and state grouping. It consumes saved data,
rejects unknown executable profiles and contradictory evidence, and never treats
context-local texture names as cache IDs or permission to alter resources.

Current remaining sequence:

1. COMPLETE: frozen package launch, settings preservation, and one local capture.
2. COMPLETE: identify the actual terrain pass family and its observed mask state.
3. ACTIVE: connect those terrain bindings to reviewed cache/archive records and
   determine the neighboring-mask sampling convention. Continue offline review
   first; the existing trace cannot supply resource tokens it did not record.
4. Implement the evidence-supported seam repair, validate the complete package
   and frame cost, then let the user judge its appearance.

No seam repair or visual acceptance is claimed yet. Working evidence and commits
remain local; the earlier push/export restriction remains in force.

The subsequent [offline ownership review](terrain-resource-ownership.md) located
the paired shader/source texture vectors and an RTTI-backed texture-to-GL-binding
path. Internal token-to-archive decoding and the live instances' exact resource
identities remain unverified. These findings are not new approved runtime offsets.

Analyzer checkpoint validation: **38 focused tests passed**, including collector
tests, plus Ruff and diff checks. Native source is unchanged; no new native build
or seam-fix performance/visual acceptance is claimed.

## Edge-refresh correction selected — 2026-09-03

Further offline review verified token serialization and located the client's
existing four-direction seam handling. It also found a narrower actionable
defect: successful matching-material edge copies bypass the GPU-mask dirty
flag, unlike the blend-ramp paths. See the exact control flow and proposed
single-byte branch corrections in [the ownership review](terrain-resource-ownership.md).
Some source masks are synthesized, so direct archive attribution is not a
universal prerequisite or a safe assumption.

The active sequence is updated accordingly:

1. COMPLETE: verify source/generated mask ownership, token order, and the
   existing neighboring-edge copy/refresh path offline.
2. ACTIVE: implement the whole-function-verified, full-renderer-only refresh
   correction; test drift rejection, restoration, and both native profiles.
3. Validate Python/package boundaries and prepare a separately verified test
   release. No new capture, VM changes, or upload are authorized by this step.
4. Test appearance and frame/streaming cost before claiming live acceptance;
   further visible seams may need separate attribution.

This selection does not assume that the four-byte correction fixes all terrain
seams. Archives, live VM state, and frozen release artifacts remain unchanged.

## Implementation checkpoint

The full renderer now installs the four single-byte corrections only after
verifying all seven complete routines (four directions, mask-copy producer,
dirty-gated consumer, and streaming-update caller). Fixed relocation lists
normalize ASLR before SHA-256 verification. Every guard passes before any byte
is changed. There is no signature search or inferred mapping fallback.

The new branch targets execute only the existing dirty store; directional
completion flags, blend ramps, material ordering, alpha data, and original
continuations are unchanged. The streaming caller at 0x008aca80 returns early
when its tracked coordinates/settings are unchanged. No observer or extra
per-frame GL work is added, but refresh/upload cost during streaming still
requires live measurement.

Changes are process-local, not executable/cache-file writes. Installation uses
single-byte compare/exchange, instruction-cache flush, and page-protection
restoration. Partial installation rolls back owned bytes. Restoration refuses
to overwrite an unrelated replacement and reports an incomplete rollback rather
than claiming stock state. Diagnostics-only compiles out installation/restoration.
Graphics status exposes terrain_mask_refresh independently of shading controls;
the correction follows renderer startup/shutdown, not the live effect toggles.

Both native profiles built and passed **16/16 CTests**. Additional read-only
integration checks against the frozen executable passed for full and disabled
repair variants: seven actual routine fingerprints, both relocation directions,
every-byte drift rejection, exact dirty-only branch targets, public startup/stop
on relocated copies, idempotence, and last-guard rejection before any writes.
Unit tests cover partial-install rollback at each site, unrelated-byte ownership,
rollback retry, inaccessible memory, and restored page permissions.

Current next item: release versioning and Python/package compatibility checks.
The source implementation is complete; no release publication, new capture,
live performance result, or visual acceptance is claimed.

## Versioned test release: 1.6.13

Release identity was updated to 1.6.13. A stale launcher pin was subsequently
caught and corrected during restart preflight (see below). Full DLL SHA-256:
01e4297798c3c2ca4212d997f0793b8a4af0bb98d429f31d9e07a9dc029f42a4.
Diagnostics-only SHA-256:
f51119f8584d482fe40d73c183f6ebacdeb75f962688e2d6200483a7e16e740c.
Both embed version 1.6.13.0. The ordinary bootstrap still produces the same
reviewed a9a59004 executable; terrain repair changes only the running full
renderer process, not the packaged executable's bytes.

Validation: **1,483 Python tests and 211 subtests passed**, seven skipped;
repository Ruff passed. Both versioned native profiles passed **16/16 CTests**.
The actual frozen-code integration passed in full and disabled test variants.
Saved 1.6.12 traces remain analyzable; 1.6.13 is also explicitly supported.
New live requests require the exact running version, not either version blindly.

The host-side package dry run correctly refused the baseline because its
recorded root is the guest UNC path. The baseline has not been rebound or
modified; that remaining package check must run in the guest.

Current todo state:

1. COMPLETE: reviewed edge-refresh implementation and rollback/isolation tests.
2. COMPLETE: 1.6.13 version/hash pins and complete source/native validation.
3. ACTIVE: freeze the local bundle and run the path-bound package dry run in
   testing, without closing the game or starting another diagnostic capture.
4. PENDING: preserve settings, normal client restart into the isolated package,
   and visual/streaming-cost acceptance. Keep old packages and the plain VM intact.

## Guest package check and restart handoff

Frozen source ed9aa5b and the full DLL were staged through a new read-only
testing-only share. The checker and payloads were SHA-256 verified locally
before execution. The package dry run then **passed** inside testing against
the baseline's unchanged original UNC root. No game package was published.

The old client's exact-lifetime live graphics settings were successfully saved
to a new guest-local JSON using read-only shared memory and stable repeated
reads. That settings file and the dry-run receipt remain guest-local. The old
game stays open, its controls unchanged; no new trace was requested. Local
operator handoff and verification screenshots are retained beside the frozen
bundle. No diagnostic export or push was performed.

Todo state: implementation, release validation, bundle freezing, guest dry run,
and live-settings backup are COMPLETE. The single ACTIVE item is normal
restart/publication into a new empty runtime parent, followed by restoring
preferences and visual/streaming-cost acceptance. Await normal user exit;
do not force-close or inject game input. The plain VM stays untouched.

## Restart preflight: launch pin corrected; installation stopped for space

After the user confirmed normal exit, a read-only guest process check found no
sb.exe. The saved client identity was PID 6420, creation FILETIME
134329234815817786, in the 1.6.12 runtime under
S:\ShadowbaneLab-Guided\20260903-1016421. Six allowed configuration files
(ArcanePref.cfg and character SCREEN_GAME profiles) were copied and individually
SHA-256 verified into a new guest-local backup; original files stayed untouched.

The preflight found that the launch script still required the 1.6.12 DLL hash,
despite its version having advanced to 1.6.13. The previous golden test asserted
that stale hash independently of the publisher. Commit 8f5bf8e corrects the pin
and adds a publisher-versus-launcher identity equality test. A complete rerun
passed **1,484 Python tests and 211 subtests**, seven skipped. Focused Ruff passed.
The native artifact is unchanged; its previous two 16/16 native results apply.

The corrected source archive (8f5bf8e) was frozen separately and hash-verified
before guest extraction. SHA-256:
c50d431a09d4d1f02e419835a89004269ba0c053e4181adf20937eaef5197915.
The original ed9aa5b bundle and receipts remain intact. The publisher repeated
its dry run and reused the matching receipt, then stopped at the free-space
check BEFORE prepare-copy: required 2,920,748,059 bytes; S: had 1,054,076,928.
C: also has only about 1.22 GiB free. No new game package or client was launched.

Read-only inventory found these older guided packages, each about 2.22 GiB:

- 1.6.10: S:\ShadowbaneLab-Guided\20260903-920ba0f\Wonderbane-graphics-wb-55fbad5f-4b602995-cel-1.6.10
- 1.6.11: S:\ShadowbaneLab-Guided\20260903-a1f8a77\Wonderbane-graphics-wb-55fbad5f-4b602995-cel-1.6.11
- 1.6.12: S:\ShadowbaneLab-Guided\20260903-1016421\Wonderbane-graphics-wb-55fbad5f-4b602995-cel-1.6.12

No old packages were deleted or moved. The new 20260903-ed9aa5b parent exists
but is empty. Guest-local source-8f5bf8e, preferences-backup.json,
closed-client-preferences, and install-1.6.13.log preserve the checkpoint.
The installer deliberately refuses a blind rerun because staging now exists.

ACTIVE todo: obtain space for the isolated installation. Proposed narrow cleanup
requires user authorization: preserve the 1.6.10 configuration, then remove only
that old test copy, keeping 1.6.11 and the current 1.6.12 fallback. Afterward,
resume from verified local staging, publish, launch, restore live controls, and
verify the four-site repair status. Visual and streaming-cost acceptance remain
pending. No new capture, diagnostic export, push, or plain-VM change occurred.

## Installed test checkpoint and disposable-build policy

Per user direction, generated VM test builds are disposable artifacts, not
rollback backups. Git history plus the frozen official client baseline are the
authoritative inputs for rebuilding an older renderer when continued diagnosis
requires it. Transfer the active user's reviewed configuration into a new test
build when needed, but do not retain whole client copies merely for rollback.

After an exact, read-only package preflight passed, the user explicitly approved
permanent removal—with no backups—of the four superseded testing builds: 1.6.8,
1.6.10, 1.6.11, and 1.6.12. Each target was proven to be a sealed disposable
WonderBane package, had matching recorded executable/extension hashes, contained
no reparse points or .git directory, and was resolved to its exact S: path before
removal. All four removals completed; a subsequent exact-path check found zero
remaining. S: free space increased to 7.65 GiB.

The 1.6.13 package was then published and verified at:
S:\ShadowbaneLab-Guided\20260903-ed9aa5b\Wonderbane-graphics-wb-55fbad5f-4b602995-cel-1.6.13.
It launched as PID 5240, creation FILETIME 134329293478567243. Saved graphics
parameters were applied only to that exact process and acknowledged at sequence
4. Final status reports terrain_mask_refresh=active with patched_sites=4. No
terrain trace or other diagnostic capture was requested. The plain VM and frozen
official baseline remain untouched.

ACTIVE todo: user login and visual evaluation at the selected terrain seams,
followed by a separate streaming-cost check if appearance is improved. The live
status proves the reviewed repair installed; it does not by itself prove every
visible seam is resolved.

## Live visual result: installed but no seam change

With the user positioned at the same obvious cobblestone/ground boundaries, the
visible seams were unchanged. A fresh read of the running process's own status
file at 2026-09-03T17:22:09.9166869Z confirmed PID 5240, version 1.6.13,
full-renderer, terrain_mask_refresh=active, reason=matched-edge-dirty-flag, and
patched_sites=4. Scene color and depth passes were also active; phase was ui.

Therefore this result is not a deployment/profile failure. The repair is
installed, but it is not sufficient to change the observed seams. The current
one-byte branch corrections deliberately have no execution counters, so this
status cannot distinguish (a) the visible seam never traversing those matched-
edge copy branches from (b) those branches running while the refreshed generated
mask is not the visual source of the boundary. Do not tune this correction based
on appearance. ACTIVE todo is now to attribute the visible boundary to its actual
terrain layer/material transition, or add narrowly scoped branch-hit evidence,
before proposing another renderer change. No new capture was taken for this check.

## One-shot branch evidence prepared

A bounded external collector now covers the four repaired completion
instructions. It requires the exact 1.6.13 executable, extension DLL, PID,
creation time, and repaired bytes before debugger attachment. Four hardware
execution breakpoints replace event-heavy tracing; only one observation per
role is retained. At each hit, the collector reads the already-reviewed
430-byte terrain source object from EBX and records only the three vector
bounds, base reference, direction-completion byte, and dirty byte. It performs
no process-memory writes, scans, pixel reads, texture reads, client calls, or
input injection. The diagnostic transport temporarily changes thread debug
registers and clears them before detach. On the testing VM, Windows accepted
attachment but returned access denied for the explicit detach call. A separate
read-only check after the debugger process exited confirmed that the exact game
process remained alive and no debugger was attached. The collector therefore
uses a short-lived worker and publishes its JSON only after a parent repeats
that post-exit lifetime/debugger/signature verification.

Focused tests cover exact-identity refusal, create-only JSON, bounded terrain
state, no-activity semantics, and legacy vendor-dialog tracer compatibility.
The complete Python gate passes with 1,488 tests, 211 subtests, and 7 skips.

ACTIVE todo: run one stationary 15-second capture at the preserved seam view.
If it records no hits, run one separately labeled movement capture across the
boundary. Use those results to decide between the repaired matching-material
path and an unreviewed layer/material-transition source.

## Branch attribution result: repaired path not observed

Both required captures completed against PID 5240, creation FILETIME
134329293478567243, while the same visible cobblestone/ground seams remained
on screen:

- Stationary, 15.016 seconds: zero hit events and zero unique branches.
  Original artifact SHA-256:
  bbbfecaa7dae30232645e7ecc8fceaac0bcdf10cd478254a78ed3bc1e3a40627.
- Forward boundary crossing, 15.047 seconds with three seconds of explicitly
  recorded operator keyboard input: zero hit events and zero unique branches.
  Original artifact SHA-256:
  b442999cdebc3b8cacd59b427c6624dfa16afab3f8b3203efa8591032dbb5f6a.

Both captures verified the exact executable and 1.6.13 extension. All four
repaired instructions matched before attachment, while attached, and after
the debugger worker exited. Debug-register clearing completed, the exact game
lifetime survived, and the parent found no debugger attached. Neither capture
performed client code/data writes, scans, pixel or texture reads, or unrecorded
input.

This rejects the repaired matching-material completion branches as the
observed path for these seams during both stationary rendering and a warm
crossing. It does not invalidate the stock lifecycle defect or prove a
cardinal direction name. Keep the minimal repair, but do not extend or tune it
to chase this image.

ACTIVE todo: trace the visible boundary through the terrain layer/material
composition path, beginning with the already reviewed source vectors,
ArcShaderCustomTexturedTerrain population, and masked-layer draw sequence.

## Rejected terrain material snapshot probe

A follow-up external debugger probe attempted to capture the terrain shader
source pointer at the reviewed draw entry. It was pinned to the exact running
1.6.13 client (PID 5240, creation FILETIME 134329293478567243), used bounded
reads, and was designed to publish only after post-detach verification. During
its first live run, however, the debugger worker reported that sb.exe exited.
A separate process check confirmed that the exact client was no longer running.
No final JSON result was published, so the partial observation is invalid.

The failed design assigned all four hardware execution breakpoints to the same
entry address in order to reuse the existing four-slot debugger transport. That
approach is rejected: regardless of whether duplicate breakpoint addresses were
the direct cause, a diagnostic that can terminate the test client is not an
acceptable evidence path. The command-line entry point, module, focused tests,
and operator documentation are removed in the following commit. Do not rerun
the frozen da14bad archive from the guest-local terrain-material-da14bad folder.

The exact sealed 1.6.13 client was subsequently relaunched through the frozen
8f5bf8e verifier and its matching guest-local publication receipt. It attached
the graphics panel as PID 2252. The retained draw trace and the minimal four-site
terrain lifecycle repair were not changed.

ACTIVE todo: continue material-boundary diagnosis without an external debugger.
Prefer an in-process, opt-in extension observation with a fixed per-frame budget,
or use a controlled renderer A/B that cannot mutate client memory or input. The
visible seam remains attributed to the masked terrain layer/material stack, not
to differing base texture bindings or base texture-matrix scale.

## Read-only polling replacement

The reviewed global `ArcShaderCustomTexturedTerrain` instance supplies a safer
ownership boundary than a draw-entry breakpoint. A new bounded poller reads that
global, its current owner/source, and the already reviewed texture vectors using
only `PROCESS_VM_READ` and query rights. Every accepted graph is stable across
repeated shader, owner, source, vector-entry, texture-object, and backing-object
reads. Concurrently changing samples are discarded rather than repaired or
guessed.

The poller keeps the exact executable, extension, repaired-instruction, draw-
entry, creation-time, and vtable gates. It does not attach a debugger, suspend a
thread, alter debug registers, call client methods, scan memory, read texture
bytes/pixels, or inject input. Output is create-only and capped at 20,000 polls
and 64 unique source graphs.

ACTIVE todo: validate the replacement locally, then run one five-second poll
while the user is at the visible seam. Correlate its GL bindings with the retained
draw trace before considering a renderer or cache change.

## Read-only material attribution at the visible seam

Replacement `9d1c1ac` passed 1,498 Python tests, 211 subtests, and Ruff (7 tests
skipped). A 0.1-second login-screen preflight recorded 26 idle polls and no
invented terrain. After the user logged in, a five-second in-world poll completed
against PID 2252, creation FILETIME 134329332816298963. The exact executable,
1.6.13 extension, draw entry, shader class, and four repaired instructions
matched before and after. The game remained alive. No renderer settings, camera,
game input, debugger, process writes, or plain-VM changes were involved.

The result retained 2 unique sources from 880 polls: 5 stable, 28 idle, and 847
discarded concurrent/unreadable graphs. This is deliberately partial evidence,
not frame coverage. The current shader owner was stack scratch address
`0x001afd20`; a long nested read often outlives that owner's current contents.
Do not weaken consistency checks merely to increase the sample count.

Original bounded JSON (guest and host hashes matched):

- Guest: `LocalAppData/ShadowbaneLab/client-extension/terrain-material-seam-2252-9d1c1ac-1.json`.
- Host: `E:/Projects/shadowbane/.tmp/terrain-material-evidence-2252/terrain-material-seam-2252-9d1c1ac-1.json`.
- SHA-256: `d5a76ebbf675411c99a9c1fca889f7ea630d035c4c841e1f745812f9d1dc601f`.
- Capture start: `2026-09-03T19:14:14.444255Z`; measured elapsed 5.016 seconds.

Both sources use base color token `0:100000` (binding 1145). Offline decoding of
the preserved `Textures.cache` identifies it as dark rocky ground. Color tokens
`0:100020`, `0:100030`, `0:100035`, and `0:100050` are respectively beige ground,
dark green rocky grass, light green rocky grass, and gray cobblestone. All are
256x256 RGB. These are archive identities, not names inferred from GL bindings.

Source `0x3dfa1d98` retained five paired layers (direction bits 1, dirty 0):

| Color token | Color binding | Source/GPU mask token | Mask size | Mask flags | GPU mask binding |
| --- | --- | --- | --- | --- | --- |
| `0:100020` | 1149 | zero/generated or unattributed | 64x64 | `0x13` | 1292 |
| `0:100000` | 1145 | `13936188:16779218` | 128x128 | `0x03` | 1293 |
| `0:100030` | 1165 | `4101:2432698322` | 128x128 | `0x03` | 1294 |
| `0:100035` | 1160 | `4101:2449475538` | 128x128 | `0x03` | 1295 |
| `0:100050` | 1161 | `4101:2466252754` | 128x128 | `0x03` | 1296 |

Source `0x3dfa1678` retained only the beige-ground layer with a generated 64x64
mask, flags `0x13`, GPU binding 1306, direction bits 0, and dirty 0. All interpreted
texture objects matched the reviewed ArcColorTexture vtable. Archive mask keys
decode to tile `(2,1)`, maps `13936188:1` and `4101:145/146/147`.

GL names are process/context-local. The old trace's bindings 1243/1247/etc.
cannot be equated directly with PID 2252's bindings. The old trace still proves
14x unit-0 texture matrices and identity unit-1 mask matrices for its own draws;
these new snapshots supply resource identity, not a retroactive pixel attribution.

Offline inspection of the exact mask tiles and available neighboring tiles
found nonuniform alpha data, including cobblestone values 0..153 at `(2,1)`.
That is not evidence that all tile edges should be averaged: adjacent samples
are not necessarily duplicate border texels, and generated masks are absent
from the archive. No cache modification is justified by these statistics alone.

Static follow-up at `0x8aaea0` confirms that the matching-copy path requires
flag `0x10` on both source and neighbor masks; its unmatched-layer path also
skips masks without that flag. The archive-backed masks captured above have
flags `0x03`, whereas generated masks have `0x13`. Thus the repaired copy path
does not cover every material mask in this scene. Removing the guard is not
approved: ownership and shared-source mutation would need separate review.

Clarification of earlier zero-hit evidence: the two captures exclude hits only
during their recorded stationary/warm-movement intervals. They do not exclude
edge processing during initial load or a larger streaming transition, and do
not prove the repair is causally irrelevant to all visible terrain.

Completed: safe live polling and offline material/flag attribution. ACTIVE todo:
capture bounded, already-resident CPU alpha masks with reviewed layout gates;
compare source masks with GPU-facing CPU copies and archive records. Do not call
the client's lazy pixel accessor or use GPU readback. Screen-neighbor attribution
and visual seam acceptance remain pending. Local checkpoint only; push remains
held and the temporary bounded-result VM share was removed after transfer.

## Resident-alpha evidence option validated

The existing poller now offers `--include-resident-alpha`. It preserves the
complete-graph consistency checks and adds exact ArcImage/accessor gates,
alpha-only 64/128-square dimensions, repeated resident-buffer reads, and a
16-MiB total read reservation cap including discarded attempts. Missing resident
data is labeled; no accessor, decoder, debugger, or GPU readback is used. Raw
bounded alpha bytes plus SHA-256 are retained for offline comparison. A GPU-facing
texture's CPU backing must not be described as an observation of GPU storage.

Validation: 1,510 tests and 211 subtests passed, 7 skipped; focused Ruff passed.
Completed: bounded alpha option and local validation. ACTIVE todo: one five-second
alpha capture at the unchanged seam view, then compare CPU source/copy/archive
bytes. No renderer behavior or live-client package change is part of this slice.

## Resident-alpha live result — 2026-09-03T19:30:32Z

Frozen diagnostic commit `7e54949` was deployed without replacing/restarting the
client. Its source archive hash was checked after copying locally in the guest:
`64c3448b98570c8d1d4c75bfd233d88229bc8f52c467eeedc9a85e882aa2a670`.
The exact PID 2252 / creation FILETIME 134329332816298963 survived the capture;
all required signatures matched before and after. The console was closed and
both temporary VM shares removed after the bounded result was copied and its
hash verified. No game input, settings change, debugger, GPU readback, process
write, client restart, or plain-VM change occurred.

Artifact SHA-256:
`a4019df3675be4470fe6b038d23afc3c63c67b4a4fdc2923ae7e4f3309e40fe6`.
Host path:
`E:/Projects/shadowbane/.tmp/terrain-alpha-evidence-2252/terrain-alpha-2252-7e54949-1.json`.
Guest path: `LocalAppData/ShadowbaneLab/client-extension/terrain-alpha-2252-7e54949-1.json`.

The five-second run made 918 polls: 65 stable, 27 idle, 826 discarded. It retained
**3 unique snapshots from 3 sources**, not 23 (the initial console OCR misread the
separator next to 3). Alpha read reservations were 3,342,336 bytes, below the
16,777,216-byte cap. Six resident source masks were retained. All six GPU-facing
mask backings had null resident CPU pixel pointers; none was forced to load.

| Source | Layers | Direction bits | Dirty | Resident alpha result |
| --- | --- | --- | --- | --- |
| `0x3de678a8` | 1 | 4 | 0 | generated beige mask, 64x64, range 0..216 |
| `0x3de67350` | 0 | 0 | 0 | base-only source; no alpha layers to invent |
| `0x3dfa1d98` | 5 | 1 | 0 | generated beige mask plus four archive-backed masks |

Exact byte comparisons against preserved TerrainAlpha.cache found zero
differences for all four attributed source masks:

| Archive key | Resident/archive pixel SHA-256 |
| --- | --- |
| `13936188:16779218` | `dc441322f281e826b123b16ab9e55d69b49c9a316d79dd1b510ce1277f566ddd` |
| `4101:2432698322` | `ae99e8aa9e239903dd278dee3d9be7a334c5c2a4f667f3d6ec2afd7eca3605c2` |
| `4101:2449475538` | `b4e9231698bade44e6826309aeff46b4f5c5b4b14ac211b0aefa5507a197be94` |
| `4101:2466252754` | `1e30ba1e0d5620704ed3c930fc5849f88c497e329b52f4e39bd59e4c23123602` |

The two generated mask hashes are
`35b66151f61ebc768269adbe783f35e3a0fb689c0f22dfa0f799490de03ac4d3` and
`f4194a691de2b97f620a471ddc7aab153f302ea708bdb1a1f52a4e2212b85120`.
The first mask's last stored row equals the second mask's first stored row
byte-for-byte (64 samples, range 43..77). This is continuity evidence for that
raw border, not proof that these are the adjacent screen tiles at the visible
seam. The second generated mask ranges 0..88 overall.

Interpretation: these source buffers are neither missing nor silently changed
from their attributed archive records. One generated border also agrees. This
does not establish mask UV orientation, mesh adjacency, GPU contents, or final
pixel blending. In particular, a missing CPU copy is not a zero mask, and dirty=0
is not an upload-completion measurement. Further identical polling cannot recover
already-discarded CPU copies without changing the diagnostic boundary.

Completed: safe material/alpha capture and exact offline source/archive checks.
ACTIVE todo: review mask coordinates and final layer composition for the visible
boundary, using the retained draw trace and mesh/source ownership first. If new
evidence is needed, use a bounded in-process observation of already-submitted
coordinates/upload inputs, not a debugger or GPU readback. Then implement the
evidence-supported visual repair and validate both native profiles and frame
cost before another live release. The visual seam acceptance remains open.

## Geometry ownership and combined capture prepared

The saved terrain stack resolves to ArcSinglePolyMesh -> ArcMesh -> RenderNormal.
Exact RTTI, virtual slots, vertex/UV/index offsets, topology, and per-unit matrix
setup are documented in terrain-resource-ownership.md. The masked draws are
blend-enabled and therefore rejected by BeginBandedLightingDraw; the extension's
single-texture cel shader is not replacing those captured mask passes.

The poller now offers `--include-mesh` alongside resident alpha. It records the
reviewed un-cached triangle path only, keeps full ownership consistency checks,
checks finite coordinates/indices/vector limits, and reserves at most 16 MiB
for all geometry-buffer reads including discarded attempts. Unknown/cached paths
are labeled, not guessed. Source mask rotation is retained as well. Geometry
is part of snapshot identity; these arrays do not prove actual GL bindings.

Validation: 1,532 Python tests plus 211 subtests passed; 7 skipped. Focused Ruff
and diff checks passed. No native renderer or VM behavior change is included.
Completed: offline coordinate-layout review and bounded geometry option.
ACTIVE todo: one combined mesh/alpha capture, then test actual shared geometric
edges and material weights offline before deciding whether another live observer
or renderer repair is necessary.

## Strict combined capture and staged evidence contract

Combined capture from `4fd8c87` completed at 2026-09-03T19:44:36.758144Z against
the same verified PID/lifetime without game input or restart. All signatures
passed, the process survived, and the console/temporary shares were removed.
Artifact: `E:/Projects/shadowbane/.tmp/terrain-mesh-evidence-2252/terrain-mesh-2252-4fd8c87-1.json`,
SHA-256 `236d0cbd4ccc148d57d4be5d5493b1f43c695c2ebed1cccfdb40f39841e46c23`.

5.015 seconds, 1,011 polls, 69 stable, 37 idle, 905 discarded; only one unique
source/mesh was retained. Source `0x3de678a8` uses wrapper `0x4c94dab0`, mesh
`0x4d162aa8`, 21 vertices and 60 indices. Position bounds are X 89600..89856,
Y -355..-352.9305419921875, Z -44544..-44288; UV bounds 0..1 on both axes,
mask rotation zero, and one generated beige mask. Read reservations were
3,342,336 alpha bytes and 604,488 geometry bytes. One tile cannot establish
cross-tile adjacency. Repeating the same long whole-draw ownership requirement
is likely to retain only short/simple graphs again, not improve coverage reliably.

A separately opt-in staged ownership contract was therefore implemented. It
first brackets the root/source/wrapper association with exact primary source
class validation, then double-checks the independent graph and its original
header anchors. It allows the shader to move to another draw only after the
association check; it does not claim concurrent root ownership or pin lifetimes.
Default whole-read checking remains unchanged. This is a documented change in
the evidence contract, not permission to call a partial capture frame-complete.

ACTIVE todo: validate and use the staged mode to recover neighboring geometry,
then compare material weights only where actual mesh edges establish adjacency.

Staged-mode validation completed: 1,535 tests and 211 subtests passed, 7 skipped;
focused Ruff and diff checks passed. Tests distinguish a root that changes before
association is validated (discarded) from one that advances after the association
while its source graph remains consistent (retained and explicitly labeled).
ACTIVE todo: bounded staged capture, followed by offline edge comparison.

## Staged neighboring geometry and preliminary shared-vertex comparison

The staged capture from `60905bd` completed at 2026-09-03T19:52:39.984146Z
against PID 2252, creation FILETIME 134329332816298963. Artifact:
`E:/Projects/shadowbane/.tmp/terrain-staged-evidence-2252/terrain-staged-2252-60905bd-1.json`,
SHA-256 `2c6e5967d381cef79e6a3b5642acbb32912150444d5faed5a5c175592d25c9d8`.
Five seconds, 921 polls, 13 stable, 71 idle, 837 discarded retained 7 sources
and 7 meshes. Alpha/mesh read reservations were 1,024,000 / 314,828 bytes.
All signatures passed, the same process survived, and copied evidence hashes
agreed. The diagnostic console and temporary shares were removed afterward.

The camera was observed at a different angle before this capture. No movement
command was sent, but this is a new view, not a claimed fixed-camera comparison.
When a desktop shortcut did not visibly open a window, no command was typed;
Task Manager restored desktop access before Run and PowerShell were verified.

All seven meshes have 0..1 UV bounds and zero mask rotation. Retained vertices
agree with u=(X-minX)/256 and v=(maxZ-Z)/256. An exploratory offline calculation
compared material weights only at shared referenced vertices (positions rounded
to four decimal places), using source alpha, linear clamp-to-edge sampling, and
successive source-alpha composition in layer order. Total-variation distance
between the resulting material-token weights was:

| Sources | Shared vertices | Maximum / mean weight distance |
| --- | ---: | --- |
| `0x3dfa1d98` / `0x3dfa2848` | 37 | 0.077278 / 0.024906 |
| `0x3dfa1bd0` / `0x3dfa1678` | 33 | 0.027451 / 0.000832 |
| `0x3de65fb8` / `0x3de66348` | 20 | 0.002953 / 0.000261 |
| `0x3dfa2848` / `0x3dfa1678` | 15 | 0 / 0 |

The largest difference is at (89088,26.25,-45056): modeled rock weight changes
from 0.703114 to 0.780392, beige from 0.292964 to 0.219608, and dark green from
0.003922 to zero. This is source-data evidence, NOT measured framebuffer color
or actual GPU mask content. It does not sample entire connected boundary
segments, include RGB texture phase/lighting/fog, or prove which edge dominates
the visible seam. The earlier equal raw mask row must not be treated as geometric
adjacency; mesh attribution is required.

Completed: bounded staged capture and preliminary shared-vertex comparison.
ACTIVE todo: inspect current final draw state and close the GPU/coordinate/lighting
evidence gap before selecting a visual repair. Full connected-edge analysis may
also be needed. No source-cache mutation or visual fix is justified by these
vertex-only differences alone. Visual seam acceptance remains open.
