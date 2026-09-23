# Vendor manager host 0.3.9

Feature branch: `codex/vendor-rolling`; integration destination:
`codex/native-lifecycle-hardening`, followed by reviewed `main`. Unmerged.
The normal checkout remains on `main`; continue vendor work in its existing worktree.

## Focus handoff

Start accepts the exact owned random Gilded Scepter recipe while the dashboard
has foreground focus. The durable job waits visibly for the game/vendor window
to become ready before submitting a crafting action. Switching away between
actions returns it to that wait; returning to the game continues the same job.
Stop, lost dispatch permission, changed ownership and the one-hour deadline
still prevent further submissions.

An already-submitted Create or Keep is reconciled against its exact request
and queue/inventory transition even while unfocused. Only correlated receipts
without in-flight or unresolved flags are accepted. No mutation is retried.
The game window is not automatically opened or focused; recipe and Inventory
opening remain manual. One job still fills one capacity batch, with no refill
or automatic disposal. Unknown affixes remain preserved.

## Validation and deployment

Local validation: 2163 host tests and 580 subtests passed, with 14 explicit
environment skips. Ruff and whitespace checks passed. Regression coverage
includes starting unfocused, focus loss after Create and Keep, receipt
reconciliation before waiting, and Stop/owner/deadline/permit changes while waiting.

Installed source: `e26a5e39f91238fc289e855cc9a72bc63e994bc7`.
Wheel SHA-256:
`f65f11451cf645edcb3b27ea44e82fd2982f8d61b41628cc6c0ecf8709aafc92`.
The separate host 0.3.9 environment, manager and worker passed installed source,
capability and exact current-game binding checks. The previous job remains
complete with three retained items; no new crafting action was sent during
installation. The game stayed running on native 1.8.2. The test VM desktop
WonderBane Vendor Dashboard shortcut and its opener now use host 0.3.9.
Reopen that shortcut after an upgrade or browser reload. The token is retained
only in page memory, so browser reload loses authentication; the dashboard
Refresh button updates status without reloading the page. The owner encountered
this during the check, and reopening through the launcher restored the
authenticated URL. No new batch had started at that point.
All seven CI checks passed. The latest live result is recorded below;
full batch qualification remains incomplete.
See [previous installed handoff](vendor-manager-0.3.8.md) for its exact package
and uninterrupted three-item batch evidence.

## Live focus check and unresolved Create

The owner started the job from the dashboard and left it in front. The job
waited with zero Create requests and three empty production slots. Once the
native game and vendor readiness checks passed, the same job advanced without
Resume and submitted one Create. No queue transition arrived within the timeout.

The runner stopped in review with one uncertain request and no confirmed new
items or Keeps. Later passive reads still found empty production; native state
still reported in-flight. The owner saw no error. Nothing was retried, repaired
or reset. This verifies the waiting behavior and continuation into dispatch;
a complete live 0.3.9 batch and the missing response diagnosis remain pending.

All seven CI jobs passed for the installed source. Local validation remains
2163 tests and 580 subtests passed, with 14 explicit skips.

Active: diagnose the missing Create response and resolve its uncertain outcome
before another crafting attempt. Native window opening, inventory/resource
limits, full affix evidence and disposal remain after that.

Publication approved by the owner on September 14. The implementation
`e26a5e3` and this handoff are delivered on `codex/vendor-rolling`, targeting
`codex/native-lifecycle-hardening` and then reviewed `main`.
No integration or merge has occurred.

## Follow-up investigation

Static review used the exact installed executable after an older local fixture
failed the executable identity check. The Create owner forwarder constructs
and submits the production message; its return is not server acceptance.
This does not prove serialization or server processing for the uncertain request
and does not identify the failure cause.

The latest idle inspection found the vendor management menu closed and the
action unresolved. No new request, reset or recovery was attempted. The owner
has been asked to reopen Malik's management menu without crafting or completing
anything. Next: check the current queue and ownership before further diagnostics.
