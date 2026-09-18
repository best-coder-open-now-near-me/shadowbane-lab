# Tree companion navigation: 1.8.15 / 0.3.24

Branch: codex/guard-upgrades. Exact packaged source: 861985e (pushed).
Review destination: codex/vendor-rolling, then
codex/native-lifecycle-hardening and reviewed main. Not merged.

## Live findings

The 1.8.14 runtime confirmed the warehouse building and returned to Ulmer's
resources automatically. City Command opened from its initially closed state
and returned 60 nearby structures. This qualifies the first-open correction.

Discovery then opened the Tree of Life. Its complete two-hireling roster arrived,
but the Tree's guild panel appeared above that roster. Native navigation required
the roster to be first, so its request timed out. The exact unresolved request
remains retained; no retry, gold transfer or guard upgrade followed. The cache's
empty hireling lists do not prove these structures have no guards.

## Correction and validation

Navigation recognizes only the Tree companion owned by the root's exact
ArcGuildTreeManager, with matching manager/HUD backreferences, the active panel
flag and the same building key as the initialized asset roster. No hireling HUD
may be present, preserving the guard-upgrade reader's shared navigation gate. This lets the
owned roster acknowledge a building open beneath its own companion panel.
Different buildings, unrelated owners, inactive panels, unknown HUDs and amount
dialogs still block. The entire HUD list is validated. Spending and crafting
front-window checks are unchanged; no wire layout changed.

The full native extension compiled. Navigation, funding and vendor native tests
passed, including negative cases for every companion ownership/key/active field,
amount-dialog blocking and malformed list links. Five version tests and lint passed.

Exact-source packaging passed 2,675 host tests (18 skipped), both required
native profiles, executable binding, real IPC and installed-host checks. Six
additional installed guard/funding comparisons passed. All 61 artifact hashes and
the archive were independently verified. Two pre-existing graphics transparency
diagnostics still fail per profile; whole-product acceptance is not claimed.

Guest staging, read-only update validation and activation passed. With the game
and manager stopped, the updater installed native 1.8.15 / host 0.3.24 from the
exact packaged source above. Independent verification confirmed the installed
client manifest and DLL, host version and all 171 retained records/settings.
The existing dashboard shortcut now uses that host. The background manager
restarted successfully with no open or bound clients and no reconciliation issues.
The game was left closed for the user to launch through WonderBane Vendor Test.
The superseded intermediate build was removed rather than archived.

Active todo: after user launch/login, verify the loaded extension and fresh client
binding, then qualify discovery beyond the Tree and automatic funding. Full-town
coverage, maximum-rank proof and integration remain unfinished. Earlier uncertain
requests remain retained without replay; activation did not move gold or upgrade
guards.

Obsolete task-generated runtime programs should be removed when no longer needed,
without archiving rebuildable binaries, following the user's explicit preference.
Preserve game data and transaction records.

The next live qualification now uses [continuous workflow capture](guard-workflow-capture.md)
to collect the complete manual sequence before batching further native fixes.
