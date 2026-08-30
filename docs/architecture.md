# Architecture

## System boundary

The project has four durable layers:

1. **Generic simulator** — deterministic typed state transitions, time, randomness,
   snapshots, and causal events.
2. **Shadowbane ruleset** — compiled entities, builds, powers, equipment, formulas, and
   concrete emulator mappings with provenance.
3. **Policies** — utility controllers, evolutionary optimization, quality-diversity
   archives, and learned policies.
4. **Adapters** — simulator execution, authoritative server commands, guarded client input,
   and read-only client observation.

The layers communicate through a single versioned protocol:

```text
ObservationMessage
       |
       v
AffordanceSetMessage
       |
       v
DecisionMessage
       |
       +----> Simulator adapter
       +----> Emulator server adapter
       +----> Client-input adapter
       |
       v
EventBatchMessage
```

## Protocol invariant

A policy selects a semantic, already-legal affordance. It does not select a packet, key,
hotbar slot, mouse position, or simulator opcode.

An affordance binds a stable semantic action key to an actor and any applicable target,
position, direction, item, objective, or quantity. Its semantic tags and numeric features
allow policies to reason about actions they have never seen by name.

Adapters own concrete mappings:

- The simulator adapter resolves the action key to compiled primitives.
- The server adapter resolves it to a power token and authoritative entity identifier.
- The client adapter resolves it to a calibrated input plan.

Every adapter reports results through the same event vocabulary. Correlation identifiers
link observations, decisions, input traces, emulator requests, and resulting events.

Client observation is split into acquisition, decoding, and presentation. Build-guarded native
readers emit exact typed state and combat events; calibrated pixels remain an independent
cross-check. A click-through overlay and a bounded PvE controller are consumers of the same
semantic stream. This keeps screen geometry and rendered text out of policy code and lets
differential recording consume identical observations without depending on the overlay.

## Trust boundaries

- The simulator is authoritative only inside a simulated world.
- The live emulator is authoritative for live state and action outcomes.
- A policy cannot mutate live health, resources, effects, or ownership directly.
- A client-input adapter may operate only while its approved target window and calibration
  profile remain valid.
- A client-observation adapter may capture only the approved foreground client rectangle and
  must fail closed when dimensions, DPI, profile pairing, or calibrated visual structure changes.
- A native client-observation adapter may request query/read rights only and must fail closed on
  executable identity, process ambiguity, pointer instability, or implausible decoded values.
- Template and dry-run calibration profiles cannot dispatch through a live desktop backend;
  live input requires an explicit per-profile confirmation bit.
- Recorded or dry-run input adapters are used in automated tests; test execution must not
  generate desktop input.

## Versioning

Protocol version `1` is encoded in every message. Breaking wire changes require a new
version. Additive semantic action keys, feature names, tags, and event types do not require
a wire-version change when older consumers can safely ignore them.

The protocol uses deterministic canonical JSON for logs, fixtures, sidecar communication,
and differential validation. A future binary transport may wrap the same logical messages
without changing policy semantics.

## Reference execution semantics

The scalar `ReferenceEnvironment` is the correctness oracle for later optimized backends.
It uses a virtual fixed-tick clock and a specified PCG32 random stream. Every pending phase,
projectile delivery, effect expiry, entity value, cooldown, clock value, random state, and
event counter is included in an immutable snapshot.

All decisions submitted for one tick are validated against the same pre-step state. Effects
scheduled for the same virtual timestamp use a stable order while sharing the set of entities
that were alive at the start of that timestamp; consequently, simultaneous lethal actions
can produce mutual death. Precise Shadowbane conflict and stacking rules will replace generic
ordering where differential traces establish authoritative behavior.

The initial spatial model is an unobstructed continuous 2D plane. Range and projectile travel
are enforced. Line-of-sight constraints are retained in compiled action data and will become
active when obstacle geometry enters the Shadowbane vertical slice.
