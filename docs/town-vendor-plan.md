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

## Nearby-building source checkpoint

Implemented `client observe-native-nearby-vendors --process-id PID --json`.
It copies the active City Command window's building cache and each building's
nested hireling keys and labels. It does not require selecting each building or
vendor. Stable building and hireling IDs remain separate from actor IDs.

Static inspection established these exact-build paths (RVAs, not runtime
addresses):

- Game-window initialization at 0x794830 constructs ArcCityCommandManager through
  thunk 0x00F56A / constructor 0x6EB430 and stores it at root+0xD4. Root+0xA8 is a
  different manager and must not be used for this roster.
- City-command manager type 0x1171BCC owns its window at +0x4C and primary cache
  at +0x74. The +0x80 collection is a filtered subset, not a second town roster.
- Ordinary opening constructs the CityCommand HUD (0x1166234), installs its
  owner backlink and calls request routine 0x6F10A0. That routine creates
  ArcCityAssetMessage and sets mode 14. Response handler 0x3E7580 handles mode 15,
  inserts the returned records and completes the UI update.
- Response parsing constructs ArcCityInfoBlock (0x117A7A8): display text +8,
  primary key +0x20, nested hireling map +0x38. The parser constructs
  ArcHirelingInfoBlock (0x117A7BC) with text +4; its map owns each hireling key.
- Both maps use null child pointers, header root/+4, extrema/+8/+0xC,
  node parent/+4, children/+8/+0xC, key/+0x10 and payload/+0x18.
- The response's empty-result text explicitly refers to nearby assets.
  This is not evidence of complete Rooty membership or an unrestricted remote
  building-management capability.

The reader checks the exact executable, in-world state, manager/HUD types,
active HUD ownership, initialized management mode, response-pending flag,
bounded trees, parent links, counts, extrema, unique keys/payloads and UTF-16
strings. It rechecks all copied memory in reverse order. Empty top-level caches
are unavailable, not proof of zero manageable buildings. Buildings with a
valid empty hireling map are retained. All town-completeness, fresh-response,
management-permission and command-admission claims remain false.

A read-only live header probe confirmed root+0xD4 and both empty collections.
It did not observe populated building/hireling records. The staged source
reader's subsequent live check was blocked by automatic approval review:
the existing VM authentication wrapper reads a saved setup password, and the
reviewer requires explicit authorization for that credential use. Do not retry
through another wrapper or source. No native calls, new jobs or item actions
were performed. Installed native 1.8.3 / host 0.3.11 remain unchanged.

Validation: 36 focused tests and 126 subtests passed; full host suite 2187
passed, 14 skipped, 659 subtests. Whole-tree Ruff passed. Prior checkpoint
dcfae1b CI succeeded (run 34915881138). Source-reader live success remains
unqualified; fixtures are not live acceptance.

Private evidence stays in artifacts/vendor-protocol/city-*.txt and the existing
test diagnostic share's town-command-collections.json. The staged reader and
verify-nearby-roster.py remain in that same private share for qualification;
they are not a replacement installed package. No credentials, client binaries
or raw process captures are included in source delivery.

The first todo remains active: verify populated nearby membership and freshness,
establish town coverage and actor association. Next implement the ordinary
city-window request and building/vendor switching through the existing owner
thread and correlated receipts, then connect the durable town plan and selection
UI. No Select all/Start control should claim full-town coverage from this cache.

## City-window native command checkpoint

The owner explicitly authorized use of the saved test VM setup credential on
September 14. The same read-only verification then ran successfully and reported
"city command window is not initialized". The earlier credential-use review
block is resolved. Populated live roster validation remains pending.

Native 1.8.4 source now provides typed City Command inspection/open operations
(transport kinds 11/12), separate from crafting and movement commands. The
ordinary action dispatcher at RVA 0x7CA9C0 maps fixed action 0x334 to its city
manager branch at RVA 0x7CBD9B. That branch installs the active manager at
RVA 0x16A7C1C before calling Open(root). The implementation uses that ordinary
branch; it does not expose an arbitrary native address or action identifier.

