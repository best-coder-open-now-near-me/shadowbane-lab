# Development plan

## 1. Foundation and contracts

- Establish packaging, tests, CI, architecture records, and Git checkpoints.
- Define the versioned observation, affordance, decision, and event messages.
- Define adapter and semantic input-command boundaries.
- Keep screen coordinates, keys, power tokens, and runtime object identifiers out of policy
  code.

**Gate:** messages round-trip through canonical JSON, invalid messages fail closed, and a
decision can be validated against the exact affordance set from which it was selected.

## 2. Deterministic reference simulator

- Implement simulated time, seeded randomness, fixed ticks, causal events, snapshots, and
  restore.
- Distinguish life termination, world termination, and rollout truncation.
- Implement a minimal typed action grammar for movement, melee, projectiles, healing,
  stealth, item transfer, and objective capture.

**Gate:** identical initial state, decisions, and seed produce identical event and state
traces; snapshot forks remain reproducible.

## 3. Shadowbane vertical slice

- Add movement and basic weapon combat.
- Compile representative Assassin powers, then Warlock powers.
- Classify rules as `COMPILED`, `COMPILED_WITH_OVERRIDE`, or `UNRESOLVED`.
- Preserve provenance for every concrete value and semantic interpretation.

**Gate:** the representative slice exercises the major action families without silent
approximations.

## 4. Differential validation

- Capture controlled emulator inputs, events, and resulting state.
- Replay equivalent scenarios in the simulator.
- Compare timing, legality, costs, damage, effects, stacking, interrupts, cooldowns, and
  movement.
- Maintain an explicit simulator-gap ledger.

**Gate:** deterministic mechanics match exactly; stochastic mechanics meet documented
distribution tolerances.

## 5. Guarded client-input harness

- Convert semantic decisions into calibrated click, drag, key, hotbar, camera, and target
  operations.
- Validate the target process, foreground window, client bounds, DPI, and calibration
  profile before dispatch.
- Provide recording and dry-run backends, rate limits, structured audits, a corner failsafe,
  and an independent emergency stop.

**Gate:** representative decisions replay correctly against an approved client while every
invalid focus or calibration condition fails closed. Automated tests generate no desktop
input.

## 6. Batched simulation

- Introduce fixed-capacity numeric worlds, actors, actions, and effect slots.
- Accelerate the reference behavior using array-oriented NumPy and Numba implementations.
- Test every optimized transition against the reference simulator.

**Gate:** reference parity is preserved while throughput meets the benchmark established
from representative scenarios on the target hardware.

## 7. Scenarios and baseline controller

- Current vertical slice: progression-aware Assassin-versus-Warlock clean-start duels,
  deterministic utility decisions, explicit rank brackets, and legality/resource/outcome
  metrics.
- Current live slice: a bounded nearby-mobile PvE controller using exact selected-target
  health and position, client-native trainer/service-role filtering, typed native combat events,
  semantic input actions, and strict stop conditions.
- Support clean starts, mid-fight snapshots, reinforcement, retreat, death/respawn,
  uneven teams, and objectives.
- Implement a generic utility policy over semantic affordances.
- Track legality, survival, contribution, objective impact, and resource efficiency.

**Gate:** the baseline completes representative scenarios without invalid-action loops and
provides a stable benchmark for learned policies.

## 8. CMA-ES and MAP-Elites

- Tune interpretable utility weights with common seeds and snapshots.
- Build a quality-diversity archive over aggression, engagement range, support, control,
  mobility, and resource use.

**Gate:** optimized controllers outperform the fixed baseline and the archive contains
meaningfully distinct, reproducible behavior.

## 9. Relational PPO/MAPPO and live integration

- Encode local entities and available actions as permutation-insensitive sets.
- Score bound action candidates using recurrent memory.
- Train with centralized critics, decentralized execution, rolling windows, correct
  truncation bootstrapping, and an opponent league.
- Route the same decisions through server-side and client-input adapters.

**Gate:** policies generalize across scenario and build permutations, and live deployment
cannot bypass authoritative validation.

## Current world-navigation investigation

- Read and validate the client cache directory without copying gameplay textures into the
  repository.
- Index TerrainAlpha map/tile identities and parse the nested WorldDef placement tree.
- Correlate the active runtime ArcGameZone and parent chain with CZone and terrain-raster
  resources, then join collision-bearing object populations through CObjects, Render, and Mesh.
- Project the first CZone-referenced TerrainAlpha layer, now identified as its height field, into
  LT/LG from native placement bounds, local/absolute centers, and rotation. Seed steep transitions
  as exclusions and gentler height changes as weighted traversal costs.
- Explicit zone-local `CZone` water seeds high, traversable costs from the declared sea level and
  terrain height range. Collision-bearing object-population rasters now seed soft density costs;
  decode parent/world-relative water transforms and exact static-object placements next.
- The PvE approach controller now uses bounded weighted A* with waypoint smoothing and online
  replanning from stalls. Extend that same static grid into hierarchical long-distance `/go`
  routing after exact object placement and zone-boundary composition are decoded.
- Keep native `PATHFINDING` disabled: the legacy `/path on` command is absent from the current
  WonderBane command table, and enabling its preference previously caused a launch error.
- Preserve server movement corrections as authoritative feedback even when local pathfinding is
  unavailable.

**Gate:** a recorded destination identifies its active terrain resources, produces an auditable
local route or native waypoint stream, and converges without blind fixed-direction detours while
server correction remains observable.
