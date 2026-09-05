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
4 indexed elements, 5 multi_elements (`count_unit: subdraws`). Count `-1` means unknown. The draw ordinal indexes retained
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
UVs, texgen parameters, program contents, and complete material/light/fog parameters are not
captured. Bounded enable/binding observations are described below. Do not infer those values from defaults or from missing fields.

Use this evidence to narrow the real texture/transform path before authorizing
any terrain-specific repair. Preserve stock height, population, collision, UI,
other materials, and the existing 1.6.11 transparency fixes.

Combiner query tokens and capability gates follow the Khronos
[texture environment combine specification](https://registry.khronos.org/OpenGL/extensions/EXT/EXT_texture_env_combine.txt).


## Bounded quad material evidence

The optional additive `quad_support` fields describe entry state, never replay
permission. Existing schema-1 traces without these fields remain readable and
cannot establish the new facts. `transmission_state` records current GLSL program
(on GL 2+), framebuffer, separate blend factors/equations, stencil and color mask.
Its unavailable integer sentinel is -1. No program is replaced or executed by
this observer.

`arb_enable_binding` is `[vertex_enabled, vertex_binding, fragment_enabled,
fragment_binding]`. Each advertised ARB capability enables only its own query;
`glGetProgramivARB(target, PROGRAM_BINDING_ARB)` reads binding. A missing function
leaves binding -1. Known absent extension yields enable 0 and binding -1, with
`arb_vertex_supported`/`arb_fragment_supported` false. Missing extension string
is unknown, not absence. Queries follow the Khronos
[ARB vertex program](https://registry.khronos.org/OpenGL/extensions/ARB/ARB_vertex_program.txt)
and [ARB fragment program](https://registry.khronos.org/OpenGL/extensions/ARB/ARB_fragment_program.txt)
contracts; no GL error state is consumed.

`compatibility` is 1 for a recognized pre-3 desktop context or a 3.2+ compatibility
profile, 0 for a 3.2+ non-compatibility profile, -1 for an unestablished profile.
Unqueried alternative material mechanisms are conservative unknown: core 4.1+
or ARB/EXT separate shader objects (program pipelines), pre-2 ARB
shader objects, NV vertex/fragment programs, ATI fragment shader, EXT vertex
shader, NV register combiners/texture shader, EXT fragment lighting/light texture,
and ATI environment bump mapping. Advertising these does not prove they are on;
it prevents a fixed-function claim until their state is resolved.

Per texture unit, `alternate_targets` contains 1D/3D/cube/rectangle enables with
core/extension capability gates. `texgen_enabled` contains S/T/R/Q enables.
`env_color` is the four-component environment constant, null if its optional
getter is unavailable. Texgen modes/planes, alternate-target bindings and full
material parameters are deliberately not queried. The bounded material gate
rejects relevant enabled paths instead. Existing combine and texture matrices
remain available as evidence even when their path is outside this gate.

The diagnostic `material_gate` returns `fixed_function_material_candidate` only
for immediate QUADS at caller RVA 538ED0 or D8F13, with known compatibility and
extension state, GLSL absent/zero, ARB enables zero and advertised bindings known,
no unobserved alternate program mechanism, lighting/fog/color-sum disabled, all
fixed-function units observed and active unit restored. Every alternate target
must be off; any enabled 2D texture must be unit zero, bound, MODULATE, with texgen
off and a finite texture matrix. Current RGBA must be finite. Untextured current
color is also a material candidate. Other results name the first blocking
material condition; inspect raw fields for additional conditions. These caller
RVAs are evidence filters, not executable seals or authority to read arguments.

`raster` order is render mode, sample buffers, samples, color sum, scissor enabled,
polygon offset fill enabled, color logic op enabled, maximum user clip planes.
Also recorded are front/back polygon mode, scissor rectangle, depth range and
up to six clip-plane enables (-1 for unavailable entries). A larger maximum
means clip state is incomplete. These values describe raster restrictions; they
are not included in the narrower material predicate.

**`replay_eligible` is always false in this diagnostic.** No replay path has been
validated. A future eligibility predicate must additionally establish supported
blend/channel behavior, GL_RENDER, single-sample framebuffer compatibility,
applicable scissor/polygon/offset/clip behavior, absence of duplicate native query
side effects, pre-native depth/stencil, explicit coverage preserving alpha tests,
sealed geometry/UV ABI and source equivalence. The query side-effect state,
attachment formats/contents and pixel equivalence are explicitly unobserved.
Lighting/fog/material internals and unsupported program contents are not inferred.
This result never changes effects settings or silently disables a requested cue.

The existing one-frame caps, query budget, query-safety guards and cleanup still
apply. Additional fields increase query work within the same budget, so inspect
budget-skipped counts before using the trace as evidence. No connected capture
or deployment is authorized by these fields.
