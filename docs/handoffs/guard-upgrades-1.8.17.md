# Guard discovery and Gold activation: 1.8.17 / 0.3.26

Branch: codex/guard-upgrades. Review into codex/vendor-rolling, then
codex/native-lifecycle-hardening and reviewed main. Not merged.

## Live findings on 1.8.16

The exact user-launched extension initialized and its new worker became healthy.
Warehouse building navigation succeeded. Fresh login still requires View Resources
opened once: the automatic return hook borrows that panel's owned Seneschal.
After this initialization, warehouse building/resource return was confirmed.

City Command found 60 candidate structures. Navigation passed the Tree companion
panel, verified six building rosters and eight individual guard windows, then
stopped at an owned wall menu with zero hireling slots. Four populated rows in each
six-guard tower remained unavailable beyond the first two visible rows. Neither
this scan nor the available roster proves full-town coverage.

A separate bounded qualification used one exact guard already confirmed by that
scan, through the production funding cycle and durable journal. This was not a
fabricated town plan. Tower, guard and warehouse return were confirmed; the quote
opener returned UNCERTAIN before a withdrawal amount window appeared. The record
contains no withdrawal, deposit or upgrade request and all gold totals are zero.
The uncertain request remains retained and blocks that client lifetime; no replay
or journal reset was sent. The previous deposit/reopen corrections remain unqualified.

The observed Gold list selection changed, but the warehouse selection set did not
and Withdraw stayed disabled. Static inspection confirms mouse-down selects the
list while event-zero activation dispatches the mapped resource action.

## Combined correction

- Gold selection uses the ordinary list setter and event-zero activation for the
  exact owned Gold row. It then rechecks the selected resource, enabled Withdraw,
  unchanged quote inputs, lifetime and admission. Existing Gold-only selection is
  preserved; another selection is not expanded. No transfer follows a failed check.
- Exact hireling rows outside a validated list viewport use the native clamped
  scroll setter. Full typed roster membership, disabled/hidden state, row ordinal,
  viewport bounds and action map are checked. The row must become visible, retain
  its owner/key and pass fresh lease/foreground admission before activation.
  Hidden rows inside the viewport, invalid dimensions and uncertain scrolling
  remain blocked. This also applies to the original transaction's guard revisit.
- Stable owned zero-slot menus produce a distinct unavailable observation. The
  discovery worker verifies the native snapshot and process/building identity,
  records that candidate as unavailable, and continues. It does not count an empty
  roster or claim complete coverage. Stale, partial and contradictory observations
  still stop discovery.

Reviewed native routines: list selection RVA 0x613520, mapped row activation
0x61c7f0, clamped list scroll 0x612660 and its layout routine 0x612cf0. No packet
replay, remote-thread execution or host memory writes are introduced.

Validation: 167 focused host tests and changed-file lint passed. Native funding
and navigation fixtures passed with realistic separate list-selection/resource
activation, existing selection, clipping, changed ownership, failed reveal and
lost admission cases. Complete native compilation and exact-source package checks
are next. No new live automatic spending acceptance is claimed.

Active todo: complete package validation and stage this combined correction,
then activate after user closure. The user launches Vendor Test and initializes
View Resources once after login. Next qualify the complete funding/upgrade cycle
and continue discovery. Full-town coverage, maximum rank, removal of the initial
manual warehouse prerequisite and integration remain unfinished.
