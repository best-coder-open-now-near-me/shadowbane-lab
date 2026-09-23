# Building and hireling navigation

Source branch: `codex/vendor-rolling`. Integration destination:
`codex/native-lifecycle-hardening`, followed by reviewed `main`. This work is
not merged. Start vendor work from this feature worktree, not the older main
checkout. The installed native 1.8.4 / host 0.3.13 remains unchanged.

## Completed reader slice

`client observe-native-vendor-roster --process-id PID --window building --json`
reads the active AssetManagement window before any individual Hireling window
exists. The existing default `--window vendor` remains available. Results identify
which window supplied the roster. Exact building/hireling keys remain separate
from labels, and no command authority or town completeness is inferred.

Building mode requires the rooted city asset manager, mode 6, initialized
AssetManagement state, exact HUD type/backlink and membership in the live HUD
stack, online mode, and matching selected/displayed building keys. It copies
real hireling rows and verifies occupied and total hireling-position counters
against the visible list, including vacant positions. Counts, identities,
controls and text are rechecked after copying. Missing, changing, partial or
entirely vacant lists remain unavailable; they cannot establish a complete
empty roster. Hireling positions are not production slots.

Validation: 35 focused reader/queue tests passed; full host suite 2,209 passed,
12 skipped; whole-tree Ruff passed. Coverage includes discovery before vendor
selection, vacancies, counter disagreement, wrong/closed windows, duplicate or
changed keys, changing occupancy and CLI handle cleanup. Positive live
qualification of this new building-menu source remains pending. The latest
read-only VM check found the building/Hireling menus closed, so their retained
manager fields were not used as a roster. No native command or package version
changed in this reader slice.

## Static source evidence and navigation boundaries

Addresses below are RVAs in the reviewed x86 executable; they are investigation
facts, not a callable public API or authorization to send arbitrary actions.

- Fixed ordinary action 0x57c reaches the building activation handler at
  RVA 0x7d14e0. It validates the selected object's building role and key,
  sets asset-manager mode 3 and installs its reference through the game's
  setter at RVA 0x6cf8c0. Other action branches handle placement or pets and
  must not substitute for this path.
- Live activation calls RVA 0x6d4c00, which sends a city-asset request for the
  selected building key. The ordinary healthy-building branch uses mode 2;
  the other health branch uses mode 0x16. These are not interchangeable.
- The city-asset response handler at RVA 0x3e7580 handles response mode 3 by
  creating AssetManagement through RVA 0x6cd150, setting manager mode 6,
  loading building data and its hireling rows. The menu belongs at manager
  +0x68, with initialized flag +0x48. Creation copies +0xf0 to +0xf8.
- Response +0x204 supplies total hireling positions at manager +0x380. The
  response vector +0x208/+0x20c populates rows through RVA 0x6d0340;
  remaining positions use that same path with a null source. Real rows
  increment manager +0x37c. This is a different count from crafting capacity.
- Row constructor RVA 0x5b5c00 uses vtable RVA 0x1169518, copies the hireling
  key to +0x10, display/service text to +0x30/+0x48, and marks populated
  rows at byte +0x6d. Initializer RVA 0x5b5f10 clears that byte for vacancies.
- The building menu's selection handler at RVA 0x6c6b10 handles 0x4ce and
  requires a hireling row kind 9 before requesting an individual hireling
  through RVA 0x6d69d0. No guessed row index or display name should select it.
- Selected-object helper RVA 0x498730 accepts a reference-owning argument,
  changes the selected-object reference and sends the normal target update.
  It consumes/releases its argument. Passing a bare borrowed pointer is
  incorrect; collection acquisition, reference ownership and scene validity
  must be established before native building selection is implemented.
- Asset-manager +0xd8 is the offline/demo selector, not a server-response
  pending flag. A zero value alone never establishes response freshness.
- City Command also owns guard/settings actions. Its cache supplies nearby
  building identities; its nested hirelings are not yet qualified as the
  crafting roster. Do not dispatch its guard/settings actions as navigation.

## Retained building target ownership

The vendor branch now includes the published native movement ownership changes
from 6998292, fc6b8fe and dfa766a as e7ca4a4, b637e47 and 4ad7d81.
Their 44 lifetime/collection checks passed locally. They do not activate the
optional door collection observer.

