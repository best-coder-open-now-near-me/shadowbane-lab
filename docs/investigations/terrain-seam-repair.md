# Stock terrain seam repair investigation

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

Release identity and launcher pins are updated together. Full DLL SHA-256:
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
