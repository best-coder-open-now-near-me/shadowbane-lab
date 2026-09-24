# Explicit saved attack-list combat - September 24

Design checkpoint against main `a91dfd5`. No native combat implementation,
installation, server acceptance or live fight is claimed. Response-driven
retaliation remains separately blocked on server session ordering across buffered
input; explicitly saved player entries do not need that response authority.
Private exact-image disassembly and evidence manifests remain local.

## Qualified entry and exit

Ordinary action 1551 performs the client's native player, peace-zone and state
checks, retains the target and constructs a melee request before ordinary send
and follow-up behavior. The action dispatcher returns handled even when those
checks reject the action. Its return cannot establish submission or damage.
The selection setter consumes its incoming reference. Hold separate actor/target
references, transfer one extra target reference, then recheck current identity,
scene, operation, list membership and party protections after selection callbacks.

Clear Target only clears selection; it does not clear the actor's retained combat
target. Ordinary action 1558 can exit combat when the fresh current mode is 2,
clearing the target and returning the action state to idle. Cooldown/state checks
can reject that exit. Blind toggling can enter combat. Cancel must first retire
queued extension actions, conditionally request exit, and verify the same actor,
mode 1, idle action state and null combat target before a new engagement.
Already submitted server work cannot be recalled by this local confirmation.

## Durable production boundaries

- Reuse the existing movement update's owner-thread services, lifetime watcher,
  movement Grant and native stop pipeline. A transport producer lease is a
  separate requirement, not combat permission. The generic action dispatcher
  currently runs on the transport worker and must remain rejection-only.
- Add a bounded typed combat queue and immutable per-request ledger. Exact
  process lifetime, scene, operation Grant, saved entry identity and list revision
  accompany requests. Reacquire the exact loaded player through retained native
  references; host pointers and names alone never authorize a target.
- Preserve native legality, complete fresh party protection and positive pet
  ownership evidence. Recheck immediately after selection and before entry.
  This scope accepts calibrated players only; existing NPC policy stays separate.
- Serialize list remove/clear with entry. Under the existing interprocess list
  lock, revoke registered pending admission tickets before publishing the new
  durable revision. Native entry atomically claims pending tickets immediately
  before invocation. An entry that wins the race is already in flight and needs
  cancellation; a revocation that wins prevents entry. Hold no file lock across
  game callbacks. Publish failure leaves authority revoked.
- Registration, mapping lifetime and mutation use the same owner identity and
  lock. Missing/replaced mappings or dead producer generations invalidate all
  tickets. A saved revision alone cannot protect a queued native action.
- Submission receipts correlate the exact owned melee request returned during
  this owner-thread invocation with the actual outgoing queue append. The send
  wrapper can silently drop when no sender exists. Ordinary return, serializer
  activity or unrelated messages do not establish enqueue. Queue evidence means
  local submission only, never server acceptance. Missing/ambiguous evidence is
  uncertain and must not trigger another attack request.
- Cancellation revokes future admission, composes the existing exact-owner stop
  pipeline with conditional combat exit, and blocks replacement engagement until
  local exit is confirmed. Stale stop requests cannot affect a newer owner.
  Host restart/lease loss does not resume an old encounter or replay uncertain work.

## Implementation and acceptance sequence

The exact outbound-container append slot is now qualified: ArcServerWrite's
constructor owns queue+0x40, uses the reviewed deque container, and appends through
its owned-reference thiscall slot. A scoped observation can correlate the exact
melee request at that concrete append boundary. This is an implementation
contract, not an installed hook or proven attack submission.

Earlier notes mistook that outbound writer construction for receive-wrapper
replacement. That claim is withdrawn. Read-ahead and the missing server-session
fence remain supported; ordinary paired read/write ownership proves no replacement.

Next agree the shared wire/admission-fence contract. Native ownership then covers execution,
receipts and cancellation; host ownership covers exact saved-player resolution,
store mutation fencing and runner transitions. Shared transport and movement-owner
edits have one integration owner.

Deliver one full transition: current PvE work cancels, a listed player is freshly
acquired, native basic attack is admitted, bounded engagement exits, and fresh
health/resource/camp checks precede PvE reacquisition. Interruptions do not increment
kills. Existing supported PvE/power dispatch is not silently replaced with an
unqualified native route.

Validation must cover remove/party join/manual takeover inside selection callbacks,
entry/revocation races across processes, crash around durable publication, owned
reference failure, cooldown rejection, mode changing before cancellation, stale
attack/stop, pointer reuse, dropped receipts and duplicate request IDs. Preserve
existing movement and attack-list command regressions. No fight is needed for
these source contracts; a later coherent package needs supervised acceptance.
