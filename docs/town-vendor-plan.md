# Town vendor management

Active owner: codex/vendor-rolling. Integration destination:
codex/native-lifecycle-hardening, then reviewed main. No merge is implied.

## Current priority and evidence

The owner redirected work from the single-vendor Keep test to selecting the
town's buildings and working across its vendors. Rooty and character Treehugger
remain the live target. The current multiple-mode batch stays in review:
its one created scepter is complete in production; Keep has not run. The other
three manual items remain present. Do not replay or clear that job.

The September 14 read-only census used the installed, build-guarded character
population reader. It found 19 loaded merchant/shopkeeper candidates, with zero
rejected candidates and no game actions. Neither known sage hireling ID appeared
among their candidate object keys. Do not treat actor keys and hireling IDs as
interchangeable. Loaded population is not a complete town roster and does not
prove building affiliation or management permission. Raw census evidence stays
private under vendor-manager/town-discovery-population.json.

The existing Create/Keep controller starts from the active game window's city
manager, selected building/hireling and live menu ownership. It has no qualified
town roster, building selection, hireling selection, or automatic menu-opening
command. Existing door collection work is owned by another lane; reuse its
verified boundaries only after integration, not its private drafts.

## Operator flow

Choose the town, then see buildings with their vendors underneath. Each vendor
shows its service, rank/capacity when known, selected recipe, production state,
and any reason it cannot currently be managed. Building selection selects its
eligible vendors. Select all applies to the verified town roster; visibly report
incomplete discovery and distinguish inaccessible or unverified entries.

Save the selection and crafting rules for later sessions. Start runs one
capacity batch across the selected vendors. Pause and Stop operate on that town
run. Progress shows which vendor is being visited and which are cooking, ready
for collection, finished, or need attention. The runner opens the required game
windows and changes vendors itself. Requiring the owner to open every menu is
not acceptance for this feature.

Do not assume every vendor crafts Gilded Scepters. A recipe must be available
and selected for each eligible vendor or compatible group. Preserve the user's
affix policy: exclude confirmed Tier 1/2; keep unknowns. Automatic disposal
remains unqualified. A town run does not add unlimited replacement batches.

## Durable ownership and data boundaries

- A saved town plan owns stable town/world identity, the selected building and
  hireling keys, per-vendor recipes and policy. Rooty is a display label, not
  sufficient identity. Names and raw native addresses are never selection keys.
- Discovery owns roster completeness, building membership, actor-to-hireling
  associations, access evidence and freshness. Changed, unloaded or ambiguous
  entries become unavailable; they are not silently dropped or substituted.
- Native interaction owns fresh object resolution, ordinary game permission and
  range checks, window opening, vendor selection, recipe selection and Inventory.
  Every action runs on the existing native owner thread under the exact current
  process/scene and worker permit. Local call success needs the intended visible
  state or correlated response before the next action.
- The manager owns one town operation and one native command stream. It visits
  vendors sequentially to fill verified free capacity, lets production run in
  parallel, then revisits eligible completed work. Capacity is reread each visit.
  Existing movement services may supply travel only through their qualified
  dispatch path; inaccessible buildings are reported, not acted on remotely by
  guessed messages.
- Per-vendor journals retain the exact request IDs, queue additions, expected
  counts and inventory confirmations. The town journal records scheduling and
  references these receipts. Existing schema-1 and schema-2 Create journals
  remain readable. They do not become new unsent actions during migration.
- Window pointers belong to an individual visit. Closing a window between
  completed phases should cause explicit re-resolution of the same stable
  building/vendor, not permanent invalidation or silently changing the saved
  owner. While an action is pending, its strict current ownership checks remain.
  No rebind can replay an uncertain Create or Keep.
- UI/API requests carry the plan revision, exact client instance and current run.
  A stale browser selection or another client's plan cannot start operations.
  A restored run first reconciles durable evidence and never automatically
  replays an interrupted mutation.

## Delivery sequence and active todos

1. ACTIVE: qualify building discovery and actor/hireling association, including
   the town boundary, completeness and manageable access. Inspect the ordinary
   city-management request/response and existing native collection ownership.
2. Implement and qualify native building/vendor/window selection through the
   existing owner-thread transport, including response correlation and reopening.
3. Deliver the durable town plan, building/vendor selection UI and single-owner
   scheduler together with those native interactions. Keep this a coherent
   production slice; do not expose Start against fake or unconnected adapters.
4. Test discovery deduplication and missing data, mixed vendor services,
   capacity/rank changes, menu reopening, scene loss, inaccessible buildings,
   per-vendor exclusions, pause/stop, crash recovery and uncertain receipts.
   Then qualify multiple buildings and vendors in Rooty without manual window
   preparation, and publish the exact package and integration handoff.

The interrupted single-vendor Keep qualification is retained as unfinished
evidence and will be revisited through the automatic window lifecycle. No
additional manual crafting roll is required for discovery.

## Building-to-hireling reader checkpoint

Implemented `client observe-native-vendor-roster --process-id PID --json`.
It reads the current building identity and label, the displayed owner label,
and every visible hireling's native ID, name and service label. A selected
hireling, production recipe and Inventory are not required. The command is
read-only and closes its handle on success and failure.

The exact client constructor initializes ArcHirelingEntry strings at +0x30 and
+0x48. The observed buffers are UTF-16. The active ArcCityAssetManager owns the
management HUD; its list controls own the hireling entries. The reader checks
all back-pointers, exact types, unique hireling IDs, matching building selection,
bounded buffers/collections and a reverse consistency pass. Unknown service rows
are excluded. Missing rosters are unavailable, not a successful empty result.
It does not infer management rights from the displayed owner name, or claim
town/building roster completeness.

A private live probe identified building ma-helm with two distinct hirelings:
So'hegho (Lizardman Medium Armorer) and Xelvin (Irekei Helmsmith). This confirms
building-to-hireling membership independent of the earlier actor census. The
subsequent staged production reader found the management window closed and
correctly refused the read; that reader's successful live check remains pending.
The installed host is unchanged. Native constructors and probe evidence remain
private under artifacts/vendor-protocol and the test runtime's vendor-manager.

Validation: 28 focused roster/queue tests and 81 subtests passed; full host suite
2178 passed, 15 skipped, 614 subtests. Whole-tree Ruff passed.

The first todo remains active: this is the current-building membership portion.
Broader city building discovery, roster completeness/access, and automatic
window selection remain unqualified. Do not expose town Start from this partial
discovery alone.
