# Asset mod facade

The asset mod facade composes restart-oriented texture packages without exposing cache offsets or
letting package order decide conflicts. It is an author/developer foundation for the Texture Lab
and the future Control Center mod manager.

## Package layout

A schema-1 directory package has a canonical `mod.json` plus one build-specific reviewed texture
manifest and its PNG artifacts:

```text
restrained-forest/
├── mod.json
└── compiled/
    └── wb-55fbad5f-4b602995/
        ├── texture-patch.json
        └── textures/
            ├── 0-1706002.png
            └── 0-5000190.png
```

`mod.json` is the public package boundary:

```json
{
  "schema_version": 1,
  "mod_id": "org.shadowbanelab.restrained-forest",
  "name": "Restrained Forest",
  "version": "0.1.0",
  "description": "A restrained repaint of selected forest textures.",
  "components": [
    {
      "component_id": "textures",
      "kind": "texture-set",
      "activation": "relaunch",
      "variants": [
        {
          "content_build_id": "wb-55fbad5f-4b602995",
          "texture_patch_manifest": "compiled/wb-55fbad5f-4b602995/texture-patch.json",
          "artifact_root": "compiled/wb-55fbad5f-4b602995/textures"
        }
      ]
    }
  ]
}
```

The JSON Schema is `schemas/asset-mod-v1.schema.json`. The referenced texture-patch manifest keeps
its existing exact source-cache, source-payload, artifact, dimension, channel, and result-payload
hashes.

## Compile a profile

The initial API is intentionally programmatic while the Texture Lab and Control Center surfaces are
built:

```python
from shadowbane_lab.mods import (
    compile_texture_profile,
    load_asset_mod_package,
    materialize_texture_profile,
)

packages = (
    load_asset_mod_package(r"C:\Mods\restrained-forest"),
    load_asset_mod_package(r"C:\Mods\clear-signs"),
)
plan = compile_texture_profile(
    r"C:\Baselines\wb-55fbad5f\cache\Textures.cache",
    packages,
    content_build_id="wb-55fbad5f-4b602995",
    profile_id="visual",
)
receipt = materialize_texture_profile(
    plan,
    r"C:\ShadowbaneLab\texture-profiles\visual-v1",
)
```

Materialization creates a new directory containing `Textures.cache` and
`texture-profile.json`. It never modifies the pristine source cache. The candidate is published only
after the full cache parses, every selected result hash matches, and all untargeted resource payloads
remain byte-identical to the source.

The resulting directory is not automatically installed into a client yet. A later sandbox-session
coordinator will bind it to one verified disposable client, prove that client is closed, switch the
profile, and relaunch it.

## Conflict policy

Providers that compile to the same source/result payload contract are deduplicated. Different
results for the same `(group_id, resource_id)` fail with `TextureProfileConflictError`.

Resolve a real conflict by naming one exact component provider:

```python
plan = compile_texture_profile(
    pristine_cache,
    packages,
    content_build_id=content_build_id,
    profile_id="visual",
    resolutions={(0, 1706002): "org.shadowbanelab.restrained-forest:textures"},
)
```

Unknown, stale, or unnecessary resolutions are rejected rather than ignored.

## Boundary

Public mods may describe components and build variants. They cannot provide archive offsets,
compressed cache records, arbitrary write bytes, native hooks, or in-process code. The internal
`client_extension.texture_cache` engine remains the sole owner of binary cache mutation.
