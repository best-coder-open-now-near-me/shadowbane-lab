# Warehouse return ownership: 1.8.12 / 0.3.21

Branch: codex/guard-upgrades. Exact packaged source: 27c7288 (pushed).
Integration destination: codex/vendor-rolling,
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
fault, opening fault and old HUD closure during opening. The exact-source package
passed 2,675 host tests (18 skipped), whole-source lint, required native tests in
both profiles, actual reviewed-image binding, real IPC and installed entry-point,
panel and wire checks. Six extra installed guard/funding comparisons passed.
All 61 package artifacts and the archive were independently hash verified.
Two pre-existing stretch transparency diagnostics remain unresolved per profile;
this is a diagnostic qualification package, not whole-product acceptance.

The full DLL and host package are activated after confirmed game closure. The
idle test manager was restarted automatically; the user did not need to close
its window. The same desktop game shortcut launched the exact verified full
1.8.12 extension, and the dashboard shortcut now uses host 0.3.21. Loaded DLL
version/hash, installed host source, healthy guard-capable manager and matching
read-only action-channel process identity all passed. All 108 retained records
and settings were unchanged; rollback copies and private verification receipts
remain local. No game action was submitted during activation.

Active todo: user login beside the Seneschal and initial View Resources opening,
then qualify automatic warehouse return. Next: the complete live funding and
guard-upgrade sequence. Positive maximum-rank evidence, full-town coverage and
review/integration remain unfinished. No automatic gold transfer or guard upgrade
has been submitted during this qualification. Retain all old unresolved requests.
