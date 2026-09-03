# Native action 188 trace probe

This tranche prepares a passive, process-bound trace path for Shadowbane's native
`Target Next Mob` action (`ArcanePref` action code `188`). It does **not** guess a
dispatcher address and it does not replay a client call.

## What is active now

The injected extension creates a separate mapping for each exact client lifetime:

```text
Local\ShadowbaneLab.Extension.ActionTrace.<pid>.<creation-filetime>
Local\ShadowbaneLab.Extension.ActionTraceSignal.<pid>.<creation-filetime>
```

The channel is initialized with the reviewed WonderBane PE identity:

```text
PE timestamp:     0x50A3A4E3
image size:       0x0063D000
preferred base:   0x00400000
target action:    188
```

The checked-in profile deliberately has zero target and callsite RVAs. Its status is
therefore `unconfigured`, with `active_probe_count = 0`. Transport availability is not
reported as a captured native call.

## Trace payload

Once a reviewed callsite is configured, each bounded call-entry record can preserve:

- QPC timestamp and Windows thread ID;
- target and caller RVAs relative to `sb.exe`;
- x86 `EAX`, `EBX`, `ECX`, `EDX`, `ESI`, `EDI`, `EBP`, `ESP`, and `EFLAGS`;
- up to eight copied stack DWORDs;
- the complete `action_code`, `parameter_one`, `parameter_two`, and printable ASCII
  argument only when that tuple has been proven complete.

The publisher does not follow arbitrary pointers. A future hook must copy only the
verified register values, bounded current-stack words, and tuple fields described by
the reviewed profile.

The ring retains 256 observations, reports exact overwrite counts, and commits each
slot by sequence so the host rejects torn snapshots.

## Host reader

```python
from shadowbane_lab.client_extension.action_trace_reader import (
    open_windows_client_action_trace_reader,
)

reader = open_windows_client_action_trace_reader(
    process_id,
    process_creation_filetime_utc,
)
status = reader.snapshot()
print(status.header.as_dict())

# Intentionally raises ClientActionTraceNotArmed on the checked-in profile.
capture = reader.wait_for_records(after_sequence=status.header.write_sequence)
```

## Live calibration still required

1. In a disposable reviewed client, trace ordinary UI activation of action `188`.
2. Identify the exact call target and originating callsite.
3. Record their RVAs, enough preimage bytes to reject drift, the executing thread, and
   the bounded register/stack contract.
4. Prove where all four Arcane tuple fields come from; do not infer them from the
   configured hotkey.
5. Add those facts to the reviewed profile and install the passive hook only after PE
   identity and preimage verification pass.
6. Collect several real `188` activations and compare them with unrelated actions.

Replay remains a later step. A successful passive trace does not prove that calling the
target from another thread or context is safe.
