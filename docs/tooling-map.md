# Tool ownership map

Shadowbane Lab has several command surfaces because live client operation, offline forensics,
simulation, and release gating have different safety boundaries. This map identifies the canonical
owner of each workflow and distinguishes a real capability from a wrapper around one.

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
| Network evidence | `start-wonderbane-incoming-capture.ps1`, `stop-wonderbane-incoming-capture.ps1` | Windows Packet Monitor session lifecycle |

The similarly named control-center scripts are sequential layers rather than substitutes:
`install` creates persistent configuration and shortcuts, `bootstrap` waits for VM shares at logon,
and `start` validates and launches the current manager/listener processes. The isolated-runtime
installer composes the single-slot installer with baseline capture and multi-slot deployment.

## Consolidation backlog

The current census is 62 argparse subcommands across four parser modules, plus 17 PowerShell
wrappers. The main `shadowbane_lab.cli` module alone is over 5,600 lines. New work should follow
these priorities:

1. Split the main parser and handlers into `client`, `character`, `manager`, and `progression`
   command modules while retaining one `shadowbane-lab` executable and the exact current syntax.
2. Introduce one composable native client snapshot command before adding more `observe-native-*`
   commands; retain the focused commands as compatibility aliases until scripts and runbooks move.
3. Centralize immutable tree inventory, path, hash, and strict-JSON validation now duplicated across
   baseline capture, package verification, and patch-diff evidence.
4. Keep PowerShell only where it adds Windows process, privilege, shortcut, VM-share, or fixed-path
   policy. A wrapper that merely renames a Python command should not be added.
5. Standardize operator documentation on the installed `shadowbane-lab` command. Reserve
   `python -m ...` spellings for maintenance modules without console entry points.
6. Establish the shared integrity package, content-addressed evidence manifests, complete
   fingerprint envelope, and research-case runner before adding deeper binary, asset, network, or
   memory-discovery commands.
7. Require every new producer to emit or ingest the common artifact and capture contracts. Do not
   create free-floating report formats, manually named capture conventions, or a second mutable
   evidence database.

This is a compatibility-preserving backlog. Renaming or deleting existing commands before their
scripts, shortcuts, and runbooks migrate would exchange visible clutter for hidden breakage.
