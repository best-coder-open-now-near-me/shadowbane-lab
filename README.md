# shadowbane-lab

Navigation diagnostics: [inspector usage, review branch and acceptance status](docs/navigation-inspector.md).

## Finding the current code

Start new work from freshly fetched `origin/main`, currently PR #59 merge
`1517a61b512b10bafa54fe96815372ead33fcfe4`. Installed host **0.3.63** / native
**1.8.43** use qualified source `e8aec99` with official client **1.3.38.13**.

[PR #59](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/59)
merged after all 15 hosted checks passed at approved head `1ceead0`. The installed
buff module shares one native actor owner with NPC/manual-player combat. Native
coverage and readiness govern automatic preparation; pending potion application
does not block an independent locally ready action. See the
[buff contract and qualification receipt](docs/buff-preparation-20261001.md).

Installation verified 463 modules, 9,572 preserved files, one DLL inventory change,
healthy manager activation, five shortcuts and startup preflight. The obsolete
.62 host and .42 deployment payloads were removed without retained rollback copies.
Settings, jobs and diagnostic evidence remain in place. The desktop Vendor Test
and Modded Client shortcuts use the updated launcher; dashboard shortcuts use .63.

**Active next item:** obtain merge/install approval for the qualified .64/.44
effect-observer startup repair in PR #60, then close the client and install it. Registration returned unavailable before any
buff or attack submission; exact cleanup and subsequent idle readiness passed.
Source/package qualification and installation do not prove live buff application
or expiry. Automatic retaliation remains disabled. The earlier .62
[bounded combat recovery acceptance](docs/native-owner-liveness-20261001.md)
remains a separate result and need not be repeated as buff acceptance.

The deployment-receipt/live-acceptance lane uses
`codex/buff-deployment-20261001` in the existing integration worktree. Read the
[branch map](docs/git-branch-map.md) before selecting a development base and the
[contributor workflow](CONTRIBUTING.md) before starting a new task. The
[session-boundary audit](docs/retaliation-session-boundary-20261001.md) records
remaining retaliation attribution guarantees. Earlier lanes remain in the
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
