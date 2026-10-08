# Katana moon-fire — October 8, 2026

## Scope and current state

One locally rendered katana with white moon-fire; no sheath/combat mode switch,
cosmetic equipment manager, or server gameplay change. The model-only appearance
swap has received the compression compatibility repair and is installed for a
new live check; hand alignment is not yet visually accepted. The moon-fire effect is not installed.

The main checkout's extension particles attach to an actor root, not a weapon.
Its scene-composition authority still returns false. The unmerged particle branch
69d7717 contains a scheduler but no enabled weapon attachment. Do not turn the
composition gate on to manufacture a successful demo.

Native client visuals offer another candidate route. The shipped Visual.cache
contains particle color curves, texture references and numeric attachment values.
Those values are not yet correlated with the test sword's live attachment. The
initial host-local cache lacked Archon's Blade; the patched test VM now contains
it, as established below. The host-local installation is not the test target.

## Delivered tool

`python -m shadowbane_lab.client_extension.native_visual <Visual.cache> <resource> --group 0`
inspects one exact native visual and reports its digest and typed effect headers.
Unknown effect types, opaque data, nonfinite timing, truncation, and trailing bytes
are rejected. Numeric bone values are reported without invented semantic names.

For an identified particle, add `--tint-effect <index> --source-sha256 <digest>
--output <new-payload.bin>`. The tool produces a standalone candidate payload with
cool-white RGB keys and preserves every other byte, including alpha, timing,
texture, attachment and other effects. Exclusive creation prevents overwriting
an existing file. It does not rebuild or install any cache. A colored source
texture can still tint the result; this is not an appearance guarantee.