The existing owner-thread service captures a fresh city-window state, checks the
exact HWND, current scene and producer lease, and blocks opening while crafting
is pending or unresolved. Requests have strict padding/identity checks,
expiry-before-execution handling and non-evicting deduplication. A repeated
request cannot reopen the window; an already visible active City Command is a
no-op. A submitted receipt verifies the local window opened, not server roster
freshness, permissions, or town completeness. No items or building settings
are changed by this operation.

The extension builds with warnings as errors. All six focused native city-window
and existing vendor controller/memory/channel tests pass. This native slice is
not installed yet. Next: host wire/session and coordinated invocation, broader
native validation, exact package preparation and live City Command qualification.
The first discovery todo remains active; the native open action is a supporting
part of its automatic acquisition path.

## Coordinated discovery host checkpoint

Host 0.3.12 adds strict City Command wire/session support and a "Find nearby
buildings" dashboard action. Admission requires the current healthy worker
permit and its city-window capability record, refuses overlapping operations,
and uses the existing worker operation ledger. The operation waits up to 60
seconds for readiness/focus, opens at most once, then observes loading and
checks the nearby reader against the same game identity, scene and native
building count. Cancellation stops further dispatch. Unknown, changed or timed
out results are recorded for review without repeating the open request.

Discovery owns separate immutable operation files under the instance's
vendor-jobs/discovery directory and a small nearby-summary.json for the
dashboard. It uses the same execution lock as crafting, preserves existing
crafting journals, and never turns observed hirelings into production commands.
The full roster stays in the operation record; the dashboard reports nearby
counts and explicitly leaves full town coverage unverified.

Native and Python snapshot/command/receipt bytes agree against the compiled
fixture. Focus waits, cancelled work, uncertain opening, changed scene/roster,
repeat operation execution, receipt mismatches, stale capabilities and
overlapping-operation admission have focused coverage. Required native tests:
148 passed-or-skipped (145 executed successfully, three private-image checks
skipped pending the exact builder). Full host run: 2199 passed, 15 skipped,
680 subtests, with one missed native API version constant; that constant was
corrected and the 34 affected/focused tests plus 25 subtests then passed.
Whole-tree Ruff passed. Exact packaging and live installation remain next.

## Exact discovery package prepared

The exact c268cc0 package (native 1.8.4 / host 0.3.12) passed both required
native profiles, private image checks, packaging/installed gates, installed
City Command byte agreement, full Python/Ruff checks and all seven CI jobs.
Package and reversible VM update preparation are complete; activation waits for
the running game to close. The existing game/manager remain on 1.8.3 / 0.3.11.
Host 0.3.12 is staged alongside the old environment and its exact source identity
and proposed one-entry client inventory update passed read-only verification.

See [exact package and activation handoff](handoffs/town-discovery-1.8.4.md).
The discovery todo remains active: live nearby roster qualification is next,
followed by town membership/completeness/access and automatic building/vendor
selection. No manual recipe window is needed for the new discovery operation.

Native 1.8.4 activation is now verified. The first live discovery failed before
native publication because shared host transport admission omitted the new type.
Host 0.3.13 corrects that integration boundary with a real Windows shared-memory
regression. Full host validation: 2203 passed, 14 skipped, 680 subtests; Ruff
passed. Retry through the updated manager remains the next active todo; no
additional game restart or manual vendor-window setup is required.

The corrected host is installed and its new discovery operation succeeded:
automatic City Command open, independently verified 11-building nearby cache,
and user confirmation of the visible window. Both known workshops are present.
Nested hireling collections are empty and City Command also owns guard settings;
crafting-vendor association remains unqualified. The active todo is the separate
building-management/hireling acquisition path, followed by automatic switching
and the saved town plan. See the live handoff.
