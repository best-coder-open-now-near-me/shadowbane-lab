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

The versioned protocol, typed action algebra, deterministic scalar reference environment, and
first provenance-aware Shadowbane ruleset slice are implemented. Differential traces can now
record and compare simulator and emulator semantics without relying on producer-specific IDs.
See [the architecture](docs/architecture.md),
[differential-validation contract](docs/differential-validation.md), and
[development plan](docs/plan.md).

## Local validation

The protocol has no runtime dependencies. From the repository root:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

When Python is not exposed on `PATH`, use the interpreter configured for the workspace.
