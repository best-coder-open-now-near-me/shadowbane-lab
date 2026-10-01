# Automatic buff preparation - October 1, 2026

## Scope and source status

The user authorized automatic application and refresh of missing concentration
potion, Precision, Beorc Rune, Transform and Defensive Stance effects. This record
captures requirements, native read-only findings and the intended production
boundaries. **The buff module is not implemented or live-qualified.**

The focused branch is `codex/native-buff-preparation-20261001`. Its dependency,
[PR #58](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/58),
is merged into main at `8fa16aa`; this branch has incorporated that merge. The
qualified ownership package retains source `7f37ff53e181288ce1ae695f2e2699ecf2bb8ff2`.
See the [native service ownership changes](native-owner-liveness-20261001.md).
The installed .62/.42 subsequently passed bounded two-encounter recovery and
native reuse-blocked opener fallback. That combat gate does not qualify buffs.
This dependency does not establish a buff action, actor-only authority, effect
observer or potion inventory resolver. Main inclusion, package qualification and
installation remain separate delivery gates recorded in the [branch map](git-branch-map.md).

## Required behavior

- Apply missing configured buffs and refresh them from qualified native evidence.
  Do not repeatedly cast an already active effect.
- The user reports that a concentration potion applies after roughly ten seconds.
  This is an application delay, not an effect duration or a required wait before
  other buffs. Keep its pending application separate from active effect presence;
  permit other native-ready buffs during that delay. Elapsed time alone never
  confirms application or permits another potion.
- Defensive Stance is a learned ability. Do not add a host-side combat-mode
  prerequisite or substitute the combat-mode toggle for the ability. Native
  definition requirements and current native admission remain authoritative.
- Transform is one coverage group: either Rat Shape or Skree'ekt Shape satisfies
  it. When neither is present, choose a qualified, currently ready alternative.
  The user reports cooldowns roughly twice each form's duration; these estimates
  are not scheduling constants or permission to recast. Do not replace an active
  form merely because the other becomes ready.
- Preserve legitimate actions already in flight. No fixed cast sleeps, hotkeys,
  UI selection, system-message parsing or simulated effects may drive this path.

## Native observations and remaining qualification

Passive learned-power observations for Umbra on Wonderbane identified:

| Intent | Native power ID | Observed rank |
| --- | --- | --- |
| Precision | `429545819` | 40 |
| Beorc Rune | `429590426` | 19 |
| Defensive Stance | `676005819` | 40 |
| Rat Shape (`WRT-001`) | `429513599` | 20 |
| Skree'ekt Shape (`WRT-002`) | `429415295` | 20 |

Precision, Beorc Rune and Defensive Stance were observed as category 0, target
mode 2, delivery 0: actor-directed powers. These are character observations,
not universal learned-rank defaults. Resolve and validate the current exact
character's definitions and positive learned ranks at run admission. The form
alternatives also require their exact supported native definition and effect
mapping before activation. No concentration-potion item identity is qualified by
this table.

A fresh read-only capture from the verified .62 process resolved these coverage
candidates through native action definitions:

| Power | Effect descriptor / Transform marker |
| --- | --- |
| Precision | `496654667` |
| Beorc Rune | `496699274` |
| Defensive Stance | `743114667` |
| Rat Shape | Transform marker `496622447` |
| Skree'ekt Shape | Transform marker `496524143` |

Use the actual Transform markers for alternative-form coverage, not a conjunction
of their auxiliary ApplyEff records. Native stance requirement was 3 (either
stance) for Precision, Beorc Rune and Defensive Stance; the forms were 2
(peace-side native mode). These definition requirements are distinct from the
Defensive Stance buff. The diagnostic captured 20 effect records, with none of
these five markers, but it explicitly does **not** authorize an absence or expiry
claim. Descriptor retention flags and mutation-safe publication remain to qualify.
The inventory component rejected an identity mismatch and remains unknown; this
is not evidence of an empty inventory or a missing concentration potion. No buff
or item action was sent by that capture.

The effect audit distinguishes the primary descriptor identity from the
`ArcPowerAction` definition identity in the record. Neither can be assumed equal
to a learned power ID. ApplyEff, ApplyEffs and Transform paths link action
information to effect descriptors; observations must preserve repeated records
and source tags. The local actor uses derived effect handlers: add skips
certain descriptors, so selectors must be proved observable in that collection.
An equipment-linked path also prunes records inline. Rebuild clears records before
callbacks reapply them; equal passive rereads can therefore observe an intermediate
empty list. Authoritative absence requires owner-boundary publication excluding
all qualified mutation/rebuild paths, not just a double-read. Transform membership
changes bracket model changes; appearance is not needed as authority.

The inspected remaining-time getter does not remove expired records and can
return a small positive value after a deadline, or a sentinel for unsupported
records. It is not expiry authority. Queue receipts prove local submission,
not effect presence, server acceptance or duration. Coverage/expiry publication
remains unqualified.

For the inspected ordinary item-use branch, native code constructs an
`ArcObjectActionMessage` with subtype 2, operation 1 and the exact item key,
queues it and returns without changing the actor's mode, action or AF8 in that
branch. This supports separating local submission from delayed application.
This branch is restricted to the inspected template flag and ordinary item types;
special UI-use branches are excluded. The actor's inventory interface has a
qualified lookup path through its containers, returning an owned reference under
the native lock. Reuse that path and release the returned reference; vendor HUD
pointers and crafting deposit decoders are not substitutes. Positive exact-request
append, not the native return register, must prove enqueue. Incoming quantity
changes do not prove delayed effect application.

Actual concentration-potion template metadata, branch eligibility and its effect
mapping still require evidence. The qualified generic lookup and sender paths do
not by themselves authorize an unidentified item.

## Production integration contract

Use one canonical native effect/inventory observation source, bound to the exact
character session, process lifetime and actor identity. Policy, diagnostics and
native admission must agree on identities and freshness. A rejected, partial or
changing snapshot is unknown, not an empty inventory or a missing buff.

Preparation policy belongs beside PvE policy, with generic configured coverage
groups and action alternatives. Keep coverage state (present, missing, unknown)
separate from action disposition (never entered, queued, uncertain) and pending
application. A pending potion application must suppress duplicate potion use
without becoming a global queue barrier. Native readiness decides whether each
other action may enter. Entered uncertainty retains the original immutable
request; it never becomes permission for a fresh retry. A bounded observation
deadline may report unresolved application but cannot fabricate success or
silently consume another item.

The current combat proposal and fence require an NPC or listed-player target.
Even `SELF_POWER` carries that engagement binding. Preparation before combat
therefore needs explicit actor-scoped authority; do not supply a fake NPC,
nullable combat target or self-target workaround. Extend the shared native action
owner and coordinator coherently. The existing cleanup registry permits one
obligation per exact Grant, so a second independent coordinator cannot acquire
parallel cleanup ownership. Preserve per-action records inside the shared owner,
with native-qualified handoff and stop semantics. Delayed remote application is
not automatically a local stop obligation or proof that local cleanup finished.

The proposed protocol separates three lifetimes:

| Scope | Identity and responsibility |
| --- | --- |
| Parent actor owner | Exact client/Host/Grant, scene, actor key/address and native name/server; one aggregate cleanup obligation. |
| Child context | Monotonic context ordinal and full binding digest; explicit actor-preparation authority or separately fenced NPC/manual-player target authority. Actor-only context has no target or list fields. |
| Action | Immutable context/request identity and tagged power-ID or concrete item operand; entry state, queued history and local continuation tracked independently of remote application. |

An item operand must bind its exact key, retained address identity and qualified
template identity; it must not be packed into a power ID or a fake target field.
Receipts correlate the complete operand as well as owner/context/request. Preserve
bounded replay histories and high-water rejection, including cancellation before
entry. New scope needs explicit capabilities and a versioned, tagged wire/fence
schema; freeze geometry and cross-language golden fixtures before implementation.
The existing fixed command/receipt/fence layouts must not be reinterpreted silently.

Keep one unresolved native entry/status sequence at a time, but allow independent
pending applications. For the qualified immediate item branch, exact append plus
normal return and owned-reference cleanup can settle local responsibility while
its remote application remains pending. A subsequent ready power needs no potion
wait. Attach combat target authority to the same parent owner without inserting
`StopActive` between preparation actions. Current bind already avoids a blanket
pause; its single target-bound runtime/context is the limitation being migrated.
Native action-specific continuation checks still govern handoff. Empty initiation
signals or an effect observation alone are not universal local-release proof.
Terminal cancellation revokes future actions across all child contexts before
settling native responsibilities; it cannot promise to recall an already queued
server application or erase its history.

The runner should arbitrate preparations and encounters from fresh observations.
Safety, unresolved command status and required cleanup retain priority; preparing
buffs must not cancel an unrelated legitimate cast. Permit independent pending
applications without concurrent, uncoordinated gameplay writers. Standalone and
manager maintenance continue to renew/check the exact lease and settle terminal
cleanup; they must not become background buff-submission threads. Preserve
foreground, manual takeover, scene and producer-lifetime protections.

Extend character-scoped `pve/settings.py` and the `pve-settings` command with an
explicit schema migration, retaining existing policy and opener settings. Save
intent only, using the current exact-owner checks, revision CAS and atomic write;
do not persist observed presence, timers or stale item addresses. Resolve native
identities through the current session. The common `_run_pve` composition is
already shared by direct CLI, listener and manager paths, so all should consume
the same settings and preparation implementation.

Expose each coverage group's observed state, pending action, native readiness
reason and last exact effect confirmation in trace/status output. Distinguish
queued from active, unavailable inventory from empty inventory, and unknown
observation from confirmed absence. Keep preparation accounting separate from
encounter kills, optional opener skips and server-effect claims.

## Migration and validation boundary

The shared migration touches Python `client_extension` wire/fence/channel/session
and cleanup ownership, `pve/native_combat.py`, model/runner/settings, the new
preparation policy and common CLI composition. Native counterparts are the v2
controller/runtime/entry/queue and v3 fence, channel dispatch, power observer,
qualified item entry and canonical effect publication. Existing NPC/manual-player
admission, lifecycle commands after capability loss, old-owner cleanup and
uncertain immutable-request behavior must remain covered during migration.

Required production-path regressions include pending potion plus ready powers
without duplicate consumption; Transform alternative coverage; reset/prune and
unsupported-descriptor snapshots remaining unknown; exact actor/context/item
replacement; no fresh submission after entered uncertainty; independent context
revocation; and aggregate terminal cleanup without fabricated remote cancellation.
Cross-language wire fixtures, native owner-thread tests and real channel tests
must cover actor-only actions without an NPC. Settings migration/CAS and direct,
listener and manager composition must use the same policy and observations.

## Finite next steps

1. **Active:** obtain actual concentration-potion metadata/effect mapping and
   qualify native observation mutation/rebuild publication. Finish actor-only
   authority and action-specific continuation/cleanup proof against those facts;
   these evidence dependencies currently block implementation and live use.
2. Implement one complete native/host preparation slice: canonical observations,
   shared owner and receipts, policy, saved settings, runner and status output.
3. Validate potion overlap without duplicate use; either-form coverage and native
   readiness selection; changing/unknown snapshots; uncertain request replay;
   foreign casts; actor/Grant/scene replacement; cleanup/handoff; settings migration
   and direct/managed parity. Use production paths with controlled native fixtures,
   not simulated live-effect success.
4. Complete review and exact-source package gates, then bounded live acceptance
   with current character/item/effect evidence. Claim each buff only when its
   qualified native effect is observed; retain unresolved outcomes honestly.
