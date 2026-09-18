# Guard-page response recovery: 1.8.18 / 0.3.27

Branch: codex/guard-upgrades. Review into codex/vendor-rolling, then
codex/native-lifecycle-hardening and reviewed main. Not merged.

## Problem and behavior

The 1.8.17 manager discovered 150 guards and completed two fully automatic
funding/upgrade cycles. The third upgrade succeeded, but the single subsequent
page request produced no guard window before the original 15-second deadline.
Its submitted return request was visible in the native result ring throughout.
The user opened the same guard page and read-only observation confirmed both
upgrade progress and the exact debit. No second Upgrade was sent.

The native controller now allows at most three guard-page requests, separated by
at least two seconds, within the original upgrade transaction's fixed deadline.
Each requires the original producer/window, a fresh owned replacement-building
roster, the exact guard, the exact debit and an allowed rank. After the first
request, the replacement building HUD must also stay the same. The runtime
retains its lease, foreground, scene and ownership checks around scrolling and
activation. A valid guard response ends requests immediately. An uncertain
callback, wrong observed guard, timeout or contradictory balance remains blocked.
Only the non-spending page request may repeat after a submitted request produced
no page. Upgrade remains single-shot; original command submission receipts remain
immutable. There is no new wire format, spending retry, deadline extension,
journal reset, or recovery of an already unresolved live request.

Validation: 328 focused host tests and native controller/navigation fixtures pass. Regression cases
cover a dropped first response followed by confirmation, two-second pacing,
three-request exhaustion, fixed deadline, changed replacement HUD/debit/guard/
scene/building/producer/window, lost live admission, uncertain callbacks, stopping
after confirmation and no repeated Upgrade. Exact-source full package checks and
staging are next. The installed game still runs 1.8.17 / host 0.3.26.

Active todo: validate and stage this correction before requesting game closure.
After activation, the user launches Vendor Test and opens View Resources once.
Use a fresh process-bound discovery plan; preserve the old reviewed job and
request without replay. Verify the full batch, including rank waits and available
gold. Full-town coverage, maximum rank and integration remain unfinished.
