# Terrain delivery verification - 2026-09-04

Status at inspection: substantial implementation source is published, but the
claimed merged and validated terrain-enabled release is not established by the
current repository and CI. This is a delivery check, not a full correctness review
of approximately 5,000 added lines. No VM was changed or visually assessed here.

## Exact source evidence

| Ref | Inspected SHA | Observed state |
| --- | --- | --- |
| Integration review | `607282aae2d6190045d6252b4f03e2fbf593874b` | Existing consolidated source and cleanup documentation; no new terrain repair. |
| Terrain repair | `9287c9ac2a5689dc9421e163305ae39211905186` | Policy, transaction, hooks, adapter, generator and integration-tool source published in PR #26. |
| Convergence | `031de7e5b77fa70c1bc0fabeab96ddfe59d4266d` | Only a merge workflow and validation note added since `da109b0`; repair head is not an ancestor. |

[PR #26](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/26)
remains open. Its base is convergence; it is not merged into main or PR #25.
The convergence validation note says a merge occurred, but the commit tree and
ancestry do not support that statement.

On the repair tip, `native/wonderbane_extension/CMakeLists.txt` and `extension.cpp`
are unchanged from `da109b0`. The new terrain runtime/adapter/hook files are absent
from the DLL source list, and the startup call is not wired. The integration tool
contains the planned build/startup edits, but those edits are not committed into
the product. The existing 1.6.13 version string is therefore not evidence of repair
activation.

## Validation evidence

- [Finalization run 33851067924](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33851067924)
  fails in `terrain_material_codegen.py` while `pefile` parses the executable:
  `AttributeError: 'NoneType' object has no attribute 'ExDllCharacteristics'`.
  This occurs before the integration tool can publish the product wiring.
- [Windows policy run 33851224645](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33851224645)
  and [transaction run 33851224660](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33851224660)
  fail because `cl` is not recognized. Their Linux counterparts pass; those
  successes do not establish the new Windows runtime or hook behavior.
- [Convergence merge run 33851286006](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33851286006)
  constructs a merge in the runner, then fails CMake configuration on Ubuntu with
  `No CMAKE_RC_COMPILER could be found`, before its push step. The product also
  explicitly requires MSVC and Win32/x86, so adding only an RC compiler is not a
  sufficient correction.
- [General repair CI 33851224613](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33851224613)
  and [convergence CI 33851286012](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33851286012)
  pass. Their inherited native targets omit the new runtime wiring, so they do
  not establish a working terrain repair DLL. No artifacts were listed by the
  API for run 33851224613. Separately claimed acceptance bundles were not available
  as repository/CI artifacts in this inspection and were not independently verified.

## Follow-up for the terrain developer

Reconcile the completion handoff against these exact refs. Correct the generation
failure and reviewed Windows build environment, commit the generated requirements
and real full-renderer build/startup wiring, validate the new runtime and the
absence of repair hooks from diagnostics-only, then publish the exact containing
commit and package receipts. Review the merge automation before reuse: it merges
a moving repair tip and its current native build gate cannot run on Ubuntu.

After source integration and package verification, the established bounded
Sea Dog's Rest three-boundary-tile visual pass remains necessary. Snapshot 6 stays
excluded. Do not weaken executable, ABI, ownership or transaction checks merely
to obtain a green build. No repair, merge, rerun or deployment was performed by
this status check.

The [navigation inspector](navigation-inspector.md) can start from the pinned
integration review source while this delivery follow-up proceeds independently.
