# Bounded terrain refinement for camp return

The later .94 camp run moved through native chase and completed three NPC death
cleanups. Both return attempts failed before route dispatch. Replaying the exact
terrain cache and geometry reproduced all 5,760 sampled cells and 334 inferred
blocked cells. The character occupied a coarse cell whose five height samples
spanned 66 bytes, exceeding the existing 64-byte threshold. The smaller occupied
cell spanned only 7 bytes. These are raster sample differences, not calibrated
climb angles or proof of native traversability.

Previously terrain estimates used the same obstacle layer as explicit walls.
Refinement copied each blocked coarse cell to every child, retaining this false
positive. The .95 host correction retains immutable raster/geometry evidence in
a separate terrain layer. After a failed local A* search, it resamples only that
planning window at progressively finer resolutions, bounded by the native raster
spacing and existing seed/search budgets. Explicit walls and learned collision
cells retain their obstruction semantics. Water, density and traversal costs
remain costs. Successful coarse routes keep the original path; the original map
is not rewritten by a failed or successful refined search.

The exact private replay now produces a route to the original frozen camp anchor
in approximately 0.15 seconds, without changing the global cell size, thresholds,
lease duration, native admission or arrival checks. Synthetic tests cover the
coarse-cell false positive, a genuinely blocked terrain band, explicit and learned
walls, cost preservation, distant terrain sources and seed-budget exhaustion.
Existing terrain, A*, camp and controller tests remain required.

The source change has no native or client asset changes. A computed route is not
live movement acceptance: qualified deployment must still demonstrate native
movement and observed return under the existing owner and cleanup boundaries.
