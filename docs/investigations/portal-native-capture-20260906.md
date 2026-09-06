# Portal native draw capture, September 6

The owner reports three visible effects **per portal**: one image scaling larger
and smaller, and two particle effects. This is owner-provided visual ground truth;
individual submissions have not been assigned to those three components.

After an approved normal relaunch with native trace opt-in, the existing collector
captured the portal scene once the owner confirmed it was in view. No deployment,
hot unload, combat input, or graphics-settings change was performed.

The collector returned `captured_with_limits`, sequence 1:

- Reviewed world interval complete; 594 observed submissions, 593 retained.
- One unsafe-query skip; zero capacity or query-budget skips; four omitted units.
- 95 distinct texture-unit/binding pairs; observer query time 1.8223 ms.
- All 593 retained records include transmission state; zero active-unit
  restoration failures.
- 592 retained records use a perspective projection, of which 275 enable blending.

The blended perspective records include 169 depth-tested, non-depth-writing
additive (`ONE, ONE`) submissions; 40 with the same depth settings and ordinary
alpha blending (`SRC_ALPHA, ONE_MINUS_SRC_ALPHA`); and 14 with destination-color
multiplication (`DST_COLOR, ZERO`). Another 47 alpha-blended submissions write
depth (30 also enable alpha testing). Five blended submissions disable depth
testing. These are whole-scene groups, not portal-specific attribution. Records
include multi-draw submissions and display-list entry-state limits; counts do not
represent individual particles.

The trace includes per-submission model-view/projection matrices and viewport,
blend factors/equations/constants, depth/alpha state, stencil state, color masks,
texture-unit entry state, and bounded caller/stack RVAs. It contains no pixels,
texture contents, geometry, complete shader evaluation, or per-fragment outputs.
It narrows native material families but does not prove complete transparency
reconstruction or authorize replay. Missing submission/unit coverage remains
explicit. Raw trace data and exact runtime provenance are retained privately.

Next graphics step: attribute the three owner-described components using retained
caller/texture/state evidence, preserving the whole-scene distinction. Graphics
implementation remains with the integration/particles work. This capture does
not reopen that implementation in the identity feature branch. Pet ownership
calibration remains deferred until a known pet is available.
