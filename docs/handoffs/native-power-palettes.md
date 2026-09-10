# Power Palettes planning handoff

Status: second-review revisions incorporated; documentation delivery only.

## Source, branch and integration destination

- Documentation branch: codex/power-palettes-plan.
- Source baseline: 310620bc884464b26aa44d9da366af03f9c428d0 from freshly fetched origin/codex/native-lifecycle-hardening.
- Initial adoption checkpoint: 3bf2c4f910e16ad66a0c655af340d5ae23a8a47a.
- Review/inclusion target: codex/native-lifecycle-hardening. Shared eventual merge destination: main.
- Inclusion status: planning changes remain on their own branch; no integration or main merge is performed by this task.
- Review range: [documentation changes against the rolling integration owner](https://github.com/best-coder-open-now-near-me/shadowbane-lab/compare/codex/native-lifecycle-hardening...codex/power-palettes-plan).
- Authoritative plan: [Power Palettes](../power-palettes.md).
- Source decision and verification limits: [source-selection record](../investigations/power-palettes-source-selection.md).

The documentation worktree is E:/Projects/shadowbane/.worktrees/power-palettes-plan. The normal E:/Projects/shadowbane checkout stays on main; existing feature worktrees are untouched. The standalone earlier plan export is superseded by this repository document.

Use the documentation branch to review this contract. Before implementation, refresh the source-selection record against the current integration owner; do not automatically branch from the earlier exported plan or an old source pin. No production Power Palettes branch has been created.

## Review requests incorporated

| Review request | Contract and verification changes |
|---|---|
| Negative feasibility gate | Section 1 and Phase 2 stop production on failure and require a bounded calibration report; no layout/persistence/substitute continuation. |
| Native UI qualification | Section 2 explicitly requires participation in the game UI hierarchy, coordinates, focus, hit testing, drag ownership and lifetime. |
| Source-selection deliverable | Section 5 and Phase 0 require a record before production branching; this task supplies the documentation source record. |
| Locked empty-cell policy | Whole visible rectangles own input, including gaps and hidden empty-cell visuals, in both lock states. |
| Locked rejecting target | Locked palettes remain native routing targets and consume/reject without Shift-create or world fall-through. |
| Normative drop routing | Section 3 orders owning stock targets, eligible palette cells, rejecting regions and last-resort Shift-create; chrome/closing/stale destinations are explicit. |
| Activation-boundary revalidation | Recheck the interaction token at the stock activation phase with one admission per native pointer sequence, including reentrancy. |
| Separate disk persistence | UI/model publication is independent of asynchronous save; a failed save remains dirty without rolling back a working palette. |
| Avoid assumed native mechanisms | Calibration selects verified resize/removal/unlock and copy/move indication mechanisms while product behavior stays fixed. |
| Callback retirement | Account for fetched and executing calls; verified shared hooks may remain immutable terminal pass-through with process-pinned code. |
| Identity priority | Logical power ID first; stable server-issued character ID plus shard first, discriminated exact-name fallback only when unavailable. |

Two reconciliations are deliberate: stock-target priority preserves stock-owned drags without enabling the excluded palette-to-hotbar transfer; shared terminal hooks may remain after disable without retaining live palette receivers. Neither changes the native-only product goal.

The decision register, sample JSON, phase gates, tests, connected checklist and definition of done reflect the same rules rather than leaving conflicting earlier wording.

## Validation scope

Document validation covers the 20 numbered sections, balanced code fences, parseable illustrative JSON with explicit identity mode and matching grid size, the 44 connected acceptance items, one active todo, local Markdown links and git whitespace checks. The diff is documentation-only.

No native/Python production build, client calibration, package, installation, deployment or connected acceptance is claimed. Existing CI/profile requirements are recorded for future implementation, not marked passed by this task.

## Remaining work

The requested document revision is complete. Next implementation item: finish Phase 0 readiness by refreshing source selection, completing reuse-boundary verification and running required baseline tests/profile builds before native changes. Then proceed to passive calibration and the independent keyless-native-button proof.

All Phase 1–8 implementation and acceptance work remains open. A failed feasibility proof ends the feature line with its calibration report.

Next integration step: review this documentation branch into codex/native-lifecycle-hardening under its existing ownership, then retain the plan in that line's eventual main integration. No merge is implied by publishing the branch.

The clean documentation worktree is retained for that review; it is not retired because its source remains outside the integration destination. No task-generated private captures or client binaries are included.
