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
All five buff groups were present afterward. Track copied Pro's contact and
closed its automatic window. No replay of the consumed command was issued.

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
movement geometry. Host correction, combined package qualification, installation
and a new live `/come` acceptance remain pending. These source tests do not claim
that the updated runtime is installed or that the live route has completed.
