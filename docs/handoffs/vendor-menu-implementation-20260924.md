# Vendor menu operations - September 24

Source checkpoint on `codex/vendor-town-workflow`, targeting main through PR #38.
Not packaged, installed or live-accepted. Installed native 1.8.30 / host 0.3.50
remains unchanged. Raw observations and client binaries remain private.

## Resulting behavior

A finished vendor batch now opens its own Inventory before continuing the existing
Keep workflow. The manager verifies menu support before its first Create, borrows
the existing producer transport/command sequence, and journals menu requests before
sending. Interrupted, mismatched or replayed menu evidence requires review; a
currently visible window cannot repair a lost acknowledgement.

The same typed menu service opens ordinary single-item recipes, selects a template,
sets Magic/random mode and closes owned recipe/Inventory windows. Recipe preparation
verifies retained, activated and selected template identity, table when requested,
random sentinels, quantity and single mode. The separate menu protocol leaves
Create/Keep and navigation payloads unchanged. Existing Gilded Scepter spending
admission remains in place; dagger production is not enabled by selection evidence.

Native operations run on the existing owner thread, through ordinary owned controls.
They recheck lifetime, foreground, producer lease, pending operation barriers,
current page and event-parent route before each call. A list selection alone does
not complete activation. Recipe HUD/list replacement cannot satisfy an earlier
selection or mode request. Other vendor, city, guard, funding and Condemn writes
remain blocked while a menu result is pending or uncertain. Observations are demand-driven; Inventory visibility makes no freshness or completeness claim.

The journal has a separate bounded schema and validates its full ordered request
chain on recovery. No migration or replay of existing spending records is performed.
Closing a borrowed menu adapter leaves its parent's transport alive; closing the
parent invalidates the adapter.

## Validation

- Full-profile Win32 DLL build passed with MSVC and warnings treated as errors.
- Twelve affected native controller/channel/runtime tests passed, including mapped
  control dispatch, ownership, cancellation, reentrancy, replacement windows,
  transport expiry and shared barriers.
- 172 affected host tests passed (85 subtests), including receipt correlation,
  lost acknowledgements, exact recovery chains, borrowed transport lifetime,
  incompatible native support before spending, and the synthetic C++/Python wire
  fixture. Ruff and diff checks passed.
- Independent native/host integration review completed; the replacement-window
  finding was fixed and tested. Hosted CI and live acceptance remain separate.

## Remaining work

The actual Inventory close control and full event-parent routes are dynamically
checked, with no guessed fallback. They were not all captured by the earlier
manual walkthrough; candidate live acceptance remains required. A missing named
CANCEL or unsupported route returns unavailable and does not invoke another control.

Next: saved random-recipe admission and durable town plan/visit scheduling, followed
by a coherent versioned package and supervised acceptance. Recipe preparation is
available to that orchestration; the dashboard does not yet save arbitrary recipes.
Multiple-mode preparation, generalized crafting, full resource/affix policy and
recurring spending are not completed. Preserve unknown affixes and old unresolved
Create/Keep records.
