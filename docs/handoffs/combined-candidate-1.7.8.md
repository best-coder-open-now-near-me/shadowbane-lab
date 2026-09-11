# Controller chat repair candidate 1.7.8

Exact clean source: `97612e63f4865e0e9ca192db8c340520e32b7781` on
`codex/native-lifecycle-hardening`; previous installed source
`5d211568072cd2bda6a0619b4a9873d6ba79eb08`. Includes native movement owner
`271665eaa88405c04726000d5e2d5c453c89cfc0`, cherry-picked as `97612e6`, and
product/wheel version checkpoint `394eea4`. Common batch base remains
`14d117e8c5194c6dff55dac608b2d3f683187d31`.

## Behavior and scope

Controller sticks continue native movement and camera during chat/text entry.
Keyboard typing and pointer text ownership remain protected; keyboard movement
requires neutral input after text closes. True modal, focus, unavailable input,
lifetime and nested interruption safeguards remain. Automation stops on text
entry and cannot reacquire until text closes; stale commands cannot affect the
manual controller owner. Parent-frame continuity uses fresh native cleanup/basis
and is tested while text is active. No synthetic controller-to-keyboard input.

Native focused-control fallback remains intact: live evidence did not justify
removing it. Diagnostic bit8 still means any text/global UI ownership; it does not
alone establish controller inhibition in this version. Settings and public wire/
diagnostic layouts are unchanged. ABI versions are not product versions.

Remappable action profiles, new targeting/hotbar/interact adapters, newer PvP work
and unfinished particles are excluded. Existing visible selection and conservative
transparency policy are preserved. This is the existing diagnostic package path,
not certification that deferred visual work is complete.

## Verified package

Private output: `E:/Projects/shadowbane/artifacts/combined-packages/f0c92a36`.

- ZIP SHA256: `ddf7091f420ca51607f2dfa5d35f077200cbcbdf316e7fd6f5f45a747c2e8826`
- Full DLL: `ca67bac3a83a4685747642ed222de3a360bf24519c1d56ae84a17885625373dd`
- Diagnostics DLL: `5df84733a28f0fc679bb5eb5c6ef1dc0240b93e573fb2294713fb746a1d6913f`
- Wheel0.2.8: `9becc247c9ccdfe85d38cb5645914f80b5964c63e9a49e7fe691439daa30fb71`

Existing exact-commit builder passed Python1854 tests,14 skips,238 subtests; Ruff;
both ALL_BUILD profiles;132 executed required native suite passes per profile with
three no-argument binding skips. Actual cue/sky/prepared-image bindings executed
separately and passed. Each profile45 interprocess/reader tests passed,zero skipped.
All three new runtime cases (controller-text,controller-modal-rearm,
parent-controller-text) executed and passed in each profile, as did native UI tests.
Known ideal-transparency failures remain separate deferred diagnostics.

Installed wheel entry point, inspector, Graphics Lab effects/selection/sky/movement
controls and trace-reader checks passed outside the source checkout. All58 receipt
file hashes/sizes and ZIP CRC passed. Source/profile lists and capabilities were
checked by the existing builder. Full logs and manifest remain beside the package;
root progress log is `artifacts/combined-1.7.8-build.log`.

Independent reviewer approved exact diff1095722..97612e6 with no findings.
Independent work was source inspection only; execution above is root evidence.
CI34580020338 passed all seven jobs; retained `artifacts/combined-1.7.8-ci.log`
confirms each new runtime case actually passed in both profiles.

## Installation and single focused live check

Current VM remains on1.7.7. Exact1.7.8 bootstrap and installation/launch scripts
are prepared privately under diagnostics/combined-acceptance-1.7.8-f0c92a36;
PowerShell syntax checked. They preserve current1.7.7 Config, install the verified
wheel, prepare from the pristine reviewed baseline, and verify hashes before launch.
No guest install/launch has occurred. Close current diagnostic game and panel before
installation. Retire stopped superseded client under standing owner authorization;
retain settings, baseline and receipts. No main merge or unrelated client changes.

After installed identity and enabled trace verification: left-stick movement and
right-stick camera with chat open; type ordinary text without WASD movement; release
sticks to stop; close chat and verify normal controls. Controller input must not
insert text. Retain modal/focus stop and neutral recovery check. No broad navigation
retest. Physical disconnect/reconnect recovery remains a separate unconfirmed item.

Next: controlled client close/install, targeted live chat acceptance, then complete
remappable actions with verified native adapters on the existing movement branch.

## Verified VM installation

After owner confirmed game/panel closed, installed verified1.7.8 and wheel0.2.8 at
`S:/ShadowbaneLab-Guided/combined-acceptance-1.7.8-f0c92a36`, preserving1.7.7 Config.
Launched PID5948, creation FILETIME134335900068691076, HWND394300. Loaded DLL SHA256
matches the full artifact above; prepared EXE remains
`bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87`.
Schema3 trace channel verified enabled before login; zero records at that point.
Movement status not yet consistently published before in-world initialization;
verify after login. No collector currently running.

Removed only stopped superseded1.7.7 client tree after exact resolved-path,
reparse-point, process-use and replacement/receipt checks under standing owner
cleanup authorization. Preserved current settings, pristine baseline and private
receipts. No other client or main branch changed. Next: owner login, then bounded
controller/chat trace and focused acceptance described above.

## Passed connected controller/chat acceptance

Owner confirms: "chat recovery and input while chat focused is good" on installed
1.7.8. Completed bounded private capture controller-chat-acceptance-20260911.jsonl
covers tick15190812..15370843,1,609 current samples. It includes55 samples with
UI ownership bit, connected controller and moving policy together, plus1,352
UI/controller manual-idle samples,zero fault states. The only ownership event in
that interval is ordinary manual takeover; no unexpected owner loss. Historical
ring entries before the capture interval were excluded from that assessment.

The focused chat/input behavior is accepted. Both user observation and trace are
retained; the trace alone does not inspect typed text or certify every controller
function. Collector finished; none running. Next active delivery is the separate
remappable supported-action checkpoint, followed by verified targeting/hotbar
adapters. Physical controller disconnect/reconnect remains unconfirmed; do not
repeat accepted keyboard/navigation/chat runs without a relevant new change.

## Door interaction is the next main gameplay mission

Owner prioritizes approach -> identify/select door -> invoke native interaction ->
open -> walk through, before broader combat controls. Owner reports ordinary mouse
selection and an interact-selected hotkey but no apparent door-targeting shortcut.
This is a live question, not proof that no native targeting path exists.

Existing character-specific selected-target readers cannot establish a door layout.
Root prepared a bounded, receipt-lifetime/hash-guarded read-only selection-root
observation for installed1.7.8; do not invoke client code or write its selection.
The probe observes only selected pointer/vtable changes, not interaction call flow.
Owner positioning near a closed unselected door is pending; no door capture started.
Native movement owner is investigating actual object picking/selection and native
interact dispatch, distinct from the terrain-only movement pick. Preserve range,
locks, permissions and obstructed-target behavior. Semantic remappable Interact
is the intended delivery, not a guessed key macro or unwired action choice.

Remapping source b727b0f is integrated and its preliminary package built at private
combined-packages/4153e9bd, but review P2 mandatory profile-IPC test presence remains
open. Do not install/certify that preliminary package. Existing owner must fix the
mandatory gate and add targeted failed/nested cancel coverage before exact rebuild.
Running1.7.8 remains the accepted movement/chat baseline. Main is unchanged.
