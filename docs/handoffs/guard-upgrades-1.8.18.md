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

Validation: 328 focused host tests and native controller/navigation fixtures pass.
Regression cases
cover a dropped first response followed by confirmation, two-second pacing,
three-request exhaustion, fixed deadline, changed replacement HUD/debit/guard/
scene/building/producer/window, lost live admission, uncertain callbacks, stopping
after confirmation and no repeated Upgrade.

Exact source `826de6a0909f36360ad31fdd64879728b50492fd` is pushed to
`origin/codex/guard-upgrades`. Its full package passed 2,700 host tests (18 skipped),
lint, both native builds/suites (163 registered each, three context skips each),
prepared-client bindings and installed contracts. Six additional installed
native guard/funding wire checks and two return-receipt roundtrips passed. All
61 artifacts and the archive digest were independently checked. The two known
graphics transparency stretch diagnostics still fail in each profile; this is
a diagnostic package, not complete product acceptance.

Full extension SHA-256:
`c51e527735044814eea1b3c5129b540bc7e229a8120de7ccb788d2a2b6add8ce`.
Host wheel SHA-256:
`2001748a15e7036535bf50e66c7c1f5406721cd6f1a0e71af7a8d0680520b5b1`.
Diagnostic archive SHA-256:
`04122afe7cb957909e7a1e93d53b0306aa562fda72fe90e93fd2e055e8628751`.
Guest preparation and read-only update validation passed. The separate host
0.3.27 installation and exact source/artifact pins were checked. The loaded game
still has the original 1.8.17 extension; its files and journals are unchanged.

Active todo: apply the verified correction after user-confirmed game closure.
After activation, the user launches Vendor Test and opens View Resources once.
Use a fresh process-bound discovery plan; preserve the old reviewed job and
request without replay. Verify the full batch, including rank waits and available
gold. Full-town coverage, maximum rank and integration remain unfinished.
