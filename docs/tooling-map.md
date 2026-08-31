# Tool ownership map

Shadowbane Lab has several command surfaces because live client operation, offline forensics,
simulation, and release gating have different safety boundaries. This map identifies the canonical
owner of each workflow and distinguishes a real capability from a wrapper around one.

Historical feature ownership, unmerged branch dependencies, preserved experiments, and integration
rules are recorded in [`feature-lineage.md`](feature-lineage.md).

## Canonical command surfaces

| Surface | Audience | Owns | Does not own |
| --- | --- | --- | --- |
| `shadowbane-lab` | operators and developers | `client`, `character`, `manager`, and `progression` workflows | extension packaging, PE forensics, simulator experiments |
| `python -m shadowbane_lab.rollouts` | simulation developers | deterministic scenarios, matrices, and rollout reports | live client lifecycle or evidence capture |
| `shadowbane-runtime-consistency` | release validation | suite validation, capture, baseline promotion, comparison, and deployment gates | installation or client patching |
| `python -m shadowbane_lab.client_extension` | offline client-maintenance work | immutable client snapshots, official-build diffs, extension manifests/packages, rollback, and heartbeat evidence | live automation or game policy |
| `python -m shadowbane_lab.client_alignment` | low-level client forensics | one-PE inspection and two-PE byte/section/anchor comparison | whole-client release comparison |

`client_extension diff-baselines` deliberately reuses `client_alignment compare` internally when
the executable changed. The former is the whole-release evidence workflow; the latter remains the
focused forensic primitive. Do not introduce a separate patch-diff executable or PowerShell wrapper
unless the VM workflow later needs fixed path, timestamp, or privilege policy.

## PowerShell wrapper groups

The scripts are deployment adapters, not additional domain APIs:

| Lifecycle | Scripts | Canonical capability beneath them |
| --- | --- | --- |
| VM/bootstrap | `setup-wonderbane-vm.ps1`, `bootstrap-wonderbane-control-center.ps1` | environment setup and delayed share availability |
| Install/configure | `install-wonderbane-vm-control-center.ps1`, `install-wonderbane-isolated-runtimes.ps1`, `configure-wonderbane-client-count.ps1` | manager manifest and runtime deployment commands |
| Start/stop | `start-wonderbane-control-center.ps1`, `start-wonderbane-go-listener.ps1`, `stop-wonderbane-go-listener.ps1` | manager app and listener process lifecycle |
| Extension evidence | `build-wonderbane-client-extension.ps1`, `freeze-wonderbane-client-baseline.ps1`, `collect-wonderbane-client-extension-evidence.ps1`, `prepare-wonderbane-client-extension-copy.ps1` | client-extension maintenance commands |
| Live evidence | `run-wonderbane-pve-evidence.ps1`, `export-wonderbane-sim-observation.ps1`, `trace-wonderbane-vendor-dialog.ps1` | bounded client observations and runs |
| Network evidence | `start-wonderbane-incoming-capture.ps1`, `stop-wonderbane-incoming-capture.ps1` | Windows Packet Monitor session lifecycle |

The similarly named control-center scripts are sequential layers rather than substitutes:
`install` creates persistent configuration and shortcuts, `bootstrap` waits for VM shares at logon,
and `start` validates and launches the current manager/listener processes. The isolated-runtime
installer composes the single-slot installer with baseline capture and multi-slot deployment.

## CLI implementation boundaries

`shadowbane_lab.cli` is the stable executable facade and top-level dispatcher. Parser construction
and command behavior live under `shadowbane_lab.cli_commands`: character, manager, progression,
client inspection, client PvE, client travel, and chat-listener behavior each have a focused owner.
Shared live-client guards are isolated in `client_runtime`.

Keep existing imports and patch points on `shadowbane_lab.cli` compatible when moving behavior. New
command logic belongs in its owning command module; the facade should contain only routing and
compatibility plumbing.

## Effective pipelines

The useful compositions below should stay inside their current command owner. They do not justify
new top-level executables:

| Pipeline | Primitive flow | Status and boundary |
| --- | --- | --- |
| Official patch intake | `freeze-baseline` before update -> `freeze-baseline` after update -> `diff-baselines` | Complete. This is the canonical developer-patch diff: it verifies both immutable trees and composes cache and PE alignment evidence into one report. |
| Extension candidate lifecycle | `inspect-bootstrap` / `align` -> `author-bootstrap` -> `prepare-copy --dry-run` -> `prepare-copy` -> `verify-copy` -> live launch -> `verify-heartbeat` -> `discard-copy` | Complete primitives. Keep manifest review and live verification explicit; alignment evidence must never become write authority. |
| Multi-client release gate | `freeze-baseline` -> `author-bootstrap` -> `manager provision-runtimes` -> `manager preflight` -> manager app/workers -> `runtime-consistency gate` | Composed by the isolated-runtime installer and runtime gate. Baseline promotion remains a separate reviewed action so a candidate cannot approve itself. |
| Live PvE calibration feedback | `validate-profile` + `inspect-hotbar` -> `run-pve` evidence -> `calibrate-pve` -> `rollouts --scenario smart-camp --pve-calibration ...` | Strong artifact pipeline that links guarded live evidence to deterministic simulation. It needs a runbook, not another command surface. |
| Character-layout forensics | `inspect-process` -> analyst-directed `scan-text` / `scan-pointer` -> `validate-layout` -> `snapshot` | Deliberately interactive. Candidate addresses and layouts require review, so automatic chaining would weaken the safety boundary. |
| Native simulator observation | `observe-native-progression` + `observe-native-training` + `observe-native-player` -> simulator observation JSON | Useful but not yet coherent. The current PowerShell exporter performs three separately guarded reads; replace it with one Python snapshot command bound to one exact process and timestamp, then keep the focused observations as compatibility aliases. |

The last row is the highest-value new composition. It removes a temporal-consistency gap and one
thin PowerShell wrapper while reducing command sprawl. Patch qualification should reuse the first
three rows rather than introducing a second diff, packaging, or release-gate system.

## Consolidation backlog

The current census is 62 argparse subcommands across four parser modules, plus 17 PowerShell
wrappers. The original 5,600-line `shadowbane_lab.cli` implementation has been split into the
boundaries above without changing its executable or syntax. Remaining work should follow these
priorities:

1. Introduce one composable native client snapshot command before adding more `observe-native-*`
   commands; retain the focused commands as compatibility aliases until scripts and runbooks move.
2. Centralize immutable tree inventory, path, hash, and strict-JSON validation now duplicated across
   baseline capture, package verification, and patch-diff evidence.
3. Keep PowerShell only where it adds Windows process, privilege, shortcut, VM-share, or fixed-path
   policy. A wrapper that merely renames a Python command should not be added.
4. Standardize operator documentation on the installed `shadowbane-lab` command. Reserve
   `python -m ...` spellings for maintenance modules without console entry points.

This is a compatibility-preserving backlog. Renaming or deleting existing commands before their
scripts, shortcuts, and runbooks migrate would exchange visible clutter for hidden breakage.
