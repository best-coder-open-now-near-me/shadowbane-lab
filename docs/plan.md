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
- Prefer the pinned WonderBane calculator for static tables and published formulas, then verify
  representative outputs against the live client before promoting calculator-derived values.

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

## Evidence-spine delivery program

Further live-mechanics and forensic work should use the evidence spine rather than create new
standalone artifact families. The durable delivery sequence is:

1. Extract shared strict-JSON, digest, timestamp, path, tree-inventory, and create-only primitives
   without changing existing public artifacts.
2. Add content-addressed artifact storage, sealed evidence manifests, verification receipts, and a
   rebuildable query index.
3. Compose client, runtime, service, environment, character, and lab-execution identity into one
   mandatory fingerprint envelope.
4. Add versioned research-case and experiment contracts with bounded steps, capture requirements,
   safety policy, repetition design, and explicit hypotheses.
5. Align native, extension, semantic-decision, input-audit, simulator, process, screen, log, and
   authorized network-summary records through monotonic clocks, producer sequence, correlation,
   and synchronization markers.
6. Seal three end-to-end case families: runtime health, vendor-dialog observation, and one combat
   breakpoint differential.
7. Generate coverage, next-evidence, stale-build, and change-impact reports from the corpus,
   layouts, cases, simulator bindings, tests, and gap ledger.
8. Add semantic binary alignment, asset dependency graphs, protocol reconstruction, and passive
   runtime discovery only after those producers can use the common evidence contracts.

The complete architecture, schemas to introduce, module boundaries, migrations, validation
matrix, commit cadence, and per-slice gates are defined in
[the evidence-spine specification](evidence-spine.md) and
[delivery plan](evidence-spine-delivery-plan.md). ADR 0004 makes canonical JSON manifests the
durable truth, content-addressed objects the raw evidence store, and SQLite a disposable index.

**Gate:** each named mechanic can be traced from exact fingerprints and immutable raw artifacts to
a discriminating experiment, normalized trace, profile-specific claim, simulator binding,
differential result, regression test, and declared invalidation rule.

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

## Current PvP simulator readiness

- Complete-sheet JSON profiles compile source-pinned attack, defense, weapon, power, mitigation,
  proc, passive-defense, stacking, immunity, and interruption mechanics without fallback stats.
- Single-seed and compiled-once multi-seed guide duels among the Assassin, Warlock and Druid carry
  formula revision, sheet source revision, and compatibility acceptance in every result.
- Shadow Touch, Shadow Bolt, and Steal Breath now carry current-client token mappings as well as
  historical canonical IDStrings.
- Stances are mutually exclusive snapshot state, travel drops to normal on an unavoided hit, and
  caster-centered versus target/ground-centered areas resolve explicit radius, relations, target
  caps, and per-victim hit gates.
- Timed scalar modifiers, deterministic periodic pulses, resistance adjustments, and cumulative
  post-resistance breakpoints execute Steal Breath and Psychic Shield without power-name logic.
- The source-pinned Elf Healer Druid adds target-relative kiting, target-centered thorn/lightning
  areas, typed poison/disease cleansing, three distinct healing shapes, Oaken Flesh pre-fight
  cooldown state, and complete matchup matrices against both existing builds.
- The remaining data work is current WonderBane differential validation, complete live combat
  sheets, authoritative stance modifiers and AoE rows, resolution of the Psychic Shield and Oaken
  Flesh breakpoint/resistance conflicts, passive resource regeneration and expansion from the
  present representative action slice to additional selected movesets. The runner rejects any
  selected unresolved action meanwhile.

**Gate:** representative live traces promote all three sheets and selected action rows to
`live_verified`, after which the default strict CLI runs without acceptance overrides.
