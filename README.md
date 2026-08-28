# shadowbane-lab

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
The local multi-client manager now provides strict per-PC lifecycle manifests, read-only
preflight, exact launch/attach correlation, dispatch-only pause/resume, non-activating window
tiling, graceful-close primitives, and an authenticated localhost dashboard without coupling
character tactics to a host PC.
Differential traces can record and compare
simulator and emulator semantics
without relying on producer-specific IDs. The input adapter compiles the same semantic
decisions into calibrated plans and keeps live PyAutoGUI input locked behind window guards,
an emergency stop, and explicit profile confirmation. See [the architecture](docs/architecture.md),
[client-input runbook](docs/client-input-harness.md),
[local multi-client manager](docs/client-manager.md),
[camp-scoped PvE runbook](docs/pve-automation.md),
[closed-loop travel runbook](docs/travel-automation.md),
[client world-data notes](docs/world-data.md),
[PvP data catalog and capture guide](docs/pvp-data.md),
[automated VM setup](docs/vm-setup.md),
[simulation rollout guide](docs/simulation-rollouts.md),
[differential-validation contract](docs/differential-validation.md), and
[development plan](docs/plan.md).

## Local validation

The protocol has no runtime dependencies. From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m shadowbane_lab.rollouts
python -m shadowbane_lab.rollouts --scenario irekei-proc --level 59 --json
python -m shadowbane_lab.rollouts --scenario verified-duel --left-profile .\assassin.json --right-profile .\warlock.json --episodes 1000 --accept-source-revision --accept-ruleset-overrides --json
python -m shadowbane_lab.cli client observe-native-progression --json
python -m shadowbane_lab.cli client observe-native-training --json
python -m shadowbane_lab.cli client advise-irekei-proc --json
python -m shadowbane_lab.cli client observe-native-position --json
python -m shadowbane_lab.cli client observe-native-target-position --json
python -m shadowbane_lab.cli client observe-native-zone --json
python -m shadowbane_lab.cli client observe-native-zone --cache-directory 'C:\path\to\Wonderbane\cache' --json
python -m shadowbane_lab.cli client observe-native-group --json
```

When Python is not exposed on `PATH`, use the interpreter configured for the workspace.
