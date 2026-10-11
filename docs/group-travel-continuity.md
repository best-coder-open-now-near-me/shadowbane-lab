# Group travel continuity - October 10, 2026

## Observed failure

The installed host .99/native .64 received and admitted Pro's fresh `/come` from
Umbra's current group. Two native route submissions succeeded. Travel stopped
before arrival when the native update interval reached 266 ms: the controls'
250 ms discontinuity rule revoked the automation grant as `stalled`. The user
observed the stop when Pro came into view. There was no recorded manual takeover
or group change. Arrival radius was 75; the post-terminal distance was about 422.
The command admission expiry is not the active travel deadline.

Private correlated evidence is
`artifacts/bot-deploy/20261010-group64/listener-ready/come-result-index.json`,
SHA-256 `205e7d504799fbaa5f47f8b263e11187ecde69a999834ce00404206b8cf906ab`.
The passive capture began after the terminal event; the native boundary trace
and worker travel output provide the correlated movement and revocation evidence.
All five buff groups were present afterward. Track copied Pro's contact. The
separate prior readiness capture, `listener-ready/readiness-234954/index.json`
(SHA-256 `4782aecf7343b413c057a366aaa3b5b1f403afc6e721ef6714b2ed8d2bf52501`),
records the automatic Track window absent. That presentation observation precedes
this command; it is not a HUD capture during travel. No command replay was issued.

## Ownership boundary

Host .100/native .65 replaces the activity-specific frame-gap exemptions with
one exact acquired-owner lease check. Moving, paused, newly acquired and service
operations use the same authority: the current grant and scene, owning thread,
live producer process and current producer heartbeat/generation. The existing
producer lease timeout is unchanged. Client frame spacing does not expire a
live operation, resend a destination or resume a paused route.

Native cleanup remains an independent obligation. A failed stop blocks new
writes until the exact cleanup succeeds; retaining the operation grant does not
mark that cleanup complete. Scene changes, unavailable native bindings, focus/UI
loss, text entry, clock regression and producer loss still retire authority.
Fresh configured player intent takes over even when a delayed frame lacks the
camera basis or terrain pick needed to issue a manual move. Camera integration
still discards elapsed time across a discontinuity.

The host companion preserves the first travel stop cause instead of replacing
it with a generic priority/dispatch message. User cancellation and actual runtime
failure must retain their respective terminal classification.

## Validation and remaining work

Native checkpoint `d0bd80b013433848889f6f9a1d3f4170d3edd201` passed 40 focused
controls/runtime cases and independent review. Regressions cover the observed
266 ms active-route gap, pause and explicit resumption, service completion,
pending cleanup, producer loss, and fresh manual takeover without usable native
movement geometry. Host `1e2a0890` passed 92 focused tests with one optional native-fixture skip,
including 14 stop-cause cases also independently rerun. Its real runner-to-CLI-to-
worker regressions cover explicit cancellation, interruption and cleanup failure.
PR #160 is merged after all 15 hosted checks passed. Exact .100/.65 composed
package qualification and activation also passed. A new live
`/come` acceptance remains pending. These tests do not claim that the live route
has completed. See [the delivery record](group-travel-delivery-20261010.md).


## Admission authority correction - October 11

A later .100/.65 run received Treehugger's `/come`, admitted its exact destination,
and failed before any route submission with
`group command permission changed; native_movement_owner_revoked`. Sampled group
identity remained stable. Private evidence is
`artifacts/bot-deploy/20261010-group65/listener-ready/come-result-index.json`,
SHA-256 `663e979a358dc60cfe7d133054276f547b48388728f33049b71cd68be5a8cb2a`.
The capture does not identify which host permission predicate failed at the exact
supervision tick, nor prove that the host check caused the native revocation.

The demonstrated host defect is independent of that uncertainty: the same
unchanged group observation permits a command at age 500 ms and rejects it at
501 ms. Worker supervision reused this admission check after execution began,
so delayed or unavailable passive observation, or a whole-roster change, could
terminate an already authorized one-time operation.

Host .101 keeps fresh current-member authorization at claim and immediately
before queued execution. The claimed `/come` destination remains fixed; running
work no longer leases authority from observer age or the roster digest. Explicit
Pause, group-command disable, Cancel/Stop and fresh-command preemption remain.
Exact worker/game/scene/native ownership and player-attack target protections
continue through their existing execution boundaries. No timeout or native code
changes are included; native remains .65.

The observer acknowledges a consumed command before processing later frames,
so an active or completed command is not subsequently described as having expired
before admission. Acknowledgement and observation publication share the service
lock; durable consumption writes occur outside it so disk I/O cannot block the
worker's setting read before native maintenance. The observer remains the sole
policy writer, and acknowledging an older command cannot discard a newer one.

Focused validation passed 116 tests, including the actual worker serve loop and
maintenance with stale/unavailable observation and changed roster, pre-execution
rejection, explicit cancellation/disable, native failure, consumed status and
blocking persistence. This source correction still requires composed-package
qualification and a fresh live command; it does not establish successful arrival.
