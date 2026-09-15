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

## Exact package checkpoint

Source `a440cfdbfcbfe30bd0aa3b6c9619110bf7fa3efe` is pushed. The exact-source
package is `E:/Projects/shadowbane/artifacts/vendor-packages/01bbe98a/`.
All required full and diagnostics-only native gates, real IPC/image checks,
installed host entry points and installed vendor/navigation contracts passed.
The isolated source archive ran 2,264 host tests, with 14 expected skips (the
worktree additionally has the built native byte-agreement fixture).
The two previously deferred native transparency diagnostics remain recorded in
each profile; this remains a diagnostic package, not full graphics acceptance.
All 61 packaged artifacts were independently checked against archive hashes.

- Package SHA-256: 6104a8d9c1ad96082cacdb2ed7fe3f37bbcc6e45ff39270e2fd4707326413365.
- Diagnostics DLL SHA-256: efef80b69c3e227000d3871309ad3f33299d298b16cc594b01cb732eb353ed18.
- Host wheel SHA-256: 31daf5b21bc6ca40a81bdd385b45c3f9205504a4b7165d425ccd5e58c448227b.
- Prepared game SHA-256 remains b646ae32ebc44be45a7a65da3c764e1cd67f63f45fca91262b75f21fd11002f3.

Host-only payload, exact authored manifest, checksummed plan and reversible updater
are in `E:/virtual-machines/shadowbane-testing/diagnostics/vendor-1.8.8-a440cfd`.
Python compilation and PowerShell parsing passed. This replaces only the DLL in
the client inventory, preserves the official-client drift guard and both patched
game assets, updates host launch paths and saves rollback copies. It checks
historical job/discovery records and settings before/after application. It refuses
to apply with Shadowbane or the manager running. No guest staging or installation
has occurred; guest dry-run validation is still required.

CI: https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34964383768.
Five jobs passed at this checkpoint; both native jobs were still running.

Automatic approval review rejected a later read-only VM connection and then
rejected the identical retry citing the existing authorization. Its stated reason
was that reading the plaintext saved password from the unattended-install XML for
guest authentication lacked sufficiently specific user authorization; it rejected
"you know the answer" as insufficient. No alternate credential source or connection
route was attempted. An explicit question now asks permission for that exact saved
credential use to install and verify this update, and asks when the game is closed.

Next active todo: obtain that response, stage using prepare-town-update.ps1 and
inspect its guest dry-run receipt; verify game exit and the exact idle manager,
then apply, update the existing dashboard shortcut, relaunch and verify identities.
Do not regenerate the package from a documentation-only successor commit. After
login, run a new guarded discovery operation and retain all historical requests.

## Installed, then recovered after a game exit

The user explicitly answered "Approved; Shadowbane is closed" to the scoped
question authorizing this VM's saved password from its unattended-install XML
for access, installation and continued testing. The same established connection
then succeeded. That approval block is resolved; do not ask for it again for
this scope. All seven CI jobs for a440cfd passed.

Guest staging and the read-only updater dry run passed. With no sb.exe running
and the manager reporting zero slots, the exact manager PID 6272 / FILETIME
134339397794679601 was stopped. The updater changed one client inventory entry
(the DLL), updated package metadata and host launch paths, verified five rollback
copies and preserved all 41 tracked JSON/settings files. The dashboard desktop
shortcut now uses host-0.3.17; its previous shortcut has a separate backup.
The official-client drift guard and patched game/asset hashes remain intact.

Initial launch was PID 5828 / FILETIME 134339465852996366, HWND 4457430.
The loaded DLL hash, native 1.8.8 and exact healthy worker binding were verified.
After the user entered the world, a guarded fresh discovery was prepared, but
the user reported the game crashed before it submitted a request. Read-only
inspection found no new preflight, start request, response or discovery journal;
the latest records were still the earlier terminal 1.8.7 operation. No request
was replayed. The interrupted script is now pinned to the exited PID/lifetime
so a delayed invocation cannot act on a replacement client.

A recent Application-log check found no sb.exe event 1000/1001 to explain the
exit. Do not classify the cause as either automation-related or unrelated.
The manager released the dead client and reported zero slots. The same desktop
launcher reopened the verified client; no game or job files were reset.

Current recovery launch: PID 6532, FILETIME 134339469942878355, HWND 394352,
instance client-9481a8c69158cfc5d50bdb13523117a37cd86054a7cc6d6f8e69b5ed128dc9a9.
The exact loaded DLL is efef80b69c3e227000d3871309ad3f33299d298b16cc594b01cb732eb353ed18.
Worker 5452 / FILETIME 134339469971652010 is healthy, native 1.8.8 is initialized,
and no operation is queued or active. Root mode was 3 at the check; the user has
been asked to log Treehugger back into Rooty, without opening any menus.
Refresh all identities before the next action.

Private activation, crash-followup and crash-relaunch-verification receipts are
in the existing vendor-1.8.8-a440cfd diagnostics and guest upgrades directories.
The package source remains a440cfd, not this documentation successor.
Next active todo: verify the new in-world identity and run one fresh manager-owned
building/vendor scan; then complete automatic recipe/inventory navigation and
bounded town scheduling. Historical crafting and discovery records remain intact.
