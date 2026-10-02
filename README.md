# shadowbane-lab

Navigation diagnostics: [inspector usage, review branch and acceptance status](docs/navigation-inspector.md).

## Finding the current code

Start new work from freshly fetched `origin/main`, currently PR #61 merge
`1e7c26ff005cf53453842e4e5462a9091c9058c0`. Installed host **0.3.65** / native
**1.8.45** use qualified source `fc8b316` with official client **1.3.38.13**.

[PR #61](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/61)
merged after all 15 checks passed at `86d76b9`. The user gave standing approval
for routine bot merges/installations after required checks and reviews; see
[delivery instructions](AGENTS.md). This does not waive validation.

Installation verified 463 modules, 9,575 preserved files, one DLL inventory change,
healthy manager activation, five shortcuts and startup preflight. The obsolete
.64 host and .44 deployment payloads were removed without retained rollback copies.
Settings, jobs and diagnostic evidence remain in place. The desktop launch and
dashboard shortcuts point to the verified current runtime.

**Active next item:** resolve pending-buff timeout handling and the native potion
inventory lookup before repeating bounded gameplay. The first .65 test remains
**not passed**. Precision and Beorc effects were observed; Rat Shape queued but
remained locally pending in the captured publications. No potion or NPC attack
was submitted. A parent stop followed the host's five-second preparation deadline;
native telemetry separately retained a 281 ms stalled-update revocation. Exact
NATIVE_STOPPED cleanup and subsequent owner NONE were confirmed. This is
not full buff or encounter acceptance. Automatic retaliation remains disabled.
See the [buff record](docs/buff-preparation-20261001.md).

The delivery-record lane is `codex/buff-runtime-receipt-20261002` in the existing
integration worktree. Read the [branch map](docs/git-branch-map.md) before selecting
a development base and the [contributor workflow](CONTRIBUTING.md) before starting
a new task. The [session-boundary audit](docs/retaliation-session-boundary-20261001.md)
records remaining retaliation attribution guarantees. Earlier lanes remain in the
[integration inventory](docs/integration-status-20260923.md).

`shadowbane-lab` is a deterministic simulation and bot-policy laboratory. It treats
Shadowbane as a data-driven ruleset and keeps deployment mechanisms outside the policy.

The central communication contract is:

```text
Observation -> Affordances -> Decision -> Events
```

The same semantic decision can be consumed by a deterministic simulator, translated to
authoritative emulator commands, or mapped to calibrated mouse and keyboard input. Policy
code never contains screen coordinates, hotbar slots, server power tokens, or Java object
identifiers.

## Current status

The versioned protocol, typed action algebra, deterministic scalar reference environment,
first provenance-aware Shadowbane ruleset slice, and guarded client-input adapter are
implemented. Progression-aware duel rollouts exercise level-gated Assassin and Warlock
power ranges at explicit training-rank brackets. A sourced WonderBane progression slice
evaluates level/ability/training budgets and normalized unarmed-proc output for an Irekei
Rogue Assassin. Build-guarded native readers now expose the live scalar progression core plus
lossless skill and power vectors, and the sourced roadmap can audit those ranks directly.
A provenance-aware legacy identity catalog provides a fail-closed baseline for race, base-class,
profession, sex, and racial-discipline legality while current WonderBane creation-screen values
are captured and verified.
The PvP simulator also has a fail-closed complete-sheet path: strict versioned Assassin and
Warlock profiles compile source-pinned hit, attack/defense, weapon and spell scaling, centered
damage, resistance/protection, proc, passive-defense, stacking, immunity, and interruption
mechanics into reproducible single duels or streaming multi-seed batches. Timed scalar
modifiers, deterministic periodic pulses, and post-resistance damage breakpoints now execute
Steal Breath and Psychic Shield through the same typed algebra. Source-revision and
ruleset-override acceptance are explicit CLI switches; unverified profiles cannot run.
Native LT/LG feedback, selected-target and group-leader coordinates, and calibrated minimap axes
support bounded closed-loop travel.
Direct semantic PvE batches run known
player/mob encounters across contiguous deterministic seeds without client targeting or
window-safety machinery; a separate bridge tests the guarded production PvE controller.
The local multi-client manager now discovers open instances, grows capacity through **Add
client**, retires closed bindings, and provides exact launch/attach correlation,
dispatch-only pause/resume, graceful-close primitives, and an authenticated localhost
dashboard without coupling character tactics to a host PC. Native window tiling remains an
internal primitive because Shadowbane does not rescale its renderer after an external resize.
Differential traces can record and compare
simulator and emulator semantics
without relying on producer-specific IDs. The input adapter compiles the same semantic
decisions into calibrated plans and keeps live PyAutoGUI input locked behind window guards,
an emergency stop, and explicit profile confirmation. See [the architecture](docs/architecture.md),
[client-input runbook](docs/client-input-harness.md),
[bounded client-action harness](docs/client-action-harness.md),
[persistent client extension](docs/client-extension.md),
[player-owned vendor rolling integration](docs/vendor-rolling.md),
[local multi-client manager](docs/client-manager.md),
[read-only character snapshot runbook](docs/character-snapshot.md),
[camp-scoped PvE runbook](docs/pve-automation.md),
[closed-loop travel runbook](docs/travel-automation.md),
[client world-data notes](docs/world-data.md),
[PvP data catalog and capture guide](docs/pvp-data.md),
[automated VM setup](docs/vm-setup.md),
[simulation rollout guide](docs/simulation-rollouts.md),
[differential-validation contract](docs/differential-validation.md),
[produced-build runtime consistency gate](docs/runtime-consistency.md),
[capture-once diagnostic runbook](docs/diagnostic-capture.md),
[evidence-spine architecture](docs/evidence-spine.md),
[evidence-spine delivery plan](docs/evidence-spine-delivery-plan.md),
[tool ownership map](docs/tooling-map.md),
[Elf Druid guide matchup](docs/wonderbane-elf-druid-presets.md), and
[development plan](docs/plan.md).

## Local validation

The protocol has no runtime dependencies. From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m shadowbane_lab.rollouts
python -m shadowbane_lab.rollouts --matrix --levels 10,42,75 --ranks 0,20,40 --distances 15,60,110 --seeds 1,2,3 --json
python -m shadowbane_lab.rollouts --scenario irekei-proc --level 59 --json
python -m shadowbane_lab.rollouts --scenario verified-duel --left-profile .\assassin.json --right-profile .\warlock.json --episodes 1000 --accept-source-revision --accept-ruleset-overrides --json
python -m shadowbane_lab.rollouts --scenario wonderbane-guide-duel --matrix --distances 6,15,40,100 --episodes 1000 --assassin-stealthed --max-ticks 2400 --json
python -m shadowbane_lab.rollouts --scenario wonderbane-druid-duels --matrix --distances 6,15,40,100 --episodes 1000 --max-ticks 2400 --json
python -m shadowbane_lab.cli client observe-native-snapshot --json
python -m shadowbane_lab.cli client observe-native-progression --json
python -m shadowbane_lab.cli client observe-native-training --json
python -m shadowbane_lab.cli client advise-irekei-proc --json
python -m shadowbane_lab.cli client observe-native-position --json
python -m shadowbane_lab.cli client observe-native-target-position --json
python -m shadowbane_lab.cli client observe-native-zone --json
python -m shadowbane_lab.cli client observe-native-zone --cache-directory 'C:\path\to\Wonderbane\cache' --json
python -m shadowbane_lab.cli client observe-native-group --json
python -m shadowbane_lab.cli character validate-layout .\configs\wonderbane-character-layout.template.json --json
```

When Python is not exposed on `PATH`, use the interpreter configured for the workspace.
