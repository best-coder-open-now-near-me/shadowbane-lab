# Power Palettes source-selection record

Status: documentation source selected; production branching, native calibration and implementation have not started.

## Source and ownership

| Field | Verified result |
|---|---|
| Selected source commit | 310620bc884464b26aa44d9da366af03f9c428d0 |
| Selected source ref | origin/codex/native-lifecycle-hardening, refreshed by successful git fetch origin in this session |
| Documentation checkout | Initially detached at that source; record completed on codex/power-palettes-plan |
| Designated rolling integration owner | codex/native-lifecycle-hardening, documented by the selected source's README.md, CONTRIBUTING.md, docs/git-branch-map.md and native-lifecycle handoff |
| Merge-base with active integration line | 310620bc884464b26aa44d9da366af03f9c428d0 |
| Shared merge destination | main at 047147dfe468670458486a806d03b03284824dd1 |
| Merge-base with main | 047147dfe468670458486a806d03b03284824dd1 |
| Documentation review destination | codex/native-lifecycle-hardening, with later inclusion in main through its owner's review |
| Production branch | Not created; this record must be refreshed before any production branch |
| Normal shared checkout | E:/Projects/shadowbane remains on main |

This record selects source for planning. It is not an installed-package receipt, a current CI certification, or proof that native palette construction is available.

## Related branches reviewed

The fetched remote containment check found only origin/codex/native-lifecycle-hardening containing the complete selected commit. No descendant palette branch was found.

The related movement branch was inspected at 92122148860f7645134573182c78d5678d48e742. Its merge-base with the selected line is dbfe259dd0e96004ba9c953699983cf6a2cd7e53. Neither branch tip is substituted for the other. The selected line retains its later cold-idle package-gate commit.

The movement-side ordinary log includes historical commits 69661e4 and 622a688 and merge commits; its cold-idle test change is patch-equivalent under git log --cherry-pick. A focused tip comparison of movement_native_image.cpp, movement_runtime.cpp and movement_runtime_test.cpp returned no differences. This does not certify all branch-local files or authorize deleting the movement branch.

git branch -vv and git worktree list were inspected. Existing lifecycle, movement, navigation, selected-cue, sky, particles, renderer, PvE, identity, streaming and preservation checkouts remain with their current owners. No existing worktree is switched, merged, cleaned or retired by this task.

## Existing boundaries

Paths refer to the selected commit.

| Facility | Source evidence inspected or located | Remaining limitation |
|---|---|---|
| POWERNAME identity | src/shadowbane_lab/client_input/arcane_hotbar.py: ArcaneHotbarSlot requires POWERNAME for PowerHotButtonInfo and exposes power_name; implementation inspected | The module also exposes F-key activation, which palettes must not reuse. Parsing does not prove native factory ownership. |
| Native HUD coordinates/focus/hit testing | native/wonderbane_extension/movement_native_ui.h and .cpp: NativeClientPoint, NativeUi, NativeUiState; header inspected | Palette parentage, drop details and extraction safety still require review/calibration. |
| Scene lifetime | native/wonderbane_extension/movement_lifetime.h: NativeScene and Start/Observe/Current/Retire APIs; header inspected | Observer is explicitly process-pinned with terminal retirement; preserve original call-through rather than adding competing hooks. |
| Learned powers/ranks | src/shadowbane_lab/client_observation/native_training.py: NativePlayerTrainingProfile and NativeTrainingEntry definitions inspected | Completeness and activation freshness remain calibration gates. |
| Active character/config | src/shadowbane_lab/client_observation/native_character_config.py, docs/active-character-profile.md and tests/test_active_character_config.py located | Stable server-issued character ID availability is not established. |
| Dispatch boundary | native/wonderbane_extension/client_action_dispatch.h declares reviewed_client_dispatcher_unavailable; event_channel_test.cpp references rejection | No calibrated power executor is established. |
| Atomic storage | src/shadowbane_lab/record_store.py and tests/test_manager_record_store.py located; native-lifecycle handoff describes interprocess load/merge/replace | Evaluate reuse; navigation merge semantics do not replace palette writer/epoch policy. |
| Package pipeline | native/wonderbane_extension/CMakeLists.txt, scripts/build_navigation_inspector_package.py and tests/test_package_native_gate.py located | Preserve existing pipeline and exact membership; no parallel release path. |

The unified exact client profile, independent control factory, source-free update/tooltip lifecycle and native invocation remain unproved.

## Validation contracts to preserve

The selected CONTRIBUTING.md and .github/workflows/ci.yml require Ruff, Python tests on 3.11/3.12/3.13, full and diagnostics-only Win32 builds, required CTests excluding stretch-diagnostic, separate diagnostic evidence, and PowerShell syntax validation. The package builder also requires actual runtime/binding execution, source-profile membership and installed-status checks.

Focused future regressions include movement_native_ui_test, movement_lifetime_test, movement_runtime_test, movement_windows_input_test, movement_image_test, movement_settings_runtime_test, tests/test_arcane_hotbar.py, tests/test_native_training.py, tests/test_active_character_config.py and tests/test_package_native_gate.py.

This documentation task validates document structure, sample data, links and diff hygiene. It does not rerun unrelated builds or claim historical CI certifies a future palette candidate.

## Protection and refresh rule

The root was clean on main at inspection. Other-task dirty files have not been enumerated or touched; every existing worktree is treated as potentially active. Branch-local source, uncommitted drafts and private evidence remain with their owners.

Before production work, fetch again, refresh source tips/ancestry and relevant deltas, record new shared-ownership changes, update this record and the handoff, and only then create or select the production branch. No production branch may be created using a stale record by branch name alone.
