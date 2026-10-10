# PvE terrain return delivery — October 10

## Observed return failure

After the user repositioned Umbra at the same Connauch Henge camp, the normal
bounded .94 run confirmed three exact NPC health-zero results and their cleanup.
Native chase moved 72.694844 units. The two subsequent camp-return searches
failed at 48.375 and 53.468 seconds, before any host movement was dispatched.
Cancellation and cleanup succeeded, then all five buffs resumed maintenance.

Exact cache, native geometry, object-density and learned-obstacle replay matched
5,760 sampled cells, 334 blocked cells, 4,940 weighted cells and 4,051 density
cells. The occupied 20-unit cell mixed a steep edge with nearby walkable ground;
its sample spread of 66 crossed the existing 64-byte threshold. Existing fine
planning copied that inferred coarse blocker into every child cell.

The .95 repair preserves terrain provenance and resamples only the failed local
planning window using the original raster and geometry. Explicit and learned
obstructions retain their semantics, costs remain costs, and the original map is
not rewritten. Refinement remains bounded by native raster spacing and existing
sampling/search budgets. The complete exact offline replay found the return
route in 0.183 seconds; independent replay took 0.190 seconds. These timings and
computed routes are not live return acceptance.

## Source and qualification

Reviewed source is PR #152 at `cb88d5675b025d02f435138494641a63e58a181d`,
on `codex/pve-camp-return-routing-20261010`, based on refreshed main at PR #151
merge `70da648dac59e99f2f02949a93a656c638d067e1`.
Release `714928e006912aaefcd9c448d78fadc1b0f90021` is pushed on
`codex/pve-terrain-release-20261010`. It retains installed graphics and exact
native .60/assets from `5a46687dce579417f8b8bd086c4c6929a68c513a`.
The sole composition conflict was the branch map, resolved to the current
reviewed feature document. Runtime files had no conflict.

Independent source/composition review passed; 107 focused tests passed in both
author and reviewer runs. The exact clean release passed 6,107 host tests with
41 optional skips. Qualification tooling passed 73 tests. The package completed
all 16 stages, including both native profiles and installed host checks.
Independent artifact audit passed: all 486 modules match source, wheel and
installation. Both profiles passed 76 movement, 86 combat and 237 actor cases
without skips, failures or errors; six desktop cases and one real worker
handshake passed. All 15 hosted checks passed at the exact reviewed head. PR #152 merged as
`e0617db29220624736463b0221d5564e112c95c9`; the normal main checkout is clean.

| Qualification evidence | SHA-256 |
| --- | --- |
| Exact host attestation | `b95339f9dc9e8cd5c8d54fb940304472c01d44a1005d108b0da194a4000edb51` |
| Frozen qualifier sources | `46306ff7f0646ceca309cea363bcf00363438b3071a6d5743ca588da64eaffa7` |
| Package receipt | `ad8d66670cde828df66088b63d6ec5a9836248d588d5c725175ab05724e6bd35` |
| Host wheel | `9015ef104c8799b9690de61f03c49e69f2bdd3b360e0d9d64e370060ccaa8045` |
| Source archive | `7b89565a5fa3c7e0ba759e2411f6544f760ae0639fa44bdb1ee01c298622f615` |

Private reproduction evidence is under `artifacts/pve-camp-return-20261010`;
qualification and deployment evidence is under `artifacts/bot-deploy/20261010-host95`.
No private captures or third-party client assets are included in the source PR.

## Verified host-only installation

The .95/.60 host is activated from release `714928e0`. The game stayed open as
PID 5108, creation 134361291422429449, window 787258, with unchanged native DLL
`c0a3f2028ecf410b7d959ce9dcf7ad58c5937f04a9c4b5d9a08b25eaca257c12`.
No client files were written. The exact old manager/worker were stopped before
switching the host. Desktop shortcuts now select .95 where they invoke the host.

Activation verifies 486 installed modules and 9,558 retained records with zero
exclusions. Ten expected generated records changed: manager startup, worker
reservation, dispatch permit, preparation status and six startup capabilities.
Settings, saved jobs and historical journals remain in place. The new healthy
manager is PID 8884, creation 134361359093056163; the sole bound worker is PID
8108, creation 134361359122427663, ID `worker-5e7a40b3605c44b7940431a771ae13e3`.
No rollback copies were created.

| Installation evidence | SHA-256 |
| --- | --- |
| Reviewed update plan | `97e8020a596073f425487aeb02482016f309de249f0c7c3bd2e487a1d749adb1` |
| Prepare | `de5a40e36f61a85dab6c4d14cd8c010d204fe44dec0453c5c1365ba7b935addc` |
| Exact manager/worker stop | `7099a0b7c9edc0fa796b370ebfb41d0ccce9ef9b04cb35eef848249b0b19bb00` |
| Apply | `665ea3534e4655699c1095c43f69dc722dd5c8ad0639c8e3919a65b76fa7dcd8` |
| Shortcuts | `7df4b80c51b65d87b9461c4b24d7fe430eb524c40a0f438eaaecd4da4e971973` |
| Activation | `a7b2f298f47a08b822a4b12c2387ac63fb0ac9bae87b00ddba2f2b77d73caafe` |

## Live return attempt and remaining work

The first .95 check used the supported manager TRAVEL operation to the exact
original anchor, LT 78205.0625 / LG 54244.74609375. A fresh census matched the
same Umbra lifetime, worker and Connauch Henge placed zone `[578,79]`, approximately
72.6 units from that anchor. Operation
`operation-e62b37e52d9a4eb388e711bc7b8a39d2` failed during native acquisition,
before the travel executor or terrain planner ran. The native result was
`INHIBITED`; generation 8 and owner NONE were unchanged. No route was dispatched
and no movement acceptance is claimed. The status-to-receipt flags 23/7 differ
only in the informational controller-API bit; they do not prove lost focus.

The wrapper did not retry the start or issue a post-failure Resume. Fresh
same-worker preparation captured at 1791662441.877 followed the terminal receipt
at 1791662437.980 and was maintaining with no local pending action or active/queued
operation. This proves production handback, not successful travel. The passive
sample showed concentration and stance present, with precision, Beorc and
transform missing; manual-activity admission inhibition prevented new upkeep
entries. Full buff coverage is not claimed.

The retained native input-change history contains continuous events 1–73 with
zero dropped or missing records. Event 73 at tick 42037734 set UI/text input
ownership; no subsequent gate transition occurred through tick 42378125. The
acquisition snapshot at 42312468 lies inside that interval. Native processing
handles UI/text ownership before queued movement commands, providing a sufficient
veto for this refusal. Foreground remained valid. The trace does not identify
the particular widget or exclude a simultaneous preparation veto; it does not
by itself justify relaxing admission checks. The user subsequently reported that
the Who search had been opened and typed into, but was already closed. Current
UI ownership may therefore be stale; the reader and native focus-reset semantics
must be checked before attributing the refusal to an interface still being open.
The subsequent passive sample still reports input ownership with no active or
queued operation. Source inspection found an unconditional focused-text fallback
that does not honor the native text-enable global. Whether the closed Who control
is retained through that path is under direct read-only investigation.

Source merge, qualification and installation are complete. Next: retry the
original return route after resolving the reported stale input condition, verify arrival,
cleanup and buff maintenance, and retire obsolete .94 software. In parallel, the
user requested `/come` from any current group member; its native chat, sender,
group membership and navigation integration are under review. No rollback copies
are allowed; follow [deployment policy](deployment-policy.md).
