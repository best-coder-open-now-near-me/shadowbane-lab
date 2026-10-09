# Automatic preparation fault recovery

An unexpected exception while the preparation service owns native resources used
to reserve the same handoff flag used by finite worker operations. Even after
positive native cleanup, that reservation remained set; without a corresponding
finite operation, nothing released it. Enabled upkeep could then remain disabled.

The service now records an internal recovery request separately. It retains the
original owner, makes one passive finish request, and uses the existing exact
closure inspection while that request remains unresolved. Only positive closure
and completed resource disposal clear the internal request. A later cycle reads
current intent and worker authority before acquiring a replacement owner.
Concurrent finite-operation handoff, failed finite cleanup, Pause/Stop, and
permission loss retain their existing authority. Ordinary native manual-action
deferral does not trigger this recovery or force cancellation.

The first fault detail remains visible while cleanup is pending. A status getter
exception cannot terminate the service's exception-reporting path: it reports
cached presentation while retaining the owner for cleanup. A reserved finite
handoff reports `yielding`; blocked worker dispatch reports `paused`. `disabled`
is still used when saved buff settings cause the factory to return no owner.

Deterministic service-loop tests reproduce the old permanent handoff and cover
late closure, concurrent finite handoff, explicit control, failed cleanup,
repeated inspection failure, status getter failure, and manual deferral. The
live .85 observation is consistent with several paths; its initiating exception
has not been established. This change is host-only and is not an installed/live
acceptance claim.
