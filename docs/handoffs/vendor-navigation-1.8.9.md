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
