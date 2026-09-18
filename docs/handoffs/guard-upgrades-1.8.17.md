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

Source checkpoint: `1fb4c0c8ca9ee9225c2ae487bbe68e3e09d99814`, pushed to
`origin/codex/guard-upgrades`. The package is built from that exact checkpoint.

Validation: 167 focused host tests and changed-file lint passed. The complete
package passed 2,700 host tests (18 skipped), lint, both native builds and both
native suites (163 registered tests each, three context-dependent skips each).
Prepared-client bindings and installed entry points/contracts passed. Six extra
installed guard/funding wire checks and two guard-return roundtrips passed against
the actual compiled fixtures. Native fixtures cover separate list selection and
resource activation, existing selection, clipping, changed ownership, failed
reveal and lost admission. All 61 package artifacts and the archive digest were
independently verified. The two known graphics transparency stretch diagnostics
still fail in each profile, so this remains a diagnostic package, not full product
acceptance. No new live automatic spending acceptance is claimed.

Full extension SHA-256:
`a64c742ea3c0b06d1d3964529d9ffe2857d14d8cbf54fcf3fe5b4af2ffa4774f`.
Host wheel SHA-256:
`d9560a5bf47771de521819fca0fd9f50a87cb427bfcadd16b3cdac1bc87fd87a`.
Diagnostic archive SHA-256:
`6ad67457da3fec3c1745bf527e65ca03bbb5eb4d451037c727db7448e8877490`.

Guest preparation and read-only update validation passed. After user-confirmed
game closure, the combined update was installed and its extension version,
hashes, host source and launchable client package verified. All 249 retained
records/settings were unchanged after the manager restarted healthy. The
Dashboard shortcut now uses host 0.3.26; Vendor Test keeps the same reviewed launch
path. The game was left closed for the user to launch.

## Live manager qualification

The user-launched extension and replacement worker are verified. After the user
opened View Resources once, automatic warehouse building/resource return passed.
A diagnostic helper then rejected a withdrawal-reader call because no amount
quote was open; both navigation actions had already been confirmed and the
journal was idle. No navigation retry was required.

The production manager checked all 60 discovered candidate structures. It
verified 150 individual guard windows across 27 owned building rosters, recording
33 zero-slot/unavailable candidates separately. All six rows in populated guard
towers were reached. Its exact process-bound prepared plan was admitted normally;
full-town membership/coverage remains unverified.

The manager's maximum-rank job completed two full automatic cycles. Each confirmed
122,100 gold withdrawn from the warehouse, deposited into the tower, and debited
for the exact guard upgrade. The third cycle confirmed another 122,100 withdrawal
and deposit, then submitted its upgrade. Its automatic guard-return activation
was submitted once, but no guard window was observed before the 15-second native
deadline. The retained result ring shows IN_FLIGHT plus REOPENED until UNRESOLVED;
this was not an admission failure or a host transport timeout. A later read-only
observation found tower funds zero and the selected third guard row visible.
The user then opened the exact third guard's own page. Read-only capture matched
its process, building and guard to the original request, confirmed upgrade
progress and the exact zero balance. This establishes the observed live outcome;
it does not manufacture a native completion or clear the timed-out journal.

The job is stopped in review, with the third request and original submission
retained unresolved. No replay, journal reset or replacement spend was sent.
Confirmed cycle totals are 366,300 withdrawn and deposited; 244,200 of upgrade
spending is fully correlated. The third 122,100 debit and upgrade progress were subsequently verified on the user-opened page. The job's
completed-cycle counters intentionally do not yet include that active cycle.
A continuous read-only capture and stopped-cycle observations remain private
inside the VM. The recorder ended normally through its stop marker; its launching
guest-control wrapper timed out while the recorder remained alive.

Next: [bounded guard-page response recovery](guard-upgrades-1.8.18.md).
The existing timed-out request remains retained and is not replayed. Full-town
coverage, maximum rank, removal of the initial manual warehouse prerequisite and
integration remain unfinished.
