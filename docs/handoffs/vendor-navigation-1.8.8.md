# Vendor discovery correction: 1.8.8 / 0.3.17

Owner branch: `codex/vendor-rolling`; integration destination:
`codex/native-lifecycle-hardening`, followed by reviewed `main`. Not merged.
The normal checkout remains on main. This document supersedes earlier login-pending notes.

## Live evidence

Treehugger successfully entered Wonderbane on reviewed game 1.3.38.7,
native 1.8.7 / host 0.3.16, source c64eb0d. The isolated desktop launcher now
uses the patched game and official assets; the login patch mismatch is resolved.

Fresh operation `operation-66a25bf7681c4d44b54e08114c50168a` found 11 nearby
buildings. Its first building request, `b992da77-deca-46ab-bded-0be730d91ec8`,
was submitted for Tree of Life (2201004). The worker cancelled 3.35 seconds
after admission because its dispatch permit had expired by 0.181 seconds.
The original operation and navigation journal remain terminal and unchanged.

Separate later read-only observation confirmed that Tree of Life's real
AssetManagement HUD was visible in mode 6, with exact owner/backlink and matching
selected/displayed building keys. Its roster contained Viktor the Runemaster
(2204862) and Simeon the Bursar (2204864), with three positions and one vacancy.
The selected entry pointer was nonzero with a valid hireling-row vtable but an
empty key. The native snapshot rejected that combination. Native inspection
confirmed the original request remains latched unresolved; do not reset it or
replay it. No crafting, Keep, disposal or vendor opening was sent.

Private evidence is under
`E:/virtual-machines/shadowbane-testing/diagnostics/vendor-1.8.7-c64eb0d`, including
`capture-read-only.json`, the original operation journals and `permission-timing.json`.
The typed read-only transition receipt is also in the guest upgrades directory.
No private capture, binary or credential is included in Git.

## Corrections

A selected vacancy now remains a valid building snapshot. Native capture verifies
row kind, populated marker and exact key consistency; it retains the selected
pointer for equality checks. A vacancy cannot prove an individual vendor window.
Opening still resolves an exact populated roster row and retains active-manager,
HUD membership/backlink, scene, lease, deduplication and unresolved-request guards.

Dashboard reconciliation no longer holds application slot locks during blocking
session refresh. Session lifecycle locks and atomic identity publication remain;
renewal independently checks fresh process inventory and the current binding.
A deterministic regression reproduced skipped renewal in the old implementation
and now passes for healthy, paused, exited and replaced clients. This fixes a
confirmed starvation path; the precise cause of the single live 0.181-second
expiry is not proven. A separate 20-second passive dashboard poll saw no expiry.
The two-second permit lifetime and fail-closed cancellation are unchanged.

## Validation and next work

Full local host suite: 2,265 passed, 13 skipped. Whole-tree Ruff passed.
All three native navigation CTests passed, including vacancy, invalid row/key,
exact-key response, duplicate suppression and late-response quarantine cases.
Host discovery tests traverse two buildings with selected vacancies and preserve
an existing crafting record without replay. Package validation remains next.

Next active todo: package this exact committed source, stage the verified native
1.8.8 / host 0.3.17 update, then replace the extension only after the game closes.
A new game lifetime permits a fresh discovery operation; historical journals
remain preserved. After discovery, finish recipe/inventory opening, durable town
selections and the bounded multi-vendor scheduler. Unknown affixes remain kept;
automatic disposal is still unqualified and disabled.
