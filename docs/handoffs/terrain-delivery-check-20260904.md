# Terrain delivery verification - 2026-09-04

Status at inspection: substantial implementation source is published, but the
claimed merged and validated terrain-enabled release is not established by the
current repository and CI. This is a delivery check, not a full correctness review
of approximately 5,000 added lines. No VM was changed or visually assessed here.

The subsequent correction at `3b344f0` is inspected in the
[v2 follow-up below](#v2-correction-follow-up). Its delivery run fails before
assembly/validation and produces no artifacts; convergence remains at `031de7e`.
The original evidence below remains a record of the first delivery attempt.

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

## V2 correction follow-up

The developer's correction branch is `codex/terrain-material-repair-final-v2`
at `3b344f024558ed806ce9bc661ac8a24d680a97ff`. It adds a delivery workflow and
`tools/terrain_delivery_finalize.py` over the reviewed repair source. The corrected
product tree is intended to be generated and committed by that workflow; it has
not yet been published to convergence.

Code inspection confirms these changes are staged in the finalizer/workflow:

- ABI analysis starts at the function entry, follows reachable direct branches
  within executable PE sections, treats calls as fallthrough, and rejects indirect
  jumps, inconsistent return cleanup and overlapping instruction interpretations.
  PE parsing changes to `fast_load=True`. These changes are present as generator
  rewrite logic; successful exact-client generation is not yet demonstrated.
- Generated CMake wiring assigns runtime sources and the enable definition to
  the full profile. Both generated Visual Studio project files are inspected for
  runtime inclusion/exclusion and the enable definition before their builds.
- Native builds explicitly select Visual Studio 17 2022 and Win32 for both
  profiles. The workflow orders Python/Ruff/package gates, native builds/CTest,
  DLL receipts and artifact upload before the convergence push.

[Delivery run 33860581515](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/33860581515)
fails during `Assemble clean convergence plus reviewed repair` with
`Committer identity unknown` / `fatal: unable to auto-detect email address`.
The workflow attempts `git merge --no-commit --no-ff` before configuring
`user.name` and `user.email`; those settings occur only in a later commit step.
The failure precedes the finalizer, generation, product commit and all product
validation. The run reports **zero artifacts**. General CI on `3b344f0` passes,
but it cannot substitute for the failed generated-product delivery run.

The next developer checkpoint should:

1. Set repository-local Git committer identity before the first merge operation.
2. Require the exact reviewed repair SHA `9287c9ac2a5689dc9421e163305ae39211905186`
   (or a newly reviewed explicit replacement) before assembly. The current
   workflow resolves `origin/codex/terrain-material-repair` dynamically and checks
   ancestry against that resolved value, not against the stated reviewed SHA.
3. Remove the post-delivery force-pushes of the final-v2 and completion branches
   unless the owner separately authorizes rewriting those histories. The guarded
   fast-forward of convergence is the relevant delivery operation; leases on
   helper branch rewrites do not make them fast-forwards.
4. Run the corrected delivery path to completion and inspect every gate, actual
   artifact receipts and committed product wiring. Then verify the published
   convergence SHA and ancestry before updating the completion claim.

No workflow was dispatched, source repaired, ref rewritten or VM changed during
this follow-up. The inspector baseline and pending terrain visual pass are unchanged.
