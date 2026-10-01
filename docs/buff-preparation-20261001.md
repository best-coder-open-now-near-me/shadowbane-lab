# Automatic buff preparation - October 1, 2026

## Scope and source status

The user authorized automatic application and refresh of missing concentration
potion, Precision, Beorc Rune, Transform and Defensive Stance effects. This record
captures requirements, native read-only findings and the intended production
boundaries. **The buff module is not implemented or live-qualified.**

The focused branch is `codex/native-buff-preparation-20261001`, based on
`7f37ff53e181288ce1ae695f2e2699ecf2bb8ff2`, the reviewed source head of
[PR #58](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/58).
It depends on that PR's [native service ownership changes](native-owner-liveness-20261001.md).
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

The effect audit distinguishes the primary descriptor identity from the
`ArcPowerAction` definition identity in the record. Neither can be assumed equal
to a learned power ID. ApplyEff, ApplyEffs and Transform paths link action
information to effect descriptors; observations must preserve repeated records
and source tags. A complete, consistent collection and its reset/full-update
boundary still need qualification before an empty result can mean missing.
Expiry and duration semantics remain unqualified. Queue receipts prove local
submission, not effect presence, server acceptance or duration.

For the inspected ordinary item-use branch, native code constructs an
`ArcObjectActionMessage` with subtype 2, operation 1 and the exact item key,
queues it and returns without changing the actor's mode, action or AF8 in that
branch. This supports separating local submission from delayed application.
It does not yet qualify concentration-potion use: its exact template flags/type,
actor-owned inventory lookup and retained item lifetime must be proved first.
Existing vendor HUD inventory and crafting deposit decoders do not provide that
ownership proof.

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

## Finite next steps

1. **Active:** qualify actor effect coverage/absence, exact potion inventory/use,
   actor-only authority and action-specific pending/cleanup semantics together.
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
