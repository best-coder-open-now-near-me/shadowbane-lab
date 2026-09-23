# Vendor HUD ownership correction: 1.8.9 / 0.3.18

Branch: `codex/vendor-rolling`. Integration destination:
`codex/native-lifecycle-hardening`, then reviewed main. Not merged.
The normal main checkout remains untouched. Installed runtime remains full
1.8.8 / host 0.3.17 from a440cfd until this correction is packaged and activated.

## Completed deployment and live verification

The full-profile 1.8.8 DLL was installed after the user confirmed closure.
SHA-256: c535161bb49aa86f3c8719885206d822f2d9e6379678c44bd075e9028b7ccd4a.
The updater preserved all 47 tracked JSON/settings files and five rollback files.
The action mapping was opened read-only and its header matched the exact game
lifetime before login. Host 0.3.17 and the existing desktop shortcuts are active.
Explicit saved test-VM setup-XML credential authorization remains in force.

The first full-profile launch (PID 5300) froze/exited before the user reached the
world. No scan or native action ran in that session. It had already exited when
checked; the ordinary verified shortcut reopened it without forced termination.
The later PID 6832 / creation FILETIME 134339476988991771 / HWND 1442696 was
responsive and in-world, with exact Treehugger/Wonderbane identity verified.

Fresh operation `operation-ebc6b9f6bc3e49a0a4f0ef1b5075a92b` found 11 buildings.
It submitted one Tree of Life (2201004) opening, native request
`b806959f-da6b-4317-a1b5-d4dc59b260ee`, then stopped with unresolved transition.
No retry, hireling action, crafting, Keep or disposal was sent. Preserve its
terminal journal and native uncertainty; do not clear or replay it.

The native snapshot now correctly accepts the selected vacancy: row kind 9,
populated marker 0, empty key, valid row vtable. AssetManagement is visible,
mode 6, with exact owner/backlink and displayed/selected building keys. Its
independent roster again contains Viktor the Runemaster (2204862), Simeon the
Bursar (2204864), and one vacancy. This live-qualifies the vacancy correction.
The permission sampler recorded 101 samples, zero expirations, maximum age
0.5764 seconds. Renewal did not cause this stop.

## Remaining ownership defect and source correction

The global at RVA 0x16a7c1c is the last manager selected by action dispatch; it
is not exclusive ownership of every visible management HUD. Reviewed building
activation at RVA 0x7d14e0 first selects root+0xa4. Its kind-5 branch calls that
manager's Open and then posts ordinary action 0x515 at RVA 0x7d15c6.
The action's table index is 1 at RVA 0x7cdca9, whose entry at RVA 0x7cdc60 reaches
RVA 0x7cc094. That handler assigns root+0x90 to the global at RVA 0x7cc0a7 before
opening its secondary panel. The AssetManagement HUD remains independently
visible and owned by root+0xa4. Thus requiring the global to equal root+0xa4
prevents confirmation of the legitimate building response.

Native and host confirmation now use the rooted, typed, visible HUD ownership
already validated by capture, without requiring equality with that unrelated
last-dispatch pointer. The pointer is retained in snapshot equality, so changes
still invalidate action admission. No pointer writes or new action path were
introduced. Exact building/vendor keys, HUD type/backlink/stack membership,
scene, lease, foreground, occupied-row validation and deduplication remain.
Closed or mismatched windows and late/unresolved requests remain rejected.
City Command's separate synchronous opening checks are unchanged.

A later direct pointer sample occurred after the user logged off, with a different
root vtable; it is not evidence about live building ownership. The user clarified
that logout and reported being back in-game. Do not misclassify that root change
as another unexplained crash. No new scan has been issued after the clarification.

## Validation and next work

All three native navigation CTests pass. 68 focused navigation/worker/application
host tests and whole-tree Ruff pass. Tests cover secondary action managers with
selected vacancies, exact vendor responses, closed/wrong-key/offline rejection,
HUD ownership corruption, duplicate suppression and uncertainty preservation.
Exact-source package validation is next and must select the **full** DLL artifact;
a diagnostic package purpose is not a request for the diagnostics-only DLL.

Private evidence: host diagnostics and guest upgrades under vendor-1.8.8-full-a440cfd,
including activation-verification.json, prelogin-recovery.json, transition-review.json,
the immutable operation copies and discovery-permit-samples.json.
Next active todo: build/stage the exact full 1.8.9 / host 0.3.18 package, then apply
after confirmed game closure, verify loaded hash and read-only action mapping,
and run one new discovery after login. Recipe/inventory navigation and bounded
town scheduling remain unfinished. Unknown affixes remain kept; disposal stays off.