The building target adapter queries retained native world results near the
current world position, selects exactly one management key, and transfers that
owned reference to the normal target setter before fixed action 0x57c. Management
identity is at object +0x780, distinct from world identity +0x18. It rejects
duplicates, unreadable candidates, wrong thread, stale scene/admission and
unexpected position getters. Query bounds cover loaded structures within 1,024
world units; this is not full-city coverage or a claim that distant buildings
are accessible. Native query/release callbacks run outside extension read leases.
Uncertain native ownership is quarantined; selection is never replayed locally.

The adapter is connected to the typed navigation command runtime in source, but
not installed on the test VM.
Its native test covers distinct management/world keys, duplicate results,
reference consumption, query/release/selection invalidation, wrong thread,
unsupported position/parent state, dispatch rejection and native faults.
The extension and test compile with warnings as errors; the native test and
56 package-gate tests pass. Host manager coordination and live qualification remain part of this slice.

## Native navigation command checkpoint

Commands 13/14/15 inspect, open an exact building, or open an exact hireling.
They carry the producer lease, HWND, UUID and full expected scene/window state.
The owning UI thread revalidates admission at native callback boundaries.
Building opening uses the retained target adapter; hireling opening resolves the
exact populated row in the complete visible building roster and calls the normal
semantic left-button handler at RVA 0x61c6e0. Vacancies, duplicate IDs, changed
counts, wrong controls/backlinks and disabled controls cannot become targets.

Submission is distinct from an observed response. The controller blocks further
navigation while waiting, resolves only the exact requested window/key in the
same scene, and latches uncertainty on timeout, scene replacement or uncertain
native entry. Late responses cannot silently clear that latch. Request records
are bounded and never evicted/replayed. Navigation also blocks City Command and
crafting actions until resolved, and existing unresolved crafting blocks opening.

All native targets compiled. Eleven navigation/existing command regression cases
passed, plus the separate building-target ownership test and 74 package-gate host
tests. Tests cover native byte layouts, real producer-lease queue publication,
expiry before owner execution, receipt correlation, exact-key response resolution,
duplicate suppression and late-response uncertainty. No game action was sent;
the installed extension remains 1.8.4 with host 0.3.13. Host transport/session and manager operation journaling are now implemented below.
Exact package validation is complete; live qualification remains.

## Host navigation release candidate

Native 1.8.5 / host 0.3.14 is a source candidate, not installed yet. The dashboard
**Find buildings and vendors** operation first records the nearby City Command
cache, closes its producer transport, then visits each cached building and opens
its populated hirelings by exact key. Each opening has a saved UUID and expected
state before publication. An independently read building/vendor roster is checked
against unchanged native state and the exact process lifetime. A native refusal
before entry may be recorded as unavailable and skipped. Uncertain calls, changed
owners, conflicting responses and timeouts stop without replay.

Empty visible building menus and unavailable buildings remain explicitly
unverified; they never establish complete town coverage. Discovery uses a separate
navigation journal and leaves crafting jobs and items unchanged. The worker's
new navigation capability must match its current process identity. City and
navigation sessions cannot own producer leases simultaneously.

Validation: full host suite 2,252 passed, 13 skipped; whole-tree Ruff passed.
Focused integration checks include both commands crossing the actual host
transport, byte agreement with the native fixture, producer-lease loss,
two-building/vendor traversal, durable intent before publication, no replay after
interruption, cancellations, unavailable targets and independent roster mismatch.
The package builder also requires installed-wheel agreement with both native
profiles. Packaging and reversible activation are complete for source 89a4489.
The active runtime is native 1.8.5 / host 0.3.14, with exact loaded DLL and
worker binding verified and all eight old crafting records unchanged. See
[activation handoff](vendor-navigation-1.8.5.md). Login and live discovery are next.

## Active todos

1. Active: finish discovery through automatic exact-building selection and
   hireling acquisition, then qualify both known workshops. Preserve the
   existing operation lease, owner-thread scene checks and unresolved-job guard.
2. Add automatic recipe and inventory opening to that same native ownership
   boundary, with correlated receipts and no uncertain-operation replay.
3. Connect durable town/building/vendor selections and sequential scheduling,
   parallel cooking and completion revisits. Keep confirmed Tier 1–2 exclusion,
   unknown preservation and one current-capacity batch per selected vendor.
4. Qualify the complete multi-building run and record coverage/access limits.

No user menu setup or game restart is requested for the reader checkpoint.
Private runtime evidence and existing rollback files stay outside Git.
