# Progression-aware duel rollouts

The rollout harness runs the same semantic affordances used by adapters through the scalar
reference environment. Its first scenario is a deterministic Assassin-versus-Warlock duel
with a generic utility policy. The runner records the winner, termination reason, duration,
remaining resources, damage, healing, action counts, and rejected-action count.

## Progression boundary

Character level, focus-skill training, enabled powers, and power rank are separate inputs.
This matters because Shadowbane awards training points for player-directed allocation; there
is no single authoritative power-rank curve for a given character level.

The current executable slice uses these published grant points:

| Profession | Power | Granted | Focus requirement | Status |
| --- | --- | ---: | --- | --- |
| Assassin | Shadow Bolt | 10 | Shadowmastery 15 | Executable |
| Assassin | Shadow Touch | 15 | Shadowmastery 36 | Executable |
| Assassin | Passwall | 28 | Shadowmastery 66 | Unresolved and excluded |
| Warlock | Mind Strike | 10 | None published | Executable |
| Warlock | Levitation | 22 | Warlockry 52 | Executable at fixed rank 5 |
| Warlock | Psychic Healing | 26 | Warlockry 61 | Executable |

Sources are the archived [Assassin power table](https://morloch.shadowbaneemulator.com/index.php?title=Assassin_Powers&oldid=36339),
[Warlock power table](https://morloch.shadowbaneemulator.com/index.php?title=Warlock_Powers&oldid=36352),
and the pinned MagicBane server revision recorded in the bundled ruleset. Every concrete
mechanic retains field-level provenance and an explicit compilation quality state.

`CharacterBuild.enabled_power_keys` can select a strict subset. `power_ranks` can select
rank 0 through 40 independently. A ruleset must be compiled at those exact ranks; mismatches,
unknown powers, invalid fixed-rank overrides, unmet levels, and unmet prerequisites fail
closed.

## Complete-sheet Assassin-versus-Warlock simulation

The production duel path consumes one strict version-1 combat profile per character. Each file
contains the character's attributes and resources; complete resistance and passive-defense
vectors; equipment defense and attack/defense modifiers; weapon base values, speed, range, and
procs; actual skill and power-focus values; trained ranks; and immutable source/compatibility
metadata. `configs/combat/complete-sheet-v1.example.json` documents the complete shape and is
deliberately marked `unverified`, so it cannot accidentally produce a result.

The compiler uses the pinned MagicBane formula revision
`3649c629b709c67625a09150a3752107f4b873cc` for weapon and power attack rating, defense, weapon
damage bounds, stat/focus health-effect scaling, centered two-roll damage, hit curves,
resistance/protection/armor-piercing order, and effect overwrite priority. The reference runtime
also resolves block, parry, dodge, proc gates, stun immunity, and damage/stun interruption. A
profile with a different formula revision, a missing field, an unresolved selected power, or an
unaccepted source classification is rejected before the first simulation tick.

Run one accepted-source duel:

```powershell
$env:PYTHONPATH = "src"
python -m shadowbane_lab.rollouts `
  --scenario verified-duel `
  --left-profile .\assassin.json `
  --right-profile .\warlock.json `
  --episodes 1 `
  --accept-source-revision `
  --accept-ruleset-overrides `
  --json
```

Run a compiled-once, streaming 10,000-seed matchup sweep by changing `--episodes` to `10000`.
The batch result records wins, draws, termination reasons, mean final resources, damage, healing,
mana use, rejected actions, formula revision, and both sheet acceptance records. Omit
`--accept-source-revision` to require `live_verified` sheets. Omit
`--accept-ruleset-overrides` to reject the current archived static Assassin/Warlock power rows
until current WonderBane differential traces promote them.

## Run the bracket

From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m shadowbane_lab.rollouts
```

Machine-readable output and custom brackets are available:

```powershell
python -m shadowbane_lab.rollouts --levels 10,15,22,26,40 --ranks 0,20,40 --json
```

The built-in matched progression sweep assumes the published focus prerequisites are met.
It deliberately brackets power ranks at 0, 20, and 40 instead of inventing a rank-by-level
allocation. Programmatic callers can provide exact skills, trained ranks, enabled subsets,
resources, starting distance, seed, and tick limit through `DuelConfig`.

## Initial result

With 100 health, 200 mana, a 10-unit start, and the current utility policy, the checked-in
bracket produces:

| Level | Rank 0 | Rank 20 | Rank 40 |
| ---: | --- | --- | --- |
| 10 | Warlock | Assassin | Assassin |
| 15 | Warlock | Assassin | Assassin |
| 22 | Warlock | Assassin | Assassin |
| 26 | Warlock | Warlock | Assassin |
| 40 | Warlock | Warlock | Assassin |

These are harness baselines, not balance claims. In particular, Psychic Healing changes the
rank-20 outcome after its level-26 unlock, while rank-40 Shadow Touch gives the baseline
Assassin a large control advantage after level 15.

## Legacy bracket fidelity gaps

The built-in progression bracket above remains labeled `compiled_with_override`; unlike the
complete-sheet path, it intentionally uses small baseline resources and action-row values without
a character sheet. It does not model:

- hit rolls, attack rating, defense, resistances, or authoritative roll distributions;
- stat/focus modifiers, regeneration, equipment, or weapon-specific basic attacks;
- cast interruption, obstacle line of sight, collision, or full flight movement semantics;
- area targets, damage-over-time ticks, absorbs, or broad buff/debuff interactions.

In that legacy bracket, published damage and healing ranges use a reviewed continuous-uniform approximation. The
specified PCG32 stream makes those rolls exactly replayable by seed and snapshot, while
expected-value policy features remain the published range midpoint. Basic attack damage and
timing are still reviewed placeholders. The useful signal at this stage is legal action flow,
progression gating, resource exhaustion, control timing, healing timing, bounded outcome
variation, and win/loss termination. Emulator differential fixtures are the next authority
for replacing the assumed distribution and closing the remaining action-row gaps. The
complete-sheet path instead compiles the source-pinned combat formulas and fails closed on absent
sheet data; its remaining acceptance boundary is current WonderBane differential validation and
full power-catalog coverage.

## Pure semantic PvE batches

Pure PvE starts with a known player and hostile entity and chooses legal semantic combat
affordances directly. It does not instantiate `PvEController`, target-selection tokens, native
readers, window focus guards, acquisition retries, or combat-log confirmation. Those behaviors
belong to the separate client-adapter integration scenario below.

Run a compact 10,000-seed batch without emitting per-episode traces:

```powershell
$env:PYTHONPATH = "src"
python -m shadowbane_lab.rollouts `
  --scenario pure-frost-walker `
  --episodes 10000 `
  --seed 0 `
  --json
```

The initial observed-profile batch produced 10,000 kills and no timeouts. With the current
inclusive 4-5 damage approximation against 10 health, 2,473 episodes took two attacks and
7,527 took three. Modeled kill times were therefore 1,000 ms or 2,000 ms, with a 1,752.7 ms
mean and 2,000 ms p50/p90/p99. The batch is a deterministic pipeline and sensitivity baseline,
not a balance claim: its 1-second attack interval, passive enemy, lack of hit rolls, and damage
distribution are still declared assumptions.

The batch runner streams into aggregate counters by default, so large studies do not retain one
Python object per episode. Programmatic callers can opt into exact per-seed result retention for
smaller trace studies. Summary output includes kill rate, attacks-to-kill and kill-time histograms,
damage-roll counts, percentiles, rejected semantic actions, and total experience.

## Nearby-mob controller bridge

The `frost-walker` scenario runs the production bounded PvE controller against the reference
environment rather than substituting a simulator-only policy. Controller acquisition selects a
simulated mobile, attack-selected enables repeated legal `shadowbane.basic_attack` affordances,
and simulator damage/death events are bridged back into the exact typed native observations the
controller consumes.

```powershell
$env:PYTHONPATH = "src"
python -m shadowbane_lab.rollouts --scenario frost-walker --seed 23 --json
```

The profile is evidence-bearing: 10 target health, observed 4-5 player damage, 744 experience,
and the live-read player resources are data; the discrete-uniform roll, 1-second attack interval,
and passive mob are declared assumptions. It is therefore useful as a deterministic automation
gate and future differential-trace target without laundering unknown PvE mechanics into facts.

## Smart proc-Assassin camp policy

The `smart-camp` scenario is the first active multi-mob PvE policy. It retains its current living
target, selects the nearest replacement only after that target dies, opens a fresh target with
rank-40 Shadow Touch while stun immunity is absent, and otherwise maintains dual-fist pressure.
It does not contain rare-mob, rune, or location-specific behavior.

The combat policy exposes movement as a target-relative close-range intent instead of eight
world-compass actions. The environment still owns full two-dimensional positions, collision,
and pathfinding; it resolves that intent into movement toward the selected target. This keeps
future group positioning representable as pairwise range relations without multiplying equivalent
single-target choices.

Each aggregate successful hit opportunity applies sourced raw 4-16 fist damage and independently
checks the tier-three mental and rank-40 Poison Blade procs at 5%. Proc damage uses the sourced
spell-damage formula for the explicit 35/130/85/165/15 observed-trait candidate. Every chance
check, trigger, requested damage amount, effective damage amount, action, and target transition
is retained in deterministic episode evidence.

Run one detailed seed:

```powershell
$env:PYTHONPATH = "src"
python -m shadowbane_lab.rollouts `
  --scenario smart-camp `
  --episodes 1 `
  --seed 4 `
  --json
```

Or stream a compact seed batch without retaining episode traces:

```powershell
python -m shadowbane_lab.rollouts `
  --scenario smart-camp `
  --episodes 1000 `
  --seed 0 `
  --json
```

A calibration compiled from versioned live PvE traces can replace the supported generic mob
and starting-resource assumptions without modifying code:

```powershell
python -m shadowbane_lab.rollouts `
  --scenario smart-camp `
  --episodes 1000 `
  --seed 0 `
  --pve-calibration .\proc-assassin-calibration.json `
  --json
```

The result's profile, evidence, and assumptions identify the applied calibration. Sparse
observations retain baseline defaults, and poll-observed timing is quantized to the simulator's
200 ms tick.

The checked 250-seed baseline cleared all 250 three-mob camps with no rejected semantic actions.
Mean clear time was 30,538.4 ms, with 29,600/42,600/50,600 ms p50/p90/p99 and 324.62 mean
remaining health from an assumed 500. Across 7,471 successful-hit opportunities, mental and
Poison Blade trigger rates were 4.97% and 4.67%, respectively. This is a policy and stochastic
pipeline baseline, not a balance claim: all weapon hits currently succeed; target defense,
resistance, gear scaling, regeneration, and authoritative camp-mob stats remain excluded; and
the three generic mobs' 180 health and 5-10 damage every two seconds are declared assumptions.
