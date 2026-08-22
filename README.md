# shadowbane-lab

A deterministic, data-driven combat playground for discovering strange Shadowbane-style builds and tactics without running the live MMO server in the training loop.

The first slice is intentionally abstract. It proves the architecture before any Reforged values are treated as authoritative:

- combat is a fixed-tick state transition;
- abilities are compositions of typed primitives;
- policies choose from the actions actually available to a build;
- every experiment is seeded and replayable;
- builds and policy tendencies can be evolved together;
- MAP-Elites keeps strong behavioral oddities instead of collapsing everything into one winner.

> **Accuracy warning:** the current action catalog is an engine stress test, not a claim about live Shadowbane Reforged mechanics or balance. Reforged data will be imported with provenance and confidence labels, then checked against controlled observations from the client.

## What exists now

### Generic combat state

Each combatant has:

- health, mana, and stamina;
- regeneration;
- 2D position and movement speed;
- accuracy, evasion, and damage resistances;
- cooldowns and cast commitments;
- status effects;
- a build-specific action set;
- interpretable policy tuning such as preferred range and control bias.

### Typed action primitives

Named actions compile to small reusable operations:

- `DealDamage`
- `RestoreHealth`
- `ModifyResource`
- `ApplyStatus`
- `Reposition`

Every primitive explicitly identifies whether it affects the actor or the selected target. The simulator, policy scorer, event trace, and eventual Reforged importer all share that representation.

### Deterministic simulator

The fixed-tick duel runner includes:

- movement and range checks;
- cast time and cooldowns;
- seeded hit rolls;
- mitigation and wards;
- direct damage, damage-over-time, healing, resource drain, control, and mobility;
- action fizzles when a target leaves range during a cast;
- deterministic tie handling;
- event recording and per-agent metrics.

### Initial build genome

A genome currently controls:

- allocation across vitality, power, control, sustain, and mobility;
- four selected actions from the abstract catalog;
- aggression, sustain, control, and defense preferences;
- resource conservation;
- preferred engagement range;
- finisher bias.

This is deliberately compact enough to inspect when the search finds something cursed.

### MAP-Elites search

The initial archive maps elites by:

1. observed mean engagement distance;
2. observed fraction of control-tagged actions.

Fitness is measured against a small opponent league containing bruiser, kiter, sustain, controller, and glass-cannon baselines. Every candidate is evaluated from both sides of the arena using fixed seeds to reduce positional and random-roll bias.

## Run it

Python 3.11 or newer is required.

```bash
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux/macOS
source .venv/bin/activate
```

Install the package and development tools:

```bash
python -m pip install -e ".[dev]"
```

Run the tests:

```bash
pytest
```

Run a deterministic reference duel:

```bash
bane-lab duel --left 0 --right 1 --seed 7
```

Include the full causal event trace:

```bash
bane-lab duel --left 0 --right 1 --seed 7 --events
```

Run a small MAP-Elites search:

```bash
bane-lab search \
  --evaluations 800 \
  --initial-random 96 \
  --seed 7 \
  --output experiments/results/seed-7.json
```

The same commands also work without installation:

```bash
PYTHONPATH=src python -m banesim duel --seed 7
PYTHONPATH=src python -m banesim search --evaluations 200 --seed 7
```

In PowerShell, set the module path first:

```powershell
$env:PYTHONPATH = "src"
python -m banesim duel --seed 7
```

## Current package layout

```text
src/banesim/
├── model.py       # state, formulas, primitives, statuses, events
├── catalog.py     # abstract action catalog
├── genome.py      # build genome, mutation, reference opponent league
├── policy.py      # interpretable utility controller
├── simulator.py   # deterministic fixed-tick combat loop
├── search.py      # evaluation and MAP-Elites archive
└── cli.py         # duel and search commands
```

Rules data and reviewed corrections live separately:

```text
data/
├── normalized/    # generated, provenance-bearing Reforged records
└── overrides/     # small reviewed exceptions and corrections
```

## First local smoke result

A local 80-evaluation run using seed `7` completed in about 5.1 seconds on the current five-core CPU environment and occupied 22 of the 64 behavior cells.

The top candidate in that tiny run was already mildly strange:

```text
allocation emphasis: power + mobility
kit: Ember, Mend, Wither, Shadow Step
preferred range: 13.7
league win rate: 97.5%
```

That is not evidence of a real Reforged build. It is evidence that the archive and mutation loop are already preserving non-obvious combinations rather than merely reproducing the hand-authored baselines.

## Fidelity plan

Every imported rule should carry one of these confidence states:

- `confirmed` — checked against the current client or a controlled test;
- `wiki` — taken directly from current documentation;
- `inferred` — reconstructed from related mechanics;
- `approximated` — intentionally simplified;
- `unresolved` — excluded from authoritative experiments.

The transfer loop will be:

```text
Reforged wiki/client data
        ↓
normalized primitive rules
        ↓
fast offline simulation and search
        ↓
controlled comparison with live observations
        ↓
formula or override correction
```

A fast simulator that is confidently wrong is worse than a slower one with explicit uncertainty.

## Near-term roadmap

1. Add team combat with dynamic participation and fixed-length rollout windows.
2. Separate scenario definitions from the simulator and add mid-fight snapshots.
3. Add a provenance-aware Reforged wiki/client-data importer.
4. Expand primitive stacking, dispels, immunities, interrupts, and targeting.
5. Add CMA-ES for continuous utility tuning.
6. Add replay visualization and matchup matrices.
7. Add recurrent PPO/MAPPO only after deterministic fidelity tests exist.
8. Keep any live-client bridge isolated from the simulator and subject to server-owner permission.

## Scope and safety

The lab is intended for offline mechanics research, build discovery, reproducible simulation, and explicitly authorized experiments. It does not contain client injection, packet manipulation, anti-cheat bypass, or covert live-server automation.
