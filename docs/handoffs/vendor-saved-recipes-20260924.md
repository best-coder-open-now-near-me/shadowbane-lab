# Saved random vendor recipes - September 24

Source: `codex/vendor-town-workflow`, draft [PR #38](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/38), targeting `main`.
Native 1.8.31 / host 0.3.51 identify the pending vendor candidate. This checkpoint is source-only. The VM remains native 1.8.30 / host 0.3.50;
no game command, crafting, deployment or live acceptance was performed for it.

## Behavior and ownership

The dashboard loads the selected vendor's actual single-item recipe list. The
player chooses a recipe and saves its random mode. Preferences are immutable
revisions scoped to server, calibrated character key, building and vendor. A fresh
client may activate that preference only after observing the same owner and vendor.
Start pins the revision, re-prepares its exact template/table and fills one batch
of available slots. When those items finish, it opens Inventory and Keeps them.
A full production queue completes without opening recipes or changing existing items.

Catalog loading and saving share the worker's operation lease and durable menu
journal. Start checks generalized native support before spending. A changed
character, vendor, HUD/list, recipe, table or queue invalidates admission. Lost
acknowledgements and incomplete action journals require review; restart does not
replay an uncertain Create, Keep or menu operation.

## Native and journal boundaries

New verbs 32/33 provide generalized random Create and feature inspection using the
existing fixed-size channel. Legacy verbs and their Gilded Scepter restrictions
remain unchanged. The native owner thread independently verifies selected,
activated and retained typed template, exact table, random sentinels, quantity one,
single mode, current owned control/page, foreground, lifetime and producer lease.
Generalized Create dispatches the ordinary CREATE control, preserving the game's
resource, cost and naming checks. An unconfirmed request expires as unresolved
without a retry. Completion requires exactly one correlated production addition.

Schema 3 batch evidence pins the canonical recipe hash and exact completed menu
preparation bytes/hash, process lifetime and owner. Recovery validates the entire
request and item chain. Legacy schemas reject new recipe fields, including attempts
to relabel a generalized Scepter batch as historical evidence. Generalized results
preserve all unknown affixes; historical Scepter exclusion evidence cannot grant
exclusion authority for this path. No new affix decision or town scheduler is implied.

## Validation and next step

- Full Release Win32 extension build and 13 affected native tests passed.
- Combined vendor/manager/operation suite: 895 passed, 4 skipped, 449 subtests passed.
- Ruff and diff checks passed; independent native/host and manager reviews completed.
- Regressions exercise two templates through preparation, Create, Inventory and
  Keep; owner/scene replacement; changed table; stale saved revision; old worker;
  full capacity; interruption/recovery; downgrade rejection and pending-menu Stop.

Next: version a coherent exact-source candidate, run package gates and stage it
for supervised acceptance. User acceptance must cover the actual recipe list,
saving a choice and one available-capacity batch. Durable town visits, scheduling
and repeat batches remain separate unfinished work. Private captures, binaries,
credentials and build output are not part of this source delivery.

The candidate starts from canonical main plus PR #38. Cancelled carpenter preview
and recorder drafts are not included; their installed 1.8.30 rollback package and
private evidence remain retained. No installation change is implied by versioning.
