# Katana moon-fire — October 8, 2026

## Scope and current state

One locally rendered katana with white moon-fire; no sheath/combat mode switch,
cosmetic equipment manager, or server gameplay change. This work is **not an
installed or visually accepted weapon effect**.

The main checkout's extension particles attach to an actor root, not a weapon.
Its scene-composition authority still returns false. The unmerged particle branch
69d7717 contains a scheduler but no enabled weapon attachment. Do not turn the
composition gate on to manufacture a successful demo.

Native client visuals offer another candidate route. The shipped Visual.cache
contains particle color curves, texture references and numeric attachment values.
Those values are not yet correlated with the test sword's live attachment. The
inspected local CObjects cache has no name containing Katana or Archon's Blade.
Names such as Minatoan Broadsword are candidates, not established katana identity.

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

1. Active: identify the user's test katana/client and its native render/effect binding.
2. Establish the exact texture and blade attachment, then build the narrow local override.
3. Validate in-game appearance, occlusion and movement; capture the actual result.

Awaiting the user's weapon choice (Archon's Blade, an ordinary owned katana, or
no katana yet). Do not assume an arbitrary numeric particle bone is a sword bone.
Source is published on codex/katana-moonfire as unfinished work targeting main.
The normal project checkout stays on main; this branch is isolated from the
Companion/report work in PR #101.