The binary layout reference is MagicBane's
[mbEditorPro ArcVisual.py](https://repo.magicbane.com/MagicBane/mbEditorPro/src/commit/75efa29012592d7d0e35ebfd0703990f90f10995/mbEditorPro2.0/arcane/ArcVisual.py).
The production code is a bounded implementation of the format, without importing
that editor at runtime. The editor checkout used for comparison remains an
ignored research input.

## Qualification

Local Visual.cache SHA-256:
cf25abc2af9dd0d5818b3882506569f7809aa0799574f9cf01fdcf2f3ce47465.
All 478 interpretable records matched the pinned editor's effect count, particle
texture references and attachment values. Five opaque records were rejected.
All 1,169 individually tinted particle instances were independently decoded and
re-encoded byte-for-byte by the editor, with alpha curves preserved. These are
format checks, not native renderer or in-game acceptance.

Twelve focused parser/byte-preservation/navigation tests and Ruff passed.
Private evidence and research scripts are under artifacts/moonfire in the
katana-moonfire worktree. Source delivery contains no proprietary cache payloads,
client binaries, credentials or captures. The active client was not changed.

## Next work

1. Complete: identify Archon's Blade in the patched test VM and preview its mesh/texture.
2. Complete: build and inspect an animated sparse square-chain browser study.
3. Active: correlate native particle attachment and translate the study into the client.
4. Validate in-game appearance, occlusion and movement; capture the actual result.

The user has designated a logged-in test character. Read-only inspection confirms
the running test installation has the model/render/effect assets used by the preview.
The exact equipped stand-in item has been identified and an offline appearance candidate verified. Do not infer bone semantics from
numeric values alone.
Source is published on codex/katana-moonfire as unfinished work targeting main.
The normal project checkout stays on main; this branch is isolated from the
Companion/report work in PR #101.

## Patched test VM asset and preview

Read-only inspection of the official client at
C:/Users/tester/Downloads/WonderbaneClient/Wonderbane in shadowbane-testing found:

- CObject 0:7307: Archon's Blade; primary render 0:9996101.
- Render 0:9996101: RHELD target, mesh 0:29243, texture 0:8029210, no children.
- Mesh: 40 vertices, 41 triangles. Its payload is unchanged from the host-local cache.
- Blade texture: 256 by 512 RGBA; particle texture 0:9996401: 256 by 256 RGBA.
- Visual records 0:16503 and 0:16504 changed alongside this item/render. Both have
  twelve particle entries referencing texture 9996401, with attachment values
  4/3 and 15/14 respectively. Their runtime association remains to be verified.

Input receipts (hashes before/after read agreed):

| Cache | SHA-256 |
| --- | --- |
| CObjects | 4df20426f0809779b28a4a9769ebf94fc1a02d6598e216f3a1b199ffb08b4804 |
| Render | 9c8be6cc6e1b766c4a2e005460fc6bad4ef46e453a7b151770ca6c45e700564e |
| Mesh | 136f6625faa98a13378274d044d2d5f6920babbb1cb84f2547ecdacbc24e4993 |
| Visual | d27e52b056060975bd95cf8bb1baefde98765ca2ddaf8a80de1380ed0931aafb |

Existing ignored graphics-work scripts support GLB exports, texture extraction
and Blender reference renders. Graphics Lab is an in-game control panel, not a
model browser; the Texture Lab UI described in the facade doc is unfinished.
No Blender executable was available at the checked locations in this session.

scripts/weapon-preview/build.py and archon.html provide a narrow self-contained
WebGL preview for this specific asset. Run with PYTHONPATH=src and three arguments:
Mesh.cache, the decoded texture-8029210.bin payload, and an output HTML path.
It needs Pillow while building; viewing needs only a browser with WebGL. It has
rotation, zoom, a lighting toggle and an explicitly preview-only exposure slider.
It does not reproduce native effects or lighting. No CDN or network asset is used.
Keep generated HTML private because it embeds original client mesh/texture data.

Geometry, UVs and indices matched the pinned independent decoder. Headless Chrome
rendered the generated page with zero page errors and GL error 0; the screenshot
was visually inspected. Private preview: artifacts/moonfire/preview/archon.html
in the katana-moonfire worktree. A temporary loopback server on port 8876 serves
only that preview directory. Source game files were not modified.

## Animated square-chain study

The self-contained preview now overlays one strand of camera-facing diamond
sprites along the blade, with staggered 1.8-second size pulses. Defaults are
100 percent size, 80 percent spacing and 35 percent pulse; bounded sliders, pause/resume,
and an effect toggle allow one visual comparison without an effect editor.
The blade chain runs from mesh Y 0.415 to 2.28, above the collar accent and below
the tip, with a small centerline adjustment. They are inspection coordinates,
not a claim about the game's bone coordinate system. The depth-tested pass does
not write depth and uses ordinary alpha blending; browser rendering does not
qualify native sorting, attachment, lighting or additive bloom.

The original mesh and texture are unchanged. Changing exposure affects only the
model inspection; it does not brighten the proposed moon-fire sprites. Animation
uses bounded geometry (at most 65 sprites and four collar faces), limits elapsed-time jumps, and pauses
advancement while the page is hidden. Context loss displays a reload message.

Headless Chrome acceptance passed animated-geometry change, pause/resume,
effect on/off pixel difference, size/spacing range controls, zero-pulse stability,
orbit/zoom/reset, lighting toggle, and zero WebGL/page errors. The screenshot was
visually inspected at 1200 by 850. The first old browser smoke test timed out on
the now-collapsed lighting section; opening that section in the updated acceptance
script resolved it. Evidence: artifacts/moonfire/check-moonfire.cjs and
artifacts/moonfire/preview/archon-moonfire.png. No client installation occurred.

## Collar accent

The preview adds a narrow white band at mesh Y 0.18–0.208 and a larger diamond
at Y 0.29. The band wraps the blade root with four model-space faces and softly
faded edges. At 100 percent sizing the anchor is 1.3 times the base chain width and pulses every
3.6 seconds, half the chain frequency. Both use the existing effect toggle,
pause and depth-tested pass; the pulse control includes the anchor. The anchor
now has its own size control. Original mesh/texture assets remain unchanged.

Chrome acceptance still passes. Additional checks confirm finite bounded
geometry, a steady collar while the anchor pulses, and error-free angled
rendering. Front and angled screenshots were visually inspected; private
evidence is check-collar.cjs and preview/archon-collar-angle.png under
artifacts/moonfire. This remains a browser study in draft PR #106 targeting
main. Next: prove native attachment and transfer the effect into the test client.

## Blade glow and hilt sizing controls

The hilt diamond has an independent 25–250 percent size slider (100 percent
preserves the previous default). Square size now adjusts only the blade chain.
Glow strength spans 0–150 percent with a selected default of 111; width spans 40–400 percent
with a selected default of 86. Strength zero disables both the blade surface emission
and its soft additive halo. The master moon-fire checkbox disables all accents.
Emission is masked above the guard using model-space height; it is independent
of texture exposure. The six-vertex halo follows the projected blade and scales
with zoom. This is an artistic browser approximation, not native bloom.

Chrome acceptance passed independent hilt sizing with unchanged collar/chain,
glow off/on and width pixel differences, slider extremes, front/back/edge views,
finite geometry, narrow sidebar access and zero WebGL/page errors. Existing
animation/control acceptance also passes. Front and angled screenshots were
inspected. Private evidence: artifacts/moonfire/check-glow.cjs and
preview/archon-glow-angle.png. Next remains native attachment and in-game transfer;
source is pushed through draft PR #106, outside main.

## Approved visual preset — October 8

The user approved the look and supplied a screenshot of all six controls.
These values are now the saved HTML defaults and the target for native translation:

| Control | Percent |
| --- | ---: |
| Square size | 100 |
| Spacing | 80 |
| Pulse | 35 |
| Hilt diamond size | 125 |
| Glow strength | 111 |
| Glow width | 86 |

A freshly loaded generated preview was checked against all six values and labels,
rendered without page/WebGL errors, and captured for visual inspection. Refreshing
now restores this preset. Native effect values will need calibration against this
appearance; browser glow percentages are not native particle parameters. Next:
prove weapon attachment in the test VM and implement the approved appearance.


Live baseline check: no client files, process memory or gameplay state were changed.
Detailed process provenance and screenshots remain private diagnostic evidence.
Next: identify the equipped sword resource, qualify the local appearance swap,
and then validate attachment and motion in-game.


## Qualified offline appearance candidate

`client_extension.item_appearance.build_item_appearance_cache` builds an exclusive
new CObjects candidate, bound to the source digest. It changes one item primary
render key to another item's key; all other target bytes and untargeted resource
payloads are verified unchanged. It rejects non-item donors, scale differences,
missing render references, duplicate resource keys, stale sources and existing
output paths. A failed candidate is removed; the source stays read-only.
The caller must qualify render dependencies, alternate render fields and attachment
before installation. This API neither installs nor modifies a running process.

The user named the same affixed sword in both hands. The exact item was found;
its primary render and the katana share the attachment label, scale and location.
Neither item has a female or low-detail alternate render. The candidate redirects
only that named subtype, including both equipped copies and any other copy of
that subtype rendered by this client. It is not a per-character override.
An independent full item decode confirms that only the primary render field
changes: stats and animation fields are identical. All 10,691 cache resources
were checked. This is a model/attachment qualification candidate; the approved
moon-fire still requires native effect work, not merely this reference swap.

Ten focused appearance/cache navigation tests and Ruff passed. The generated
candidate, receipts and exact target mapping remain private diagnostic artifacts.
Source is delivered through draft PR #106; no game files have changed. Next:
close the test client normally, apply the verified candidate against a fresh
baseline, then log back in to verify both hand attachments before effect work.


## Model-only installation checkpoint

After the user confirmed a normal game exit, installation rechecked that no game
process was running, matched the fresh source baseline, verified the donor texture,
and compared every candidate resource with the current guest cache. Only the
selected item's primary render reference differs. The cache was replaced via a
same-directory temporary file; no rollback copy was created.

The existing launcher pins package contents. Its package inventory was explicitly
updated for this one authorized cache replacement, with a recomputed tree digest;
all unrelated file records and executable/extension provenance were preserved.
A separate private overlay receipt records the derivation and source revision.
The installed runtime package verifier passes. Settings under Config and wasd
were hashed before/after and match. Temporary publication files were removed.
Exact deployment paths, hashes and diagnostic scripts remain private.

The model swap is installed but the game was left stopped for user login through
the same prepared-client launcher. Next: check both hand grips and movement on
the named character, then wire the approved native moon-fire. Restart success and
in-game appearance remain unverified until that login; no effect delivery is claimed.


## Compression compatibility correction

The appearance builder now preserves the target entry's source compression mode.
Offline payload equivalence alone does not establish native loader compatibility.
The regression test directly inflates stored target bytes, in addition to checking
all payloads and source preservation. Ten focused tests and Ruff pass. Live
acceptance remains pending; detailed diagnostic evidence is kept private.


The compression correction is now installed. Guest-side verification directly
inflated the replacement's stored bytes and checked the complete candidate,
then post-install package verification and settings-preservation checks passed.
The obsolete failed candidate was removed; compact diagnostic receipts remain.
Next: user login to confirm native loading and both hand grips. No successful
in-game result is claimed yet.


## Live proportions and remaining demo work

The user confirmed successful native loading and the katana appearance in game.
The next demo slice adds a Katana tab to Graphics Lab: overall length from 60 to
120 percent, Try 85 percent, and Reset to 100 percent. Width remains unchanged;
the transform is anchored at the existing model origin used for the hand grip.
Only the local character's two verified katana render instances qualify. The
native callback restores matrix and enable state after each supported draw; it
does not write actor, equipment, or render-object fields.

The process-specific channel validates identity, sequence and finite bounds.
The control begins at 100 percent on each game launch. Source tests cover both
hands, foreign instances, changed actor/context, malformed controls, bounded
render traversal and restoration. Native and host builds/tests are recorded with
the candidate; installation and live visual acceptance remain pending.

Active next step: qualify and install live proportions, then verify both hands
while changing length in the panel. After that, finish the approved sparse white
moon-fire and capture the katana demo. Keep draft PR #106 targeting main until
those live results are established.

After the katana demo: add a general Visual Inspector to Graphics Lab. Begin
with self/current-target render trees and resolve mesh, texture and effect
references through cache readers. Equipment slot/name mapping and door/scenery
selection need separate validation. This is deferred follow-up work, not part
of the current demo delivery.

Validation checkpoint: 47 focused host tests, panel construction/range checks,
and the full native build passed. Of 242 CTest entries, 237 passed, three private
image checks skipped without arguments, and the two documented transparency
diagnostics reproduced their reviewed counterexamples. The diagnostic classifier
passed; all three private image checks passed when supplied the reviewed images.
The final renderer/callback tests passed again after the lifecycle adjustment.
These results qualify a local demo candidate, not live visual acceptance.
