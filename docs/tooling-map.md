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

The planned evidence-spine workflows remain command groups under `shadowbane-lab`; they do not add
another executable. `fingerprint`, `case`, `experiment`, `evidence`, `coverage`, and `impact`
orchestrate the canonical owners above and record immutable relationships between their artifacts.
They do not absorb domain decoding or release authority. See
[the evidence-spine architecture](evidence-spine.md).

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
| Capture-once diagnostics | `capture-shadowbane-diagnostics.ps1` | exact process identity, reviewed player position, aggregate frame/read/upload telemetry, authenticated observation phases, correlated one-file timeline, patched-client alignment, graphics timing/camera rings, and offline reanalysis |
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
| Extension candidate lifecycle | `inspect-bootstrap` / `align` -> `author-bootstrap` -> `prepare-copy --dry-run` -> `prepare-copy` -> `verify-copy` / `verify-runtime-copy` -> live launch -> `wait-graphics-status` / `verify-heartbeat` -> `audit-copy` -> reviewed discard | Complete primitives. Immutable and runtime policies share one inventory audit; status waits bind PID, creation FILETIME, executable path/hash, producer, and profile. Alignment evidence never becomes write authority. |
| Multi-client release gate | `freeze-baseline` -> `author-bootstrap` -> `manager provision-runtimes` -> `manager preflight` -> manager app/workers -> `runtime-consistency gate` | Composed by the isolated-runtime installer and runtime gate. Baseline promotion remains a separate reviewed action so a candidate cannot approve itself. |
| Live PvE calibration feedback | `validate-profile` + `inspect-hotbar` -> `run-pve` evidence -> `calibrate-pve` -> `rollouts --scenario smart-camp --pve-calibration ...` | Strong artifact pipeline that links guarded live evidence to deterministic simulation. It needs a runbook, not another command surface. |
| Character-layout forensics | `inspect-process` -> analyst-directed `scan-text` / `scan-pointer` -> `validate-layout` -> `snapshot` | Deliberately interactive. Candidate addresses and layouts require review, so automatic chaining would weaken the safety boundary. |
| Native simulator observation | `observe-native-snapshot` -> versioned simulator observation JSON | Complete. One process handle binds progression, training, and vitals to PID, creation FILETIME, executable identity, capture window, and snapshot token. Focused observations remain compatibility aliases. |

The final row closes the temporal-consistency gap without adding another wrapper or memory backend.
Patch qualification should reuse the first three rows rather than introducing a second diff,
packaging, or release-gate system.

## Consolidation backlog

The current census is 62 argparse subcommands across four parser modules, plus 17 PowerShell
wrappers. The original 5,600-line `shadowbane_lab.cli` implementation has been split into the
boundaries above without changing its executable or syntax. Remaining work should follow these
priorities:

1. Keep `observe-native-snapshot` as the simulator export boundary; new native fields compose into
   its versioned payload instead of creating more separately invoked snapshot commands.
2. Centralize immutable tree inventory, path, hash, and strict-JSON validation now duplicated across
   baseline capture, package verification, and patch-diff evidence.
3. Keep PowerShell only where it adds Windows process, privilege, shortcut, VM-share, or fixed-path
   policy. A wrapper that merely renames a Python command should not be added.
4. Standardize operator documentation on the installed `shadowbane-lab` command. Reserve
   `python -m ...` spellings for maintenance modules without console entry points.
5. Keep read-only camera-state telemetry as a required capture-once diagnostic channel whenever an
   identity-bound graphics producer is supplied. The non-render consumer, sealing, gap accounting,
   process-clock alignment, and offline resource/frame correlation are complete. Extension 1.6.2
   supplies the passive bounded ring from unique base-stack fixed-function state and rejects
   same-present ambiguity. Player position uses reviewed native layout compatibility; camera state
   uses runtime-observed fixed-function authority. Neither path promotes heuristic client-alignment
   candidates automatically.
6. Establish the shared integrity package, content-addressed evidence manifests, complete
   fingerprint envelope, and research-case runner before adding deeper binary, asset, network, or
   memory-discovery commands.
7. Require every new producer to emit or ingest the common artifact and capture contracts. Do not
   create free-floating report formats, manually named capture conventions, or a second mutable
   evidence database.

This is a compatibility-preserving backlog. Renaming or deleting existing commands before their
scripts, shortcuts, and runbooks migrate would exchange visible clutter for hidden breakage.
