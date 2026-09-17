# Warehouse return ownership: 1.8.12 / 0.3.21

Branch: codex/guard-upgrades. Integration destination: codex/vendor-rolling,
then codex/native-lifecycle-hardening, then reviewed main. Not merged; the normal
main checkout remains untouched. This source follows installed 1.8.11 / 0.3.20.

## Behavior

Live observation confirmed that the active warehouse resource panel retains the
exact Seneschal NPC while the guard tower management menu is in front. Returning
to resources now uses that owned NPC instead of looking for it in the building
spatial query. The source is reacquired from the native HUD snapshot on every
command; no pointer cache survives a menu/scene change.

The window-owner thread recaptures the active HUD list, exact scene and request
lease, foreground state, and the warehouse building's complete owned hireling
roster. It validates the resource HUD class, NPC class and full typed identity,
temporarily retains the NPC using the reviewed warehouse setter's virtual-base
adjustment and AddRef, and applies the ordinary interaction-range predicate.
Admission and source ownership are checked again before the ordinary resource
opener. Both range/open callbacks borrow the temporary reference; cleanup uses
the native release helper. Callback faults quarantine uncertain ownership and
disable further target operations. No retry follows uncertain submission.

The initially selected warehouse panel must remain active. Closing it requires
opening View Resources again; the worker cannot silently substitute another NPC.
Money and upgrade deadlines, exact quotes, reserves, two-sided balance checks,
and durable spending/request records remain unchanged. No wire format changed.

## Validation and remaining work

Focused native ownership and HUD snapshot tests passed, including no spatial NPC
result, wrong/missing/replaced sources, stale admission, failed range, retention
fault, opening fault and old HUD closure during opening. Full package validation,
activation and live return qualification are pending.

Active todo: package and stage the coherent runtime update, then activate after
game closure and qualify a warehouse return. Next: the complete live funding and
guard-upgrade sequence. Positive maximum-rank evidence, full-town coverage and
review/integration remain unfinished. No automatic gold transfer or guard upgrade
has been submitted during this qualification. Retain all old unresolved requests.
