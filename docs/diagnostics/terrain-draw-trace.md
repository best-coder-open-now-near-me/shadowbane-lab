# Local terrain draw/texture tracing

This observer establishes rendering evidence for the terrain seam investigation.
It is **not a seam repair**, a terrain classifier, or a performance benchmark.
No new executable offsets or terrain hooks are trusted. Capture boundaries reuse
the whole-function-verified main clear and done3d calls already used by the renderer.

## Runtime ownership

- Full-renderer only; opt-in at launch with `WONDERBANE_TERRAIN_TRACE=1`.
  Diagnostics-only cannot enable it. Normal launches allocate no trace storage,
  create no trace IPC objects, and perform no trace GL queries.
- Requests address one PID and process creation FILETIME through a local named
  event. They arm at a present, then observe the following frame. A missing main
  clear/done3d produces incomplete evidence, not a heuristic replacement boundary.
- At most 8,192 original submission records, four fixed-function texture units,
  and 24 stack frames per record. The query budget is 250 ms; overflow and skipped
  queries are counted. That is an observer budget, not a hard wall-clock deadline
  on a driver call or the game frame.
- No queries while compiling a display list or inside an immediate primitive.
  Other threads/contexts are rejected and invalidate interval completeness.
- Snapshots precede extension lighting/accent/composite passes. Queries temporarily
  select each server texture unit and restore the original selection. No texture
  parameters, matrices, colors, or game input are changed.
- All JSON formatting and local file writes occur on the existing graphics-status
  publisher thread. Only bounded storage and queries occur in the render hook.
- Separate files under the existing local graphics-status directory are created
  exclusively and published without replacement. UNC, mapped network drives,
  reparse directories, and caller-supplied output destinations are refused.
  Failed publication is never a complete `.json`; a `.partial` may remain.

## Operator workflow (1.6.12 and 1.6.13)

Publish the separately verified graphics package, preserving the older
package. Use the normal launch script with the explicit `-EnableTerrainTrace`
switch; it scopes the opt-in to the child client and restores the parent
environment. An ordinary launch explicitly clears this opt-in.

The 1.6.13 collector and analyzer also accept saved 1.6.12 schema-1 traces;
unknown versions remain rejected. A live request is additionally bound to the
exact extension version read from that process's status, not merely either
supported version. Upgrading tools must not invalidate the retained capture.
The 1.6.13 mask-refresh correction does not change this draw schema or attribute
resource IDs. Its installation state is separately reported in graphics status
as terrain_mask_refresh; effect toggles do not uninstall it.

After the user has logged in and put the affected terrain in view, run
`scripts/capture-wonderbane-terrain-trace.ps1` locally in that VM, pointing
`-RepositoryShare` at the reviewed frozen source. Optional `-ProcessId` and
`-ProcessCreationFiletimeUtc` narrow selection. Without them, exactly one verified
client must exist. No game input or settings changes are used.

The underlying module is `python -m shadowbane_lab.diagnostics.terrain_trace`.
It verifies the running executable, PID/lifetime, renderer profile and version,
reserves a lifetime-bound collector mutex and idle gate, signals one request, and
waits for a new local atomic file. Busy/abandoned requests fail closed. A collector
crash after reserving the gate can require a normal client restart; it never
silently sends another request. Missing/incomplete data are reported separately.
Exit codes: 0 captured within the declared scope; 2 saved with coverage limits;
1 not captured or rejected. No trace files are copied or uploaded.

## Schema 1

Top-level identity includes executable SHA-256, PID, creation FILETIME, sequence,
render thread, and a process-local context token. Times are QPC ticks with an
explicit frequency. `query_ticks` includes state queries and stack observation.

`reviewed_interval_complete` describes boundary continuity only. It does not
claim exhaustive state coverage: also inspect helpers, unit omissions, capacity,
unsafe-query and budget counters, and per-draw restoration results.

Submission codes: 0 immediate, 1 display list, 2 multiple lists, 3 arrays,
4 indexed elements. Count `-1` means unknown. The draw ordinal indexes retained
records, not every actual primitive inside the driver. Caller/stack addresses are
filtered to client RVAs; stack unwinding is best-effort, bounded evidence, not
terrain ownership authority. A zero caller RVA means outside the client image.

Each `state` array contains, in order: depth test, depth write, depth function,
alpha test, alpha function, blend enabled, blend source, blend destination,
lighting enabled, fog enabled, cull enabled. Also recorded: alpha reference
(one-element array), current color, model-view/projection matrices, viewport,
and original active texture unit. Nonfinite float values serialize as `null`.

Each unit records 2D enable/binding, texture matrix, environment mode, and:

- `level`: level-zero width, height, internal format, border.
- `sampler`: minification filter, magnification filter, wrap S, wrap T.
- `combine`: RGB/alpha functions; RGB sources 0–2; alpha sources 0–2;
  RGB operands 0–2; alpha operands 0–2; RGB/alpha scales. `null` if unsupported.

## Deliberate limits

Texture IDs are context-local GL names, **not archive resource IDs**. This trace
does not read pixels, texture bytes, geometry buffers, or index contents. It does
not identify an object under a screen coordinate, decode cache ownership, log
unhooked/driver-internal submissions, or inspect display-list internal draws.
List state is entry state even when the source-state stability cache reports true.
Only 2D level zero is described; other texture targets, mip contents, per-vertex
UVs, texgen, shader programs, and complete material/light/fog parameters are not
captured. Do not infer those values from defaults or from missing fields.

Use this evidence to narrow the real texture/transform path before authorizing
any terrain-specific repair. Preserve stock height, population, collision, UI,
other materials, and the existing 1.6.11 transparency fixes.

Combiner query tokens and capability gates follow the Khronos
[texture environment combine specification](https://registry.khronos.org/OpenGL/extensions/EXT/EXT_texture_env_combine.txt).
