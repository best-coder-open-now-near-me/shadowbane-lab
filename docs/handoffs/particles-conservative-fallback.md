# Particles conservative presentation fallback

The integration owner approved conservative suppression for this candidate. Particles and
trails remain wholly hidden in ordinary client scenes until the shared scene authority can
establish safe composition. This is an explicit scope reduction, not ideal-transparency
completion. Existing ideal-transparency regressions remain diagnostic evidence.

## Integration

Feature base: `14d117e8c5194c6dff55dac608b2d3f683187d31`.
Feature branch: `codex/particles-trails`; PR #28 targets `codex/native-lifecycle-hardening`.
The integration owner supplies `IsWorldEnhancementCompositionSafe()` and passes its result
at the existing `DrawEffects(camera, transparency_safe)` callsite. The argument defaults
false, including for older callsites. Only shared authority may supply true. No inference
from final depth or missing trace events is permitted. Current shared authority returns false.

Effects use the existing 256-byte mapping. Config and eight statistics retain their offsets;
reserved words at offsets 156, 160 and 164 now hold safety schema 1, presentation state and
saturating suppressed-frame count. Presentation states: 0 disabled, 1 waiting for scene or
attachment, 2 composition permitted, 3 suppressed, 4 invalid settings. This status is published
under the existing status sequence. Requested enabled settings remain separate from actual
presentation. Older clients without safety status are labeled unavailable by the updated panel.

On unsafe authority, effects clear all particle, ribbon and pending geometry history, consume
the current burst token, and perform no attachment resolution or render callback. Suppression
is latched until an acknowledged valid disabled configuration or runtime restart; context
changes and alternating frame eligibility cannot release it. While latched, new bursts are
canceled. Re-enable cannot replay canceled bursts or old trails. Indicators, sky, navigation
and movement are unaffected by this feature-local decision.

## Required checks and candidate acceptance

Existing CTest `wonderbane_extension_effects_runtime` now directly exercises safe draw,
default-deny clearing, zero unsafe attachment/render callbacks, canceled bursts, alternating
eligibility, context replacement, explicit retry, status, counter saturation and shutdown.
It prints `conservative effects fallback executed` only after executing those cases; its exit
status still reflects every assertion. Require this test in both configured native profiles.
Python `tests/test_graphics_effects.py` covers mapping layout, requested enabled versus
suppressed status, actual panel polling, and disable behavior. Keep the existing ideal
transparency test unchanged and route it as diagnostic only through the integration owner's
explicit package policy; do not relabel its failures as passes.

Before live acceptance, the integration owner must reconcile the shared callsite, review the
combined source, execute required gates and build the exact package. In the connected client,
select an actor-root preset, apply Enabled and trigger Burst. With current authority, the panel
must say enabled but suppressed, show no particles/trails, and retain zero live geometry.
Disable / clear must report disabled once acknowledged. Re-enable must remain suppressed in
ordinary scenes; there is no user override for unsafe composition. Scene/context transitions
must leave no stale trails or delayed bursts. Verify other independently enabled features
continue operating. Visible particles/trails are not claimed for this candidate. No deployment
is authorized by this handoff.
