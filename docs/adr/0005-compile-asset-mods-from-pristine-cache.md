# ADR 0005: Compile asset mods from one pristine cache

- **Status:** Accepted
- **Date:** 2026-09-02

## Context

The reviewed client package path and the restart-oriented Texture Lab now share one deterministic
`Textures.cache` mutation engine. Public mod packages still need a stable boundary above that
engine. Applying independently authored texture manifests one after another is not valid: each
manifest is intentionally pinned to its exact pristine source cache, so the first mutation makes
the second manifest's source precondition false. Silent load-order replacement would also make a
profile irreproducible and hide collisions between mods.

The native extension, cache offsets, compressed blobs, and direct write plans are implementation
details. Mod authors and users should work with package identities, build variants, components,
profiles, and explicit conflict choices instead.

## Decision

Schema-1 asset mods use a canonical `mod.json` manifest. A texture-set component contains one or
more content-build variants, each naming a reviewed `TexturePatchManifest` and its artifact root.
The public manifest is build-aware but does not expose a write API.

A texture profile compiler:

1. loads every selected package and exact content-build variant;
2. validates each texture manifest and artifact against the same pristine `Textures.cache`;
3. groups providers by `(group_id, resource_id)`;
4. deduplicates providers that compile to the same source/result payload contract;
5. rejects differing results unless the profile names one exact provider;
6. builds one combined `TextureCachePlan` from the pristine cache;
7. cross-checks the combined plan against every selected manifest result; and
8. materializes a create-only candidate directory, validates the complete cache, proves all
   untargeted payloads unchanged, writes a receipt, and only then publishes the directory.

The low-level `client_extension.texture_cache` module remains internal. The asset facade may consume
its planning, validation, comparison, and exact-copy primitives, but public packages cannot submit
raw offsets, directory records, compressed bytes, or arbitrary cache writes.

Texture activation is restart-oriented. This ADR does not authorize an in-process script runtime,
client-memory writes, live renderer callbacks, or sequential mutation of a running client tree.

## Consequences

- A selected profile has one deterministic result independent of package input order.
- Two mods cannot silently replace the same resource through load order.
- Independently authored manifests retain their fail-closed pristine-cache binding.
- Identical visible results can coexist without requiring a meaningless conflict choice.
- Candidate publication can later be composed with the manager's isolated-client lifecycle.
- Additional asset component kinds require a new reviewed compiler while retaining the same public
  package and profile concepts.
