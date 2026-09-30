# Native object-target actions: architecture audit, 2026-09-30

Source architecture and qualification plan; power activation and shared action authority remain under review.
User direction: object-targeted melee and powers by native power identity; no hotbar,
hotkey, or selected-target adapter as the delivered production path. Current host
tracking/cleanup work can be checkpointed, but final packaging is held pending this
contract. No live client invocation occurred in this audit.

## Current source checkpoint

The explicit melee adapter now preserves the reviewed ordinary native attack
checks and call order while accepting a retained target object directly. It does
not read or write UI selection. NativeTarget and the submission observer use the
explicit route with exact actor/target keys and request-pointer queue correlation.
The native runtime pins cleanup once and enters the action without its former
unconditional startup pause/repin cycle. Explicit cancellation retains the same
owner and must still complete its cleanup.

A private-image probe compares the real ordinary1551 control flow with the adapter
across 2,048 guard combinations for both original and prepared client 1.3.38.12.
Helper boundaries are identically instrumented to compare ABI, order, output
ownership and admission outcomes; this does not execute real game/network effects
or establish live acceptance. Packaging runs this probe on both executable forms.

Power requests now have a shared outbound-queue observer registration with exact
scope ownership, distinct from melee factory tickets. The native power entry and
its callsite interception are being qualified; they are not activated. NPC policy,
the versioned common action contract and host semantic dispatcher remain next.
The installed bot is unchanged; no direct-object gameplay acceptance is claimed.

## Proven reusable boundaries

- The existing owner-update service, process-pinned callback registry, immutable
  movement Grant, producer lease, scene/lifetime watch, retirement, and explicit
  stop pipeline already provide the execution/ownership boundary. Reuse them; do
  not acquire another owner for each spell, run gameplay on transport workers, or
  toggle idle at startup or between ordinary actions.
- ArcWorld 1fcc80 resolves both words of an object key into a retained reference on
  the native owner thread. Keep persistent actor/target owned slots and explicit
  SEH boundary restoration; retain independently across native callbacks.
- Host population supplies object key plus pointer token, health, position, and
  structural kind/roles. The controller now separates engaged object from UI
  selection. UI selection and AF8 are observations, not universal spell targeting.
- Existing listed-combat wire carries exact actor/target keys and owner/request
  identity. Selection is not part of its immutable binding digest. The current
  former implementation selected because manual action1551 obtained its argument
  from the selected global. The qualified explicit adapter now replaces those reads
  while preserving that handler's native legality and ownership sequence.

## Original interfaces and required generalization

- NativeTarget.Identity requires both actor and target UUID class53 (players),
  complete names/server, and manual-list owner/entry proof. The 576-byte wire
  command and binding validation encode this player-list authority. NPCs must not
  be represented by fake manual-player entries, and action parameters must not be
  slipped into reserved bytes without an explicit versioned contract.
- Current runtime accepts one START until its engagement is cancelled. A spell is
  not another independent long-lived melee engagement, and its completion must
  not force melee cancellation or wait for a projectile to land.
- Submission observers recognize D0 only at return7d3e0b and CC only7d3e67, both
  from handler1551. The new explicit Scope route supplies separate call-through
  provenance and correlated queue receipts. Merely removing the selection check
  or recognizing every D0 on a TLS stack would weaken provenance.
- Binding() and AppendGate currently require the selected global. Replace that
  clause only for a separately qualified explicit-object entry, preserving exact
  actor/target keys, actual arguments, request class/payload, writer/container,
  ownership/retirement and the immutable native entry ticket.

## Durable composition to implement after native entry qualification

1. One owner-bound native action service receives typed semantic requests under
   the existing operation Grant. A request has immutable request ID, action kind
   (melee or a qualified native power identity), actor identity and target binding.
   Power rank/learned-state operands must follow the discovered native API; no
   hotbar index, key mapping, guessed power layout, or name matching.
2. Separate target authorization from action execution. Saved manual player intent
   uses the current exact list/fence proof. Ordinary PvE uses exact native NPC
   identity and current native eligibility/party/protected-role checks. Both feed
   the same owned target acquisition and action invocation machinery. Neither
   scope can be converted into the other by a caller flag alone.
3. Treat engagement ownership and each action submission as different lifetimes.
   The engagement retains the tracked object and cleanup obligation. Each admitted
   action has a bounded immutable request/receipt record, native legality result,
   and at-most-once submission. Repeated powers reuse the same Grant; they do not
   PAUSE, reacquire, or cancel the engagement merely to submit another action.
4. Invoke only a qualified ordinary native entry that takes the target object/key
   explicitly and preserves learned ability, resources, cooldown, range/LOS,
   peace-zone and native action-state checks applicable to that entry. Do not
   synthesize outbound packets or treat a raw factory call as equivalent to the
   complete native admission path without proving its preceding checks.
5. Observe the exact produced request reaching the real native outbound queue.
   Correlate its actual pointer and verified type/payload (including power identity
   where applicable), not just an actor or target match. Preserve native owned
   argument consumption and bounded no-lock append predicates. Unknown partial
   execution is uncertain; known queued history survives later faults.
6. Use native local mode/action/pending state for ability scheduling. Action-state1
   plus no pending action is a local completion observation, not proof of server
   acceptance, damage, projectile impact, or cast-target identity. Ongoing known
   combat may be adopted without modifying selection or issuing another attack.
   An unknown active target stays uncertain; do not invent one from UI selection.
7. Cleanup is explicit: abandonment, intentional replacement, owner stop, rejected
   lifetime, or task termination. Same-owner local stop confirmation preserves the
   existing stronger mode1/action1/nullcombat-target contract. Revocation prevents
   new admissions but cannot recall an already queued attack or spell.

## Required validation before replacing the keyboard path

- Native entry audit establishes exact melee and power call ABIs, complete checked
  preconditions and normal callers, output ownership, send/followup order, and
  synchronous reentrancy closure. Power identity and request layout remain open.
- Real reviewed-image conformance fixtures execute the qualified primitives where
  feasible, as the registry probe does. Mock-only ABI assertions are insufficient.
- Adversarial tests change selection while explicit target remains bound (no effect),
  reuse a pointer under another key (reject), revoke between admission and append,
  lose actor/scene, invalidate party/role, throw before/after append, and cancel a
  request before delayed delivery. A previous request cannot be replayed under a
  new power or target.
- Power tests separate local cast completion from delayed projectile effects;
  switching observation selection or beginning another eligible action does not
  manufacture a stop receipt or kill credit. Busy/unknown native state must not
  fall through to a hotkey fallback.
- Exact-image packaging/qualification and supervised live evidence follow the
  source tests. UI selection should remain unchanged by object-target execution.

## Present conclusion

Ownership and object lookup can be reused; the existing submission scope and
manual-list wire cannot be reused unchanged for arbitrary native powers/NPCs.
Melee control-flow equivalence is qualified; real helper effects and live acceptance
remain separate. Native power submission is still undergoing qualification. Keep the existing host checkpoint
accurate and do not label the selected keyboard backend production-complete.