## Exact package staged and verified

Source `7870b3fbb9f9f6b002f0df37eb5bfe543dcac8f9` is pushed. Exact package directory:
`E:/Projects/shadowbane/artifacts/vendor-packages/5d6badf3`.
All required full and diagnostics-only native suites, real IPC/image checks,
installed entry points and vendor/navigation contracts passed. The isolated source
host suite passed 2,265 tests with 15 skips. The two previously deferred graphics
transparency diagnostics remain recorded separately for each profile. Whole-tree
Ruff passed. All 61 archive artifacts were independently hash-verified.

- Package SHA-256: c293b409be9b92eedde05fc4688859ff236dd25c2c50170afaf2d1fe6e9383f6.
- **Full-profile DLL** SHA-256: 46f195e9a323d37f2f7197491d54ae0d8bb8280f92d591e9fc7ed1dde3dbeaa6.
- Host 0.3.18 wheel SHA-256: d116970b1f0e744bb5a3e3ef6f7aaeb62840aa30de8ef874ff0df5eedc6b9ae1.
- Prepared game hash remains b646ae32ebc44be45a7a65da3c764e1cd67f63f45fca91262b75f21fd11002f3.

All seven CI jobs passed:
https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34977110026.

The full-profile payload, exact authored bootstrap manifest, hash plan and rollback
updater are staged under host diagnostics `vendor-1.8.9-7870b3f` and guest runtime
`upgrades/1.8.9-7870b3f/payload`. Host environment `host-0.3.18` is installed.
The updater's guest read-only dry run passed against installed full 1.8.8; the
running game, launchers and manager still use 1.8.8/0.3.17. The update plan and
updater explicitly require the full profile and its archive-derived DLL hash.
No game or job mutation occurred during staging. Python and PowerShell syntax
checks passed. Guest prepare.json and validation.json are copied to host evidence;
validation.json is UTF-16 from Windows PowerShell redirection.

The user has been asked to close Shadowbane. Next active todo: after confirmation,
verify the exact idle manager and game exit, apply this staged updater, update the
existing dashboard shortcut from host-0.3.17 to host-0.3.18 with a backup, and
relaunch through the same game shortcut. Verify exact loaded full DLL and open its
action mapping read-only with matching PID/creation time before requesting login.
After verified Treehugger login, issue a fresh guarded scan with a new intent file
in this upgrade directory. Never replay earlier failed requests. Do not rebuild
from a documentation-only successor commit. Town automation remains unfinished.

## Activated after confirmed closure

The user confirmed Shadowbane was closed. Fresh manager status had no slots;
manager PID 892 / creation 134339474790612939 was verified before stopping it.
The staged updater applied successfully and preserved all 56 retained files,
including crafting journals. Its five-file rollback and the previous desktop
dashboard shortcut are retained under upgrades/1.8.9-7870b3f.
The existing dashboard shortcut now targets host-0.3.18. The unchanged game
shortcut relaunched through its reviewed launcher; the dashboard restarted
without opening a browser or taking focus.

Activation evidence confirms source 7870b3f and the exact full DLL hash above:

- Game PID 8580, creation FILETIME 134339629094953274, HWND 918400.
- Instance client-3f219142fba424a5dcceba45d7284b8a15a4f9440cbabbaf1c2d1dcb008ecf64.
- Native extension 1.8.9 initialized; host 0.3.18 has a healthy, exact-bound worker.
- The native action mapping opened read-only and its decoded header matched
  that PID and creation time, with capability_flags 1. No command was sent.
- Manager has no active or queued operation. No previous request was replayed.

Private activation-verification.json, update-receipt.json and retained-files.json
are preserved in both the guest upgrade directory and host diagnostics
vendor-1.8.9-7870b3f. These checks certify activation, not in-world discovery.
The user has been asked to log Treehugger into Rooty and leave the game in front;
no menu setup is needed. Next active todo: verify that live identity and run one
fresh discovery with a new intent file pinned to this exact lifetime. Recipe and
inventory navigation, bounded town scheduling, and affix disposal qualification
remain unfinished. Unknowns remain kept and automatic disposal stays disabled.
