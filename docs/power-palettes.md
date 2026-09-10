# Power Palettes: expanded implementation plan

Status: repository-adopted planning contract, revised against the second review. Native calibration and production implementation have not started.

This document expands and replaces the supplied implementation plan. It incorporates the review decisions into one contract rather than leaving an addendum for implementers to reconcile. Only the source-selection record's explicitly inspected facilities are verified by this documentation pass. Native factories, ABI contracts and release acceptance remain unproved.

The supplied plan identified codex/native-lifecycle-hardening at 310620bc as a historical integration reference. A fresh fetch in this revision session confirms its full tip as 310620bc884464b26aa44d9da366af03f9c428d0. The [source-selection record](investigations/power-palettes-source-selection.md) documents source, ancestry, facilities and verification limits; the [handoff](handoffs/native-power-palettes.md) records delivery and remaining work. Refresh that record before production branching rather than assuming this pin remains current.

Reading guide: sections 1–4 define product behavior; 5–12 define evidence and ownership contracts; 13–15 define execution and validation; 16–20 define source organization, delivery, remaining discovery, and todo status.

## 1. Objective, scope, and completion boundary

Power Palettes let a player copy powers from Shadowbane's ordinary Powers window into freely positioned, persistent native palette windows. Clicking a shortcut uses the same native behavior as a stock power button without consuming a stock hotbar slot or registering an F-key.

The stock Powers window remains the catalog. Its source controls and entries are never detached, reparented, or altered to create a shortcut.

The first feasibility milestone is:

> Construct a second genuine native power shortcut outside the stock hotbar, with independent ownership and no key registration, and prove stock-equivalent activation, presentation, updates, and teardown.

### Feasibility decision and failure gate

Production implementation is blocked until the exact target build demonstrates an independently owned, keyless native power shortcut outside the stock hotbar. The proof must include stock-equivalent activation, presentation, update registration, tooltip behavior and teardown.

If this proof cannot be achieved without stock hotbar registration or slot reservation, unsafe object cloning, retained source pointers, hidden stock controls, synthetic input, packet bypass, Win32 UI or overlay presentation, stop the feature line and produce a bounded calibration report. Record the exact build, attempted reviewed boundaries, evidence, missing ownership or invocation contract, and conditions needed to resume. Do not continue into production layout, persistence, substitute presentation or dependent refactoring.

A failed feasibility gate is an investigation result, not permission to weaken the architectural invariants. Planning documents may record the outcome; production work remains blocked until new evidence satisfies the gate.

Production delivery includes multiple palettes, editing, resolution-safe layout, per-character persistence, missing-power placeholders, lifecycle handling, status, disable/reset controls, packaging, and connected-client evidence. A one-slot proof is an internal validation gate, not an MVP to hand to the user as the completed feature.

### Included

- Powers-to-palette copying and Shift-drop palette creation.
- Native power icons, tooltips, cooldown, disabled, resource, stance/toggle, and active-state behavior.
- Palette move, resize, lock/unlock, remove, reorder, and cross-palette move/copy.
- Stable identity resolution and automatic reactivation after retraining.
- Exact-build support, shared native UI/scene ownership, and safe unsupported-build behavior.
- Character/server-bound storage, recovery, concurrent-client policy, diagnostics, and release handoff.

### Explicitly deferred or excluded

- Palette names and user-customizable visual themes.
- New keyboard shortcuts or F-key assignments.
- Host-driven learned-power execution. A future dispatcher may reuse the reviewed executor, but is not part of this release.
- Stock-hotbar-to-palette and palette-to-stock-hotbar transfer gestures.
- Arbitrary macro sequences, synthetic input, packet construction, and overlay implementations.
- Automatic guessing of renamed characters, build mappings, power identities, or configuration paths.

The two excluded transfer gestures do not change existing Powers-to-stock-hotbar or stock-hotbar-to-stock-hotbar behavior.

## 2. Architectural invariants

These are release requirements:

1. No PyAutoGUI, SendInput, PostMessage, virtual keypresses, or hotbar-key simulation.
2. No OpenGL overlay or separate Win32 child window standing in for native UI.
3. No direct packet construction or bypass of the ordinary client action lifecycle.
4. No mutation of the stock Powers list or stock configuration for palette storage.
5. No persistent native pointer, vtable, source-control address, hotbar index, or display-name-only identity.
6. No raw byte cloning of native controls or PowerHotButtonInfo objects.
7. Every native binding belongs to one unified, exact target-build profile.
8. All native UI creation, mutation, invocation, and destruction occur on the verified owning UI thread.
9. Native callbacks and controls cannot outlive the code or generation they reference.
10. Unsupported builds have no palette interaction hooks installed and leave stock behavior unchanged.
11. A partially constructed palette is never exposed as a working feature.
12. No fallback implementation silently weakens these requirements.
13. No completion claim without connected evidence of native behavior and lifecycle correctness.

For this document, a native palette control is an in-process object participating in Shadowbane's own UI hierarchy, logical coordinate space, visibility, invalidation, z-order, focus, hit testing, drag/drop ownership and lifecycle. It may reuse verified stock classes or an extension-owned class implementing the verified game UI ABI. A Win32 child or owned window, OpenGL-composited panel, screen-coordinate click surface or hidden stock control does not qualify.

Native pointers are permitted in bounded, generation-bound runtime records and controlled calibration evidence. They are never used as persistent shortcut identities or retained from a completed drag.

## 3. Exact interaction contract

### 3.1 Creation and initial state

Open the ordinary Powers window and begin its normal power drag. Holding Shift at release over valid empty HUD creates a one-slot palette anchored at the drop point, then clamped into the usable HUD area.

A new palette starts unlocked. Its sole power remains present in the original Powers window. Dropping without Shift on empty HUD follows the ordinary canceled stock drop.

The creation transaction succeeds only when the power identity, character binding, HUD generation, native construction, and layout limits all validate. Otherwise no palette is created and the stock source remains unchanged.

### 3.2 Clicking and native presentation

- A normal completed click invokes exactly once at the stock power control's verified native activation phase. "Completed click" does not prescribe a new mouse-down or mouse-up policy.
- Targeted powers enter normal targeting; instant powers execute normally.
- Cooldown, resource checks, disabled behavior, active state, stance/toggle state, and learned-rank presentation come from reviewed native behavior.
- Hover uses the native tooltip lifecycle.
- No F-key or stock hotbar registration is created.
- A drag completion, cancellation, or control destruction does not emit a click.
- Palette input participates in native focus, hit testing, modal ownership, and z-order. Handled input must not reach world movement or camera handling.

Immediately before that verified native activation phase, revalidate the exact process lifetime, character binding, scene/HUD generation, layout epoch/revision, shortcut-instance identity, control generation/lifetime, native definition, learned observation and input/modal ownership against the interaction-start token. A changed or unavailable binding cancels without invocation, even if pointer-down was valid. Returning to the same pointer address is not continuity; generation/sequence checks still apply.

Each native pointer sequence has an activation guard admitted at most once before any reentrant invoke callback. Duplicate down/up handling, reentrant callbacks and replay cannot consume that sequence again. Drag completion/cancellation, removal, destruction, focus loss, modal takeover and stale-generation rejection cannot emit an activation. Keep the guard until the native sequence and any fetched callbacks retire.

The stock control may implement these checks internally. Calibration must prove the actual pre-invoke validation/guard boundary and its ordering; if it cannot, activation feasibility is unproved. Any extension guard must use the same reviewed invoke path rather than create an independent executor.

### 3.3 Locked and unlocked behavior

Unlocked palettes provide a title/move strip, resize action, lock and close controls, cell drop targets and an independent removal action on occupied cells.

Resize must be integrated into the palette's game-UI object. It may reuse a verified stock resize control or implement the verified native control ABI; no hypothetical stock grip API is assumed. Removal may use a dedicated non-overlapping native control or a verified native context command. Its hit target/command cannot invoke the power. Lock, close and unlock affordances likewise use verified stock classes or the verified native control ABI, never a Win32 or OpenGL surface. Calibration records the selected mechanisms before production construction.

Locked palettes allow power clicks and tooltips but disable movement, resizing, incoming drops, outgoing edit drags, reordering, shortcut removal, and palette deletion. Chrome and empty-cell visuals are suppressed. Cell positions remain unchanged; locking does not compact the grid. While visible, the complete native rectangular bounds remain UI-owned in both locked and unlocked states, including empty cells, gaps, borders and hidden chrome. Suppressing empty-cell visuals never creates click-through holes. Pointer input over any empty part is consumed as UI input and cannot become a world click, selection, movement command or camera gesture. Version 1 has no pass-through regions.

A native unlock affordance remains reachable and does not overlap icons; its size and verified implementation must preserve that behavior. Locking is per palette, so locked and unlocked palettes may coexist.

A locked palette remains a native hit and drop-routing target but rejects edits. A drop over its bounds cancels without modifying source or destination. It is never empty HUD and cannot fall through to Shift-create, a target behind it or world input.

Opening chat or another native input owner does not grant palettes priority over that owner. Modal UI blocks palette interaction according to the same rules as stock controls.

### 3.4 Drop matrix

Shift is sampled from verified native modifier state at drop finalization. The active native drag interaction must communicate copy/move intent unambiguously. Prefer the stock cursor or ghost only where a verified mutation seam exists; otherwise use a native receiving-target indication, including a native HUD-owned indication for eligible empty-HUD creation. No custom OpenGL cursor or screen-coordinate overlay is authorized. Focus or modifier uncertainty cancels the extension edit.

| Source | Destination | Modifier | Result |
|---|---|---|---|
| Stock Powers | Stock hotbar | Either | Original stock behavior, unchanged. |
| Stock hotbar | Stock hotbar or other stock target | Either | Original stock behavior, unchanged. |
| Stock Powers | Empty unlocked palette cell | Either | Copy into that cell. |
| Stock Powers | Occupied unlocked palette cell | Either | Insert a copy at that position. |
| Stock Powers | Valid empty HUD | Shift | Create unlocked one-slot palette with a copy. |
| Stock Powers | Empty HUD | No Shift | Original canceled drop. |
| Unlocked palette | Another cell in the same palette | No Shift | Move/reorder transaction. |
| Unlocked palette | Another unlocked palette | No Shift | Move transaction. |
| Unlocked palette | Another cell or unlocked palette | Shift | Copy transaction. |
| Unlocked palette | Valid empty HUD | Shift | Create a new palette containing a copy; retain source. |
| Unlocked palette | Empty HUD | No Shift | Cancel; retain source. |
| Any power source | Locked palette | Either | Reject without an edit; never treat it as empty HUD. |
| Stock hotbar | Extension palette | Either | Unsupported; reject extension drop and preserve stock source. |
| Extension palette | Stock hotbar or other stock target | Either | Unsupported; cancel extension drag before stock target mutation. |
| Any unsupported payload | Extension palette | Either | Reject extension drop. |
| Any source | Modal-covered, blocked, or invalid area | Either | No extension edit. |
| Any power source | Palette title strip, resize chrome, remove/lock/unlock/close control, border, or unused frame area | Either | Reject without editing or running that control's action; the point is not empty HUD. |
| Any power source | Previous/next page affordance | Either | Verified hover may change the destination page; release on the affordance rejects the drop. |
| Any power source | Palette observed as closing or retired during this drag | Either | Cancel the stale operation; do not reinterpret disappearance as Shift-create. |
| Any power source | Source/destination layout epoch or revision changed since drag start | Either | Cancel unchanged; never retarget to the new cell occupant. |

For stock-origin drags over stock targets, always preserve original dispatch and ownership. For extension-origin drags, do not expose an unsupported transfer to a stock commit handler. This distinction must be enforced before drop finalization; a stock mutation followed by attempted rollback is unacceptable.

Dropping a palette shortcut onto its own cell is a no-op, with or without Shift. Duplicates are otherwise allowed and have distinct shortcut-instance IDs.

### Normative interaction binding and drop-routing precedence

Every palette interaction is bound to the exact process lifetime, character identity, scene/HUD generation, control generation, layout epoch/revision and native drag or pointer sequence under which it began. Immediately before drop commit or native activation, revalidate that token. A mismatch cancels without a model edit, stock mutation or automatic rebasing onto changed controls.

The source/interaction token is fixed at drag start. A destination observation is acquired when routing enters a target; intentional pointer movement or verified page navigation may select a different destination, but finalization revalidates that observed target against the original layout revision and source token. This permits ordinary target selection without rebasing an operation after a stale-layout or lifetime change.

Resolve the frontmost owning native target using native z-order/modal/hit-test rules. Routing priority must not tunnel through an owning palette to a stock target behind it, or through other native UI to a palette beneath it.

1. Validate process/character/HUD/scene and drag generations, payload type/provenance, source lifetime, focus, capture and modifier certainty before extension interpretation.
2. If the owning target is an ordinary stock target and the source is stock-owned, preserve verified original stock behavior unchanged.
3. If the owner is an eligible unlocked palette cell, resolve the matrix's copy/move/insert transaction.
4. If the owner is a locked, closing, stale, read-only, unsupported or otherwise rejecting palette region, consume/reject safely with no fall-through.
5. Only if no native UI target owns the point, evaluate Shift plus valid empty HUD plus an eligible Powers/palette source for creation.
6. Otherwise preserve stock-owned canceled-drop behavior, or cancel an extension-owned drag through its verified native manager contract.

Shift-create is the last extension interpretation, never the first.

The initial extension admission check does not authorize intercepting ordinary stock interactions when palette bindings are unavailable: pre-installation rejection leaves stock hooks untouched; validated terminal pass-through preserves original stock dispatch. Extension-origin transfers into stock targets remain unsupported and are canceled before stock mutation. These source distinctions reconcile stock-target priority with deferred hotbar transfers.

The native drag manager owns cancellation and source restoration. Rejection finalizes/cancels once; it must neither swallow a stock source's cleanup nor replay input into a newly exposed target.

### 3.5 Occupied cells, gaps, and capacity

Cells have a fixed row-major address within a persisted grid. Empty cells are meaningful and round-trip through storage.

- Drop into an empty destination: fill that cell.
- Copy or cross-palette move into an occupied destination: insert at that cell, shifting entries forward up to the first available empty cell. Entries outside that affected interval remain unchanged.
- Same-palette move onto an occupied cell: rotate the inclusive source-to-destination interval so the moved instance occupies the destination and intermediate entries retain relative order. Capacity is unchanged.
- Same-palette move into an empty cell: move into the hole and leave the source empty.
- If insertion needs more capacity, add the smallest number of complete rows within the configured limits. Reject unchanged if growth is not permitted.
- After a cross-palette move or removal, preserve remaining gaps. Remove a now-empty source palette only after the whole edit commits.

No occupied shortcut is silently replaced or discarded. Power duplicates count toward limits like any other shortcut.

### 3.6 Removal, close, and cancellation

While unlocked, invoking a slot's independent native removal action removes only that shortcut. Clicking the palette close control deletes that palette and its shortcuts from the logical layout.

The release contract requires an independent native removal action. A verified dedicated control or context command may provide it; calibration records one mechanism consistently for the release. Deletion is always explicit, never an interpretation of dropping outside a target.

Closing during a drag cancels that drag first. Removing the final shortcut deletes its empty palette after transaction completion. Closing a palette or invoking a removal context command must not dispatch any power underneath its control/menu.

Cancel extension edits on focus loss, capture loss, modifier uncertainty, native drag invalidation, source retirement, destination closure, modal appearance, HUD/window/scene generation change, character change, feature disable, or binding failure. A canceled edit creates no layout revision and queues no save.

## 4. Layout and resolution contract

Persist normalized position plus explicit rows and columns. Do not also persist an independent normalized width/height as a competing authority for grid capacity.

The anchor is relative to the HUD origin:

~~~
x = (palette_left - HUD.left) / HUD.width
y = (palette_top  - HUD.top)  / HUD.height
~~~

Cell dimensions, chrome, and spacing use the target build's native logical UI metrics. Resizing snaps to cells. Moving changes only the normalized anchor.

Shrinking is allowed only if the proposed grid can represent all existing occupied cells after the documented row-major reflow. Preserve the entire ordered cell sequence through the last occupied cell, including intentional gaps; trailing empty cells may be discarded. Reject shrinking below that required capacity. Changing columns reflows that sequence row-major and does not change shortcut order.

Initial release limits, centralized and tested:

- 16 palettes per character.
- 64 occupied shortcuts per palette and 256 per character.
- 1–12 rows and 1–12 columns per palette.
- 1,024 total allocated cells per character.
- 1 MiB maximum layout document.
- 128 UTF-8 bytes for power ID and 256 UTF-8 bytes for display-name hint.

These are engineering bounds, not claims about native capacity. Calibration and stress evidence may justify a documented revision to these limits before release; any change must update the schema, model, UI behavior, and tests together.

### Restoration and temporary constrained layouts

Restore the saved grid and anchor against current logical bounds. Clamp the frame so title/unlock controls remain reachable. Never rewrite the saved grid merely because the game temporarily changes resolution.

When the full grid cannot fit, use a native paged viewport within the palette frame: render contiguous row-major cell ranges, with native previous/next controls outside the icons. Every occupied cell remains reachable. The saved grid and shortcut addresses remain unchanged; page selection is transient.

Editing remains available within the displayed page. On an unlocked writable palette, during an eligible native drag, hovering a previous/next page affordance for 500 ms changes the destination page without committing an edit; leaving the affordance resets that dwell. The native drag manager retains the payload, and any hidden source control remains in a verified deferred-retirement record until finalization. Revalidate the transaction after page changes. This must use the native UI update/drag lifecycle, not an independent Windows input state machine. If this ownership cannot be proven, constrained-layout editing is an unresolved release gate. Resizing can replace paging when a user explicitly chooses a grid that fits. All edits target persisted cell addresses.

If the HUD cannot fit even one native power cell plus required controls, suspend that palette's view and report waiting_for_space. Preserve its model. This is temporary display suspension, not deletion or feature support failure.

The native paging controls and their input ownership belong to calibration and acceptance. No overlay scrolling or invisible inaccessible shortcuts are permitted.

## 5. Repository verification and unified target-build profile

The supplied plan reports these facilities:

| Reported facility | Required repository verification |
|---|---|
| Lossless PowerHotButtonInfo persistence using POWERNAME | Locate parser, fixtures, validation rules, and actual identity guarantees. |
| Learned-power vectors with tokens and ranks | Locate reader, completeness/freshness rules, bounds, and supported build evidence. |
| HUD, native hit testing, focus, drag pointer, and input gates | Locate implementations, ownership, exact profile, and regression tests. |
| UI-thread calls and scene retirement handling | Verify ordering, generation semantics, callbacks, and teardown coverage. |
| Exact process, server, character, and config binding | Verify source of identity, process-lifetime binding, and rejection of ambiguous profiles. |
| Generic action transport without reviewed learned-power dispatch | Confirm actual capability advertisement and unavailable behavior. |
| Different reviewed offsets across executable hashes | Inventory every required binding and prevent mixed-profile use. |

Before calibration, publish a source-selection record containing:

- Selected full source commit and branch or detached source pin.
- Designated integration owner and merge-base with the active integration line.
- Relevant descendant and related branches reviewed, including material excluded deltas.
- Existing native UI/lifetime facilities to reuse, with symbols and file paths.
- Known branch-local work that must not be overwritten.
- Build profiles and tests that must remain green.

No production branch is created until this record exists and matches refreshed remote evidence. Documentation may be prepared on a detached pin or isolated documentation branch; that does not start production implementation. Record verification limits, not just plausible filenames. The current [source-selection record](investigations/power-palettes-source-selection.md) distinguishes inspected declarations from unproved native contracts.

One immutable target-build profile must cover:

- Normalized executable identity and supported architecture.
- Expected image ranges, code bytes, vtables, and owned-patch normalization.
- Active HUD, window, native logical bounds, native tree and hit-test operations.
- UI-thread identity and callback/lifetime ordering.
- Native drag manager, payload types, source kinds, cancellation, and finalization.
- Power control and PowerHotButtonInfo factories, binding, updates, tooltips, and destruction.
- Native power invocation and targeting boundaries.
- Frame/chrome, paging controls, child registration, focus, and z-order.
- Native power registry, token verification, learned-power observations, and rank updates.
- Exact actor, character, server, scene, and process-lifetime binding.

Validate the complete required profile before installing feature interaction hooks or constructing controls. No best-effort scanning, cross-build offsets, guessed function addresses, or partial advertised support.

## 6. Durable ownership and module boundaries

| Component | Owns | Must not own |
|---|---|---|
| AbilityPaletteModel | Identities, instance IDs, grids, anchors, lock state, pure transactions | Native pointers, file handles, input hooks |
| AbilityPaletteClient | Reviewed ABI wrappers, factories, registration, invocation, cleanup primitives | Persistent character layout policy |
| AbilityPaletteResolver | Current stable-ID resolution and generation-bound native definition handles | Long-lived drag payloads or guessed substitutions |
| AbilityPaletteRuntime | Native views, edit orchestration, UI-thread lifecycle, callbacks, status | Background file I/O |
| AbilityPaletteDrag | Native drag observation, provenance, drop classification, transaction tokens | Independent Windows mouse-drag state machine |
| AbilityPaletteStore | Schema, character-bound paths, writer lease, immutable snapshots, recovery | Native UI or gameplay pointers |
| Shared native UI context | One HUD/input/modal/focus view | Movement-specific or palette-specific duplicate offsets |
| Shared scene lifetime | Retirement ordering and generations | Independent competing lifetime hooks |

The runtime is in-process and works while the control center is closed. A background worker may live in the extension but receives only immutable pointer-free snapshots.

The manager consumes versioned status and sends supported disable/reset/export requests to the exact bound runtime. It is not a second live writer of the layout file.

No second overlapping lifetime hook, competing SetWindowSubclass, independent active-HUD definition, or duplicate offset table is introduced.

## 7. Native construction and invocation

### Factory preference

1. Reuse the stock power-button and PowerHotButtonInfo factories with a private backing model.
2. Reuse a full native hotbar container only if its model, key registration, and stock persistence can be completely separated through reviewed contracts.
3. Otherwise, use a native frame with genuine stock power controls.
4. If native frame construction requires an extension-owned class, it must implement the verified native UI ABI and delegate power presentation and execution to reviewed native facilities.

Every retained route must meet the same acceptance bar. Failure to prove any route is a feasibility blocker, not permission to substitute an overlay or hidden hotbar.

For each object, document allocation owner, constructor receiver, calling convention, argument layout, partial-construction cleanup, reference ownership, parent ownership, subscriptions, destruction order, and final deallocation.

Registration for tooltips, cooldown updates, observers, and active state must be independent of key-slot registration, or the reviewed control lifecycle must safely provide that independence. The source Powers window may close without affecting a successfully created palette.

### Activation

~~~
native palette input
    -> current binding and scene/character eligibility
    -> genuine native power shortcut control
    -> reviewed stock invoke path
    -> normal targeting / action queue / client-server lifecycle
~~~

The click does not round-trip through Python or host IPC. No separate host executor is implemented in this release.

The developer proof compares receiver/argument contracts and native action/targeting evidence with stock behavior. Similar animation or successful input dispatch alone is insufficient.

## 8. Identity, resolution, and the pure model

### Canonical identities

Identity priority is: verified persistent logical power identifier (POWERNAME for the reviewed representation), corroborated by the exact-build native definition/token, with display name only as a diagnostic/presentation hint. The token is not a substitute identity. A mismatch leaves the shortcut disabled and unresolved pending explicit reviewed verification/migration, never automatic substitution.

A runtime resolved handle is bound to process lifetime, scene/HUD generation, character generation, and learned-power observation generation. A persisted record contains none of those native handles.

Resolution proceeds as follows:

1. Obtain an exact stable character binding and a complete current learned-power observation.
2. Resolve POWERNAME through the supported native registry.
3. Verify the native definition and token against the current profile.
4. Compare saved token evidence where its profile makes that comparison meaningful.
5. Confirm current learned eligibility using calibrated native semantics.
6. Bind or refresh the native control on the owning UI thread.

An unavailable/incomplete observation is not proof that a power is unlearned. Do not infer learned eligibility from an unverified trained-rank-greater-than-zero rule; stances, granted powers, and other power types must follow observed native semantics.

### Resolution states

| State | Meaning and presentation |
|---|---|
| unresolved | Initial resolution has not completed; activation disabled. |
| temporarily_unavailable | Current observation or native registry is unavailable; retain identity and explain temporary unavailability. |
| learned_and_valid | Current complete observation and native definition agree; native activation eligible. |
| not_learned | Complete valid observation establishes absence/ineligibility; show disabled placeholder. |
| token_mismatch | Current identity verification conflicts with applicable saved/profile evidence; activation disabled. |
| unsupported_type | Identity exists but its native shortcut type is not supported by the reviewed path. |
| native_definition_unavailable | Stable identity cannot be resolved in the current validated registry. |

Only learned_and_valid may activate, subject to ordinary native action checks.

Placeholder views use the same reviewed native frame/tooltip lifecycle but cannot carry an invokable stale power pointer. They display the saved name hint when available and the canonical ID otherwise, plus a specific reason, for example:

~~~
Shadow Touch
Not currently learned by this character.
~~~

Refresh bindings when learned-power observations, rank, definition generation, character, or scene change. All duplicate instances resolve against the same current identity result. Unlearning revokes old eligibility before further activation; retraining recreates or refreshes the native binding automatically.

If the implementation cannot establish a sufficiently fresh observation at activation, it rejects the activation until refreshed. Calibration must determine whether the stock invoke itself safely performs the required current validation.

### Token/profile migration

- A same-profile unexpected token mismatch fails closed for that shortcut.
- A different supported profile requires an explicit reviewed migration mapping or verified identity rule before updating saved token evidence.
- Migration never selects another identity based on vector position or display name.
- An unresolved migration preserves the original record as a disabled placeholder.
- A successful persisted migration creates a normal layout revision under the writer lease and is saved using the same conflict rules as an edit. Read-only runtimes may apply a reviewed identity mapping to transient resolution, but cannot rewrite saved evidence; they consume the committed migration when available.

### Core model

~~~
PowerIdentity
    power_id_string
    observed_token (optional when no verified evidence exists)
    token_profile_id (required when observed_token is present)
    display_name_hint

ShortcutInstance
    shortcut_id: UUID
    power: PowerIdentity

PaletteDefinition
    palette_id: UUID
    anchor: normalized x/y
    rows, columns
    locked
    cells: row-major array of optional ShortcutInstance

CharacterPaletteLayout
    schema_version
    character_key
    layout_epoch: UUID
    revision: monotonically increasing within epoch
    palettes
~~~

Cells have exactly rows multiplied by columns entries. Each occupied shortcut ID is unique throughout the character layout. Moving preserves its ID; copying generates a new ID. Palette IDs are unique. Removing and recreating a palette produces a new ID.

An edit token includes exact process lifetime, expected epoch/revision, scene/character/HUD/control generations, native drag sequence, source palette/shortcut ID, and destination palette/cell address. A click token also records native pointer sequence, definition/learned-observation generation and input/modal ownership. Native pointers are kept outside this pure token and revalidated on the UI thread.

Required pure operations: create, fill, insert, reorder, cross-palette move, copy, remove, close, empty-palette cleanup, resize/reflow, move anchor, clamp presentation, lock/unlock, resolve destination, enforce limits, reject stale tokens, serialize, validate, and migrate.

No-op edits do not increment revision. Successful logical changes increment it once, regardless of the number of affected palettes.

## 9. Edit transaction and native callback protocol

All model/UI transactions serialize on the owning UI thread. Native event reentrancy does not permit nested commits.

### Transaction steps

1. Use the token captured when the interaction began; do not replace it at drop time. Validate source, destination, lock state, writer ownership, expected epoch/revision, all interaction generations and current resolution state. Missing or unresolved identities remain editable as placeholders; editing does not grant activation eligibility.
2. Build and validate a prospective immutable layout.
3. Allocate/bind required native resources in a non-interactive prepared state using the verified construction contract. Record every acquired resource in a cleanup ledger.
4. Revalidate generations and the edit token after any native call that can invoke callbacks.
5. Enter a publication guard. Queue nested extension edits; reject power activation from controls undergoing replacement.
6. Perform required fallible native attachment/registration while retaining enough of the old view to restore it. Keep the new view hidden or non-interactive according to the calibrated ABI.
7. Publish the new view and immutable model as one logical commit within the guard. No external callback may observe a new model paired with an old interactive view.
8. Retire superseded controls after callbacks using them have drained.
9. Queue the complete immutable layout revision to persistence and publish status.

The exact order of native attachment, visibility, and model publication is determined by calibrated callbacks. The invariant is fixed: before commit, failure preserves the prior logical layout; after commit, model and interactive view agree.

If the ABI cannot provide reversible publication, that is a design/calibration blocker. Do not assume native setters or child insertion are infallible.

### Failure boundaries

- Validation failure: no native allocation, no model change, no save.
- Preparation failure: clean up prepared resources exactly once; old view remains active.
- Publication failure with validated rollback: restore old view, release prepared resources, no revision.
- Publication failure where safe rollback is unavailable: enter fault containment, disable affected interaction, preserve the last known committed snapshot, and report the uncertain native state. Do not queue a partially applied layout.
- Save failure after a successful UI/model commit: keep the committed in-memory layout, mark it dirty/unsaved, and apply bounded retry. Disk persistence is separate from the synchronous UI transaction. A file error does not destroy a working palette, expose partial JSON or falsely report a save. Later edits coalesce earlier dirty revisions only by persisting one complete immutable snapshot.

### Callback and drag lifetime

Use explicit callback depth or equivalent quiescence accounting, deferred-destruction queues, and generation checks. A close request from inside a button callback schedules destruction after the callback returns. Callback quiescence alone is insufficient if native targeting or a queued action still retains the initiating control/model.

Every installed callback, vtable hook, dispatch hook and native registration needs a proven retirement strategy. Either remove it before its receiver/parent retires and drain callbacks already fetched or executing, or enter immutable terminal pass-through with process-pinned extension code and receiver-independent routing metadata. Unregistration alone does not prove that no caller already holds the callback address.

Retire tooltip/update/input registrations before releasing referenced objects. A shared process-pinned hook's terminal state prohibits retired palette receiver access while retaining valid original call-through. Prove admission/drain ordering and trampoline, original-target and callback-record lifetime; never infer quiescence from successful unregistration.

Remove parent/child links and release/finalize each object according to recovered ownership, never a guessed generic destruction order.

Do not retain stock drag objects or source controls after drop finalization/cancellation. Extract stable identity while the payload is live, then create extension-owned state through the transaction.

Drag completion cannot replay down/up input into a newly created control. Pointer capture must be returned through the native drag manager exactly once.


### Pending targeting and deferred native action references

Calibration must establish whether native targeting/action state retains the initiating control, PowerHotButtonInfo, or a referenced definition after the click callback returns. Record the completion/cancellation notification and release contract for each retained object.

Closing, resetting, rebinding, or retiring a palette must either transfer that state through a verified native ownership contract or cancel the palette-owned pending targeting through the normal native cancellation path before releasing retained resources. Do not cancel unrelated stock targeting. A logical deletion may commit while the old native resource remains non-interactive in a tracked deferred-retirement record, but final destruction waits for all verified references to drain.

Scene retirement must provide the same ordering. If the action/control reference boundary cannot be proven, the feasibility gate fails. No timer-based guess or callback-depth-only cleanup is permitted.

Placeholder shortcuts can be moved, copied, and removed while unlocked. Their native drag representation carries stable identity and shortcut-instance provenance without an invokable stale definition; this representation must be verified through the native drag manager during calibration. A resolution failure does not make the placeholder uneditable.
## 10. Character-bound persistence and concurrent clients

### Storage owner and location

Use an extension-owned directory, for example:

~~~
%LOCALAPPDATA%\ShadowbaneLab\ability-palettes\<character-key>.json
~~~

Do not write custom records into SCREEN_GAME_*.cfg.

Character-key priority is a verified stable server-issued character ID plus canonical server/shard identity whenever observable. Exact canonical server/shard plus exact character name is the fallback only when a stable character ID is unavailable. Use an explicit identity discriminator so these modes cannot collide; an account ID alone is not a character ID.

Construct the filename key from an unambiguous, length-delimited encoding of the selected identity mode and values, then encode/hash it into a safe filename. Include a deployment namespace where necessary. In stable-ID mode the display name is metadata, not part of the key or identity-equality check.

Do not silently lowercase names or infer rename equivalence. Document the native identity provider's canonicalization. In server/name fallback mode a rename creates a new storage identity unless explicit verified migration is performed. Same-name recreation cannot be distinguished safely by name alone; record that limit and require verified reset/migration when detected, never claim immutable identity. In stable-ID mode a rename preserves the key because the server-issued ID, not the name, proves continuity.

Repeat the full canonical character identity inside the document and reject mismatches. Bind the destination path when queuing a snapshot; never recompute it from whatever character is currently logged in.

### Representative version 1 document

The values below are illustrative, not calibrated profile or token evidence. This example uses explicit name fallback. The schema must also support identity_kind "server_character_id" with a verified character_id and canonical server/shard namespace, treating display name as metadata. Never populate that variant with an actor address or process-local token:

~~~json
{
  "schema_version": 1,
  "character": {
    "identity_kind": "server_character_name",
    "server_namespace": "verified-server-namespace",
    "server": "WonderBane",
    "name": "CharacterName"
  },
  "layout_epoch": "14240497-67cd-4b40-9e65-640eb51e3e42",
  "revision": 14,
  "palettes": [
    {
      "palette_id": "54d95cf9-651d-44d1-b930-ec59577010e6",
      "anchor": { "x": 0.67, "y": 0.74 },
      "rows": 1,
      "columns": 3,
      "locked": true,
      "cells": [
        {
          "shortcut_id": "e1a1c138-aea9-4fc8-bbc9-4ee670234234",
          "power": {
            "power_id_string": "ASS-013",
            "observed_token": 428918601,
            "token_profile_id": "illustrative-profile",
            "display_name_hint": "Shadow Touch"
          }
        },
        null,
        null
      ]
    }
  ]
}
~~~

Validate UTF-8, document size, depth, field lengths, finite geometry, integer ranges, identity, cell count, unique IDs, epoch/revision, and global limits before use. Version 1 rejects unknown fields; a newer schema is reported as unsupported and preserved without downgrade or overwrite.

### Single-writer policy

There is one live writer lease per canonical character key across extension clients and manager operations.

- The first runtime acquiring the lease may edit and save.
- Another runtime using the same character may load and activate its own independently resolved native views, but layout edits are read-only.
- Read-only status is visible and separate from persisted palette lock state.
- A reader consumes only validated committed snapshots. External updates arriving during a native click or targeting transition are deferred until its view can be safely replaced.
- On lease availability, a runtime reacquires ownership and reloads the latest disk epoch/revision before enabling edits. It never writes its older read-only snapshot.
- The manager routes live reset/export requests to the exact owning runtime. Offline mutations must acquire the same lease.
- Different character keys have independent leases and save queues.

Lease lifetime follows the actual writer process/session and cannot be simulated by an unchecked stale lock file. Worker operations retain their lease until all writes for that ownership period have completed or been canceled.

Atomic replacement alone is not the concurrency policy.

### Worker protocol

Each immutable save envelope contains canonical character identity, validated destination, writer lease/session ID, layout epoch, revision, and complete document.

The bounded worker queue coalesces only within the same identity, epoch, and ownership session. Never coalesce unrelated characters. Reject stale revisions and canceled epochs before starting a write and again before replacement if ownership could have changed.

Writes use a unique same-directory temporary file, schema validation, the platform durability flush required by the chosen atomic-replacement implementation, and replacement of the prior committed file. Recover abandoned temporary files conservatively; they are never silently promoted solely because they are newer.

Validate the storage root and opened destinations against path redirection/reparse-point races using a reviewed file-handle/path policy. Do not rely only on a pre-write string prefix check.

Keep one last-known-good validated backup with bounded retention. A write failure leaves the previous committed layout intact.

### Failures, reset, logout, and shutdown

- Retry recoverable I/O failures with bounded backoff and coalescing; after the retry budget, remain unsaved and allow explicit retry. Never spin or block the UI thread.
- Report current in-memory revision and last successfully persisted revision.
- On logout, preserve the old character's queued envelope and bound path until its save completes or fails; then release that writer lease. Loading another character does not redirect the old write.
- Runtime disable destroys native views safely and lets the pointer-free store finish pending persistence under its own lease. Controls need not stay alive while a save finishes.
- Graceful extension shutdown attempts a bounded worker drain outside UI callbacks. A timeout reports unsaved state; process termination cannot guarantee the final unsaved revision.
- Do not unload module code while its persistence worker is still running.
- Reset runs through the writer owner, cancels active edits, creates a new empty layout epoch, and invalidates older queued saves. Coordinate any in-flight replace so an old epoch cannot overwrite the reset afterward.
- A corrupt primary file is reported with a recovery/export path. Do not auto-save an empty layout over it. Restore a verified backup or reset only through an explicit recovery operation.
- Unknown newer schemas are preserved and edits remain unavailable until a supported reader/migration or explicit reset is used.

## 11. Runtime, scene, and fault lifecycle

### Independent state dimensions

Keep global runtime availability, per-palette edit state, power resolution, and persistence health separate.

Global runtime states:

~~~
disabled
unavailable_build
waiting_for_hud
waiting_for_character
ready
active
suspended
faulted
~~~

ready means dependencies are validated and no palette view is currently active. active means at least one usable view exists. suspended means a previously valid runtime is temporarily unable to present/interact while retaining layout state. A separate reason identifies scene transition, missing space, or another transient cause.

Per-palette state includes locked/unlocked, presentation page, visibility/suspension, and edit transaction state. Persistence includes writable/read_only, saved/pending/unsaved, and load/recovery errors.

Only supported, explicitly classified transient conditions recover automatically. A vtable, code identity, ownership, or ABI-contract violation latches faulted until a new validated runtime/process session. Do not repeatedly retry a potentially corrupt call.

### Shared snapshot and retirement ordering

The shared service provides a generation-bound snapshot containing HUD, owning HWND, logical bounds, modal/input ownership, drag state, process/scene/HUD/character generations, UI-thread identity, and observation validity.

It is immutable for its use interval, but not a promise that pointers remain valid indefinitely. Consumers revalidate generation and execute native calls only within the service's verified lifetime boundary.

Retirement protocol:

1. Stop admitting new palette edits and activations.
2. Cancel active native drags and invalidate pending edit tokens.
3. Revoke power bindings and queued callbacks for the retiring generation.
4. Unregister and destroy native palette resources on the owning UI thread before the parent HUD retires, following calibrated ordering.
5. Retain only pure layout/store state.
6. Wait for the new exact HUD and stable character binding.
7. Reload when character identity changes; otherwise rebuild the retained layout against the new generation.

If a pre-destruction retirement boundary cannot be proven, native UI construction remains blocked.

### Normal disable versus fault containment

Normal disable uses validated cancellation, unregistration, detachment, deferred destruction and callback draining. On completion, no live palette view, receiver-bound registration or admitted palette callback remains. A verified process-pinned shared hook may remain only in immutable terminal pass-through with no retired receiver access; report retained infrastructure truthfully rather than claiming it was uninstalled.

Fault containment must not invoke a destructor, cancel function, or child-removal method whose receiver or binding has become unsafe. Immediately revoke extension activation/edit admission and stop new native work. Use only cleanup operations whose receivers, generation, and code bindings remain validated.

If safe cleanup cannot finish:

- Report incomplete native cleanup and the reason.
- Keep necessary module code resident so remaining native references cannot call unloaded code.
- Prevent automatic re-enablement in that process.
- Require client restart for full recovery.

Do not describe this state as successfully disabled or unloaded. The promise that stock UI is untouched applies to pre-installation unsupported-build rejection; a runtime corruption fault requires truthful containment status rather than that impossible guarantee.

## 12. Calibration and build configurations

### Configuration boundaries

| Configuration | Permitted palette behavior |
|---|---|
| Diagnostics-only | Bounded passive observations, parsers, and evidence export; no palette native construction or invocation. |
| Developer-calibration | Explicitly gated active factory/invocation/teardown proofs on an exact profile; never packaged for ordinary release. |
| Full production | Reviewed native feature only after the complete profile and package gates pass. |

The developer-calibration path is separate from the diagnostics-only capability. Its entry points must not be reachable through ordinary production manager commands or included by accidental source membership.

### Passive stock actions to observe

Open/close Powers; hover tooltips; drag Powers to hotbar; move stock hotbar entries; click instant, targeted, stance/toggle, cooldown, disabled, and insufficient-resource powers; cancel and complete targeting; observe rank changes; close the source during a drag; lose capture/focus; open a modal; change scenes; log out.

Also inspect native frame controls for moving, cell-snapped resizing, close/lock buttons, page controls, z-order, hit testing, and child destruction.

### Evidence required for each boundary

- Exact executable/profile and source SHA.
- Receiver type, expected vtable or code signature, calling convention, arguments, and thread.
- Object allocation, reference, subscription, and parent/child ownership.
- Drag provenance, payload identity, acceptance, finalization, and cancellation.
- Construction failure and partial cleanup behavior.
- Tooltip/update registration independent of hotbar-key registration.
- Activation, targeting, cooldown, disabled/resource rejection, and rank/active-state updates.
- Observed pre-retirement and teardown ordering.
- Bounded trace identifiers linking stock and independent-control comparisons.

Passive evidence produces candidate contracts. Active developer validation proves independent construction and destruction. A single non-crashing call never establishes ownership correctness.

Diagnostics are bounded, opt-in, and keep unrelated character data or private captures out of source delivery. Publish appropriate sanitized source evidence with explicit draft/reviewed status.

## 13. Implementation phases and exit gates

Each phase ends with relevant validation, a reviewed diff, a coherent commit, push where configured and appropriate, and an updated handoff/todo record. Gate failure is recorded with concrete missing evidence. Do not proceed into dependent unsafe native work.

### Phase 0 — Verify baseline and freeze contract

Work:

- Fetch the relevant remote; inspect documented integration destination, upstreams, ancestry, branch tracking, and worktrees.
- Verify the repository facilities listed in section 5.
- Produce the section 5 source-selection record, including source pin, integration owner/merge-base, descendant review, reuse boundaries, protected work and required profiles/tests, before creating any production branch.
- Only after that record exists, reuse an appropriate production branch or create codex/native-power-palettes from the verified reconciled tip. A documentation-only branch may precede production branching.
- If another task owns the checkout, use a separate worktree. Preserve all existing user changes.
- Add the feature design/ADR, behavior matrix, schema direction, decision register, acceptance map, and delivery destination.

Exit gate:

- The source-selection record exists before production branching and identifies the exact baseline, integration owner/destination and protected branch-local work.
- Product semantics are explicit; unresolved native facts are labeled calibration questions.
- No feature construction or dispatch is represented as proven.
- Existing tests/profile builds establish a baseline before native/refactor changes.

### Phase 1 — Passive exact-build calibration

Work:

- Introduce bounded diagnostics-only observations without altering stock drop or activation behavior.
- Recover the native power registry, learned observation completeness, source controls, payload provenance/ownership, drop dispatch, factories, update/tooltip registration, invocation, HUD parentage, and retirement ordering.
- Recover native frame/chrome/input operations; record the selected safe resize, removal, unlock and copy/move indication mechanisms without assuming stock APIs exist.
- Assemble a single exact-build profile and evidence manifest.
- Identify all candidate factory/ownership contracts needed by the active proof.

Exit gate:

- Receivers, signatures, arguments, threads, and observed ownership are documented.
- Supported stock behavior has traceable baseline evidence.
- Active validation can be attempted under an explicit developer-calibration gate without guessed addresses or ownership.
- Missing evidence blocks only dependent work; safe documentation/pure analysis can continue.

### Phase 2 — Independent native shortcut feasibility proof

Work:

- Use the existing reviewed lifetime/UI owner through a narrow adapter; do not install a duplicate hook for the proof.
- On the UI thread, construct fresh PowerHotButtonInfo and one independent genuine native power control under a native frame.
- Avoid stock slot/key registration and source-control retention.
- Prove icon, tooltip, cooldown, resource/disabled state, rank, active state, native hit testing, and click behavior.
- Compare instant, targeted, stance/toggle, invalid-target, cooldown, insufficient-resource, and unlearned rejection against stock behavior.
- Prove source-window closure independence, immediate pre-activation revalidation, per-pointer-sequence at-most-once admission, repeated teardown and retirement before HUD destruction, including fetched/in-flight callbacks.
- Exercise partial-construction failures and deferred cleanup.

Exit gate:

- A genuine independent shortcut behaves like its stock counterpart without stock-hotbar allocation, hidden-stock clicks, synthetic input, or packet bypass.
- Invocation evidence matches the reviewed stock contract, not only the resulting animation.
- Repeated creation/destruction and scene retirement show correct ownership.
- Active proof entry points remain developer-only.
- Negative exit: if no permitted route meets the gate, stop all production palette phases and deliver the bounded calibration report specified in section 1. Do not implement layout, persistence, substitute UI or dependent extraction until new evidence satisfies the gate.

### Phase 3 — Extract shared native UI and lifetime services

Work:

- Narrowly extract native_ui_context and client_scene_lifetime from verified existing ownership.
- Preserve one owner for HUD identity, input gates, coordinate conversion, lifecycle hooks, and UI-thread dispatch.
- Migrate movement and the proven palette integration to the shared services.
- Preserve movement behavior through characterization and production-boundary regression checks.

Exit gate:

- Both consumers use the same generation/input/lifetime source.
- Movement parity and existing native profile builds pass.
- No competing subclass, duplicate lifetime hook, or forked offset table remains.
- Proven native shortcut behavior survives the extraction.

### Phase 4 — Complete model, schema, resolver, and store

Work:

- Implement pointer-free grid/edit semantics and limits from sections 3, 4, and 8.
- Implement schema validation, exact character keys, epoch/revision rules, atomic recovery, single-writer ownership, and bounded saves.
- Implement resolver states, observation freshness, duplicate refresh, and token/profile migration policy.
- Define the versioned status/control wire contract before UI/manager integration.

Exit gate:

- Pure model, schema, migration, concurrency, failure, and persistence round-trip tests pass without the game.
- Native resolver integration rejects stale generations and incomplete observations correctly.
- Reset, character switch, and save-failure scenarios preserve the defined committed state.
- No file I/O occurs inside native callbacks.

### Phase 5 — Production palette runtime and one-slot integration

Work:

- Integrate the proven native control with the production model, resolver, transaction protocol, status, and lifecycle services.
- Add native lock, close, remove, and placeholder views.
- A developer-only spawn entry may exercise the real runtime before drag integration.
- Implement current-generation restoration and complete teardown.
- Keep callbacks safe during view publication, close, unlearning, and focus/modal transitions.

Exit gate:

- One production palette passes click, native presentation, input ownership, placeholder/reactivation, save, restore, and teardown checks.
- Injected factory/publication failures preserve the transaction contract.
- No leaked callbacks or double finalization appear.
- The diagnostic spawn route is not required for release use.

### Phase 6 — Native drag/drop and complete multi-palette editing

Work:

- Register native palette drop targets and inspect native payload provenance.
- Preserve stock-origin stock-target routing.
- Add Shift-drop empty-HUD creation and every supported matrix gesture.
- Reject unsupported transfers before stock or extension source mutation.
- Add move, snap resize, occupied-cell insertion, reorder, copy, limits, auto-empty cleanup, and multiple palettes.
- Add native constrained-viewport paging and reachable controls.

Exit gate:

- Every matrix row and cancellation condition is covered.
- Same-slot no-ops and failed drops create no revision.
- Native drag finalization/capture ownership is balanced.
- No activation occurs on drop or drag cancellation.
- Ordinary Powers/hotbar behavior matches the recorded observable baseline.
- All shortcuts remain reachable across supported HUD sizes.

### Phase 7 — Restoration, controls, concurrency, and hardening

Work:

- Complete cold-start, relog, scene replacement, retraining, and resolution restoration.
- Integrate launch disable, runtime disable, current-character reset, export, persistence retry/recovery, and status.
- Complete same-character read-only clients, writer takeover, and different-character isolation.
- Validate graceful shutdown, pending writes, reentrant callbacks, and fault containment.
- Verify operation with the manager closed.

Exit gate:

- Full user workflow survives process/character/scene changes.
- Data and native bindings remain isolated between clients.
- Unsaved, read-only, waiting, disabled, and fault states are truthful and actionable.
- Normal disable leaves no live palette controls, receiver-bound registrations or admitted callbacks. Verified shared hooks may remain terminal and process-pinned; unsafe cleanup is reported without module unload.
- No source-draft or temporary proof dependency is required to use the feature.

### Phase 8 — Package candidate, connected acceptance, and integration

Work:

- Enforce exact source/profile membership and configuration exclusions.
- Build/install the exact candidate and validate status decoding from that installed package.
- Execute the connected-client checklist and stress gates below.
- Record source SHA, normalized client identity, profile ID, package hash, test/evidence manifest, and integration status.
- Remove obsolete task-generated scratch/proof artifacts from release inputs.
- Prepare the PR/integration review and current handoff documentation.

Exit gate:

- All definition-of-done items have evidence for the same packaged candidate.
- Source and deliverable identity match; failures lead to a new candidate and appropriate revalidation.
- Pushed branch/SHA, PR or explicit integration destination, remaining outside-source tips, and next integration step are documented.
- Required review/merge authorization is respected; a push is not reported as a merge.

## 14. Runtime status, control operations, and packaging

### Versioned status contract

Publish bounded, pointer-free status containing:

~~~
schema_version
runtime_state
runtime_reason
supported_profile_id
process_binding_id
scene_generation
character_generation

capabilities
    native_ui
    power_resolution
    power_execution
    drag_source
    drop_target
    persistence

layout
    palette_count
    shortcut_count
    layout_epoch
    current_revision
    persisted_revision
    writer_mode: writable | read_only | unavailable
    save_state: saved | pending | unsaved | load_error
    suspended_palette_count

counters
    activation_attempt_count
    observed_native_submission_count (only where independently measurable)
    canceled_drag_count
    rejected_edit_count
    live_control_count
    pending_callback_count

cleanup
    complete | draining | restart_required

last_error
    stable_code
    bounded_detail
~~~

A capability means the required reviewed implementation is available. It does not imply current HUD/character readiness or write ownership. Advertise no native execution/UI capability on an unsupported profile. Unknown status versions must be handled explicitly by the manager, without fabricated readiness.

Do not confuse an activation attempt, accepted native submission, and observed gameplay effect. Evidence and counters identify which one was observed.

Errors should distinguish unsupported build, missing binding, unresolved character, incomplete observation, limits, stale edit, lock/read-only rejection, factory/publication failure, save failure, schema/corruption, and unsafe cleanup. Routine rejected drops may use inline native feedback rather than persistent fault alarms.

### Controls

- Launch-time disable prevents palette initialization/hooks.
- Runtime disable follows the normal cleanup protocol; its response reports completion versus draining/restart-required.
- Runtime enable requires validated support and a fresh current binding; a latched unsafe fault cannot be cleared by toggling enable.
- Reset targets the exact current character under the writer lease and uses the epoch protocol.
- Export produces the current validated layout, including an explicitly labeled unsaved in-memory revision when applicable.
- Retry/recovery surfaces explain save or load failure without requiring extension uninstall.

Normal palette creation, locking, and use do not require the manager. Native UI status must provide concise read-only/unsaved/temporarily-unavailable feedback without obscuring power icons.

### Required package gates

- Exact source membership and reviewed source SHA.
- Unified profile membership with normalized executable identity.
- Diagnostics-only exclusion of native construction/invocation.
- Production exclusion of developer-calibration/proof entry points.
- Native/pure tests and shared movement parity.
- Production-boundary stock drag and activation regressions.
- Installed package capability/status decoding.
- Persistence schema and bounded-input validation.
- No palette-subsystem synthetic-input or overlay dependencies.
- Callback/module lifetime and normal disable teardown.
- No private capture, credentials, client binaries, or unrelated scratch output in published source.

## 15. Validation strategy and evidence requirements

### 15.1 Pure/model/schema tests

Run portable pure tests without loading the game:

- Every drop-matrix model outcome, including occupied cells, gaps, same-slot no-op, shift-copy, full-grid growth, and cross-palette cleanup.
- Duplicate powers with unique instance IDs; duplicate palette/shortcut ID rejection.
- Locked/read-only destination/source and stale epoch/revision rejection.
- Copy preserves source; move preserves instance ID; failed edit leaves both layouts unchanged.
- Resize/reflow preserves order and required gaps; insufficient capacity rejects; bounds and limits hold.
- Coordinate origin handling, normalized anchors, clamping, paging cell mapping, and temporary resolution changes without persisted layout drift.
- Malformed JSON, UTF-8, unknown fields/version, invalid geometry, integer overflow, excessive size/depth, wrong cell counts, and field lengths.
- Character mismatch, discriminated stable-ID/name key separation, stable-ID rename continuity, name-fallback rename separation, explicit migration, unknown power retention, placeholders and token mismatch rejection.
- Complete versus incomplete learned observations and duplicate refresh.
- No-op versus successful revision behavior.

### 15.2 Store and platform integration tests

Use real temporary directories and controlled concurrency/failure injection where needed:

- Complete persistence round-trip and same-directory atomic-replacement recovery.
- Interrupted temporary write, replace failure, backup recovery, and abandoned temp handling.
- Corrupt primary and newer schema preserved without automatic empty overwrite.
- Same-character writer exclusion, read-only behavior, writer death/release, and takeover reload.
- Different-character queue independence and stable destinations after character switch.
- Coalescing within an epoch/session only; stale write rejection.
- Reset racing with pending and in-flight saves.
- Retry exhaustion, bounded queue size, truthful unsaved status, and graceful-drain timeout.
- Path redirection/reparse handling using the chosen platform file policy.

Do not treat a mock of replacement or locking as proof of the real platform behavior.

### 15.3 Native ABI and runtime tests

Fakes/fixtures validate wrapper contracts; connected evidence validates the actual ABI:

- Exact receiver, arguments, calling convention, supported profile, and UI-thread admission.
- Wrong thread, vtable, profile, or generation rejects before an unsafe call.
- Partial construction failures unwind each acquired resource once.
- Native subscriptions, parent/child membership, callbacks, references, and finalizers balance.
- Close/reset/retirement from inside callbacks defers destruction safely.
- Publication callbacks cannot observe inconsistent model/view state.
- Hit testing, modal ownership, z-order, native tooltip, and input consumption.
- Native payload identity copied while live; payload/source pointers never escape drag lifetime.
- Stock-origin stock-target dispatch preserves original behavior.
- Unsupported transfer cannot mutate either side.
- Drag completion, down/up sequences, and cancellation do not double-activate.
- No creation after focus loss, source closure, character change, or target retirement.
- Missing/unlearned resolution never activates stale controls.
- Normal disable drains live controls/callbacks; allowed terminal shared hooks never access retired receivers; fault cleanup never calls invalidated methods.
- Hold a fetched-but-not-entered callback across unregistration and prove safe terminal routing/admission before receiver release.
- Change process/character/scene/HUD/control, layout, definition/learned state or modal ownership between interaction start and native activation; reject stale invocation.
- Reentrant invoke and duplicate down/up handling consume a pointer sequence at most once.
- Whole locked/unlocked palette rectangles consume gap/empty-cell input; locked/chrome/stale drop rejection never reaches Shift-create or a target behind it.
- The selected permitted native UI-class route satisfies the game-hierarchy ownership contract; implementing both alternatives is not required, and custom cursor/Win32/overlay substitutes remain excluded.
- No second lifetime owner, overlapping subclass, or duplicated build profile.

### 15.4 Connected-client acceptance checklist

Run against one exact installed candidate and record evidence for each applicable item:

1. Cold-start supported client; verify installed package SHA/profile/status.
2. Open stock Powers and Shift-drag an instant power onto empty HUD.
3. Verify one unlocked native palette at the clamped drop location.
4. Verify source Powers entry, stock hotbar slots, F-key registrations, and stock config are unchanged.
5. Hover and compare native tooltip with stock.
6. Click instant power and compare native submission/effect evidence.
7. Click targeted power; complete targeting.
8. Repeat targeted activation and cancel normally.
9. Compare stance/toggle active state and native updates.
10. Compare cooldown, disabled, insufficient-resource, and invalid-target rejection.
11. Close Powers and verify the palette continues working independently.
12. Add powers into empty and occupied cells; verify insertion and preserved order.
13. Test full-grid growth and each configured limit boundary, including copies that would exceed the character total.
14. Reorder within one palette, including both movement directions and empty-cell destinations.
15. Verify same-cell drops are no-ops with and without Shift.
16. Create a second palette and move a shortcut between them.
17. Shift-copy between palettes and Shift-copy a palette shortcut onto empty HUD.
18. Verify duplicate power instances remain distinct and update together.
19. Resize between one and multiple rows/columns; reject a destructive shrink.
20. Move and lock the palette; verify edits and incoming drops reject, empty cells/gaps/borders remain UI-owned in both states, and Shift-drop cannot create behind it.
21. Unlock without icon overlap or unintended activation.
22. Use the selected native removal action, including context-command isolation if chosen; remove the last shortcut and close a populated palette without activation.
23. Verify invalid drops never delete shortcuts.
24. Verify both excluded stock-hotbar transfer directions reject without source/target mutation.
25. Repeat ordinary Powers-to-stock-hotbar and stock-hotbar rearrangements against the stock baseline.
26. Lose focus/capture, change Shift and open a modal during drags; verify unambiguous copy/move indication through the selected native mechanism.
27. Retire the source, close the destination or change its layout revision during a drag; also drop on title, resize, remove/lock/close chrome. Verify cancellation without retargeting or Shift-create.
28. Open chat, inventory, training, world map, and modal UI while interacting.
29. Begin movement/camera activity, then use a palette; verify no world-input fallthrough.
30. Log out/in on the same character and verify exact layout restoration.
31. Restart the client and verify cold-start restoration.
32. Switch character and server; verify layout and native binding isolation, then return.
33. Change resolution/UI scale where supported; verify reachable controls, paging, drag-hover transfer across pages, stable cell mapping, and no permanent saved-layout drift.
34. Unlearn/remove a power and verify a truthful disabled placeholder.
35. Retrain it and verify automatic reactivation; verify rank changes and incomplete-observation handling.
36. Run two clients with different characters and verify process/character isolation.
37. Where the client/server permits simultaneous same-character sessions, exercise actual read-only/writer takeover; otherwise retain multi-process store evidence and document that connected limitation.
38. Force a save failure, edit again, retry, and verify the latest complete revision is recovered.
39. Exercise reset during pending saves and confirm old data cannot resurrect.
40. Exercise corrupt/newer layout files, export/recovery, and manager-closed operation.
41. Disable normally during idle and active drag; verify complete cleanup and preserved layout.
42. Exercise controlled developer seams for between-event binding changes, duplicate/reentrant activation and fetched callbacks during retirement. Verify at-most-once invocation, containment and restart-required status without intentionally corrupting live client memory.
43. Test an unsupported profile/candidate and verify no feature interaction hooks or native construction.
44. Execute stress runs and inspect reference, callback, control, memory, and crash evidence.

### 15.5 Initial stress thresholds

Before running stress acceptance, capture a warmed-up stock/client baseline and choose representative powers with permitted repeated activation behavior.

- 500 native create/hover/close cycles; include ordinary clicks only when native power state permits.
- 1,000 mixed model/native edit operations covering copy, move, resize, remove, and page replacement.
- 50 HUD/scene retirement-and-restore cycles where controllable.
- 10 complete relog cycles and 10 supported resolution changes.
- Zero crashes, invalid native calls, duplicate activation events, orphaned subscriptions, or ownership imbalances.
- Live receiver-bound objects/callbacks return to baseline after quiescent teardown. Any verified process-pinned terminal infrastructure has an explicit fixed inventory and cannot grow across enable/disable cycles.
- Known native caches must be measured separately; no unexplained monotonic retained-allocation growth is accepted.

These are initial minimum acceptance counts. If a connected operation is externally impractical, record the shortfall and equivalent coverage explicitly; do not silently mark the gate passed. A different justified threshold requires an updated written acceptance contract before execution.

### 15.6 Evidence manifest and regression oracle

For each candidate record source SHA, pushed branch, integration base, profile/client identity, package hash, configuration, tests, trace IDs, screenshots where helpful, observed native effects, and failure notes.

The stock-behavior oracle compares original dispatch/target selection, source ownership, final slot/config state, activation count, targeting state, and cleanup. Replace the original phrase "bit-for-bit behaviorally unchanged" with these measurable invariants.

Fakes, code signatures, and screenshots are supporting evidence; none alone proves stock-equivalent runtime behavior.
## 16. Proposed source and documentation layout

Confirm actual repository conventions before assigning final paths. The ownership boundaries are required; filenames may follow existing conventions rather than creating parallel abstractions.

### Native production

~~~
native/wonderbane_extension/
    ability_palette_types.h
    ability_palette_model.h / .cpp
    ability_palette_client.h / .cpp
    ability_palette_resolver.h / .cpp
    ability_palette_runtime.h / .cpp
    ability_palette_drag.h / .cpp
    ability_palette_store.h / .cpp
    ability_palette_status.h / .cpp
    native_ui_context.h / .cpp
    client_scene_lifetime.h / .cpp
~~~

Use the repository's existing canonical profile mechanism for the unified target-build profile. Do not add a palette-only profile file if that would duplicate the shared build authority.

### Diagnostic and developer-only

~~~
native/wonderbane_extension/
    ability_palette_probe.h / .cpp
    ability_palette_trace.h
    ability_palette_developer_proof.h / .cpp
~~~

Keep passive probe membership separate from active developer proof membership in build manifests and tests.

### Tests, schemas, and manager

~~~
native/wonderbane_extension/
    ability_palette_model_test.cpp
    ability_palette_resolver_test.cpp
    ability_palette_store_test.cpp
    ability_palette_drag_test.cpp
    ability_palette_client_test.cpp
    ability_palette_runtime_test.cpp
    ability_palette_production_boundary_test.cpp

schemas/
    ability-palette-v1.schema.json

src/shadowbane_lab/client_extension/
    ability_palette_status.py
    ability_palette_layout.py

src/shadowbane_lab/manager/
    ability_palette.py

tests/
    test_ability_palette_layout.py
    test_ability_palette_status.py
    test_ability_palette_package.py
~~~

Python decodes/validates layouts and status and supports manager operations. It does not own native power activation or compete with the runtime writer. Keep schema fixtures shared so native and Python readers agree.

### Documentation

~~~
docs/
    power-palettes.md

docs/investigations/
    power-palettes-source-selection.md
    native-power-button-boundary.md
    native-power-drag-boundary.md

docs/handoffs/
    native-power-palettes.md
~~~

The design document owns product behavior and architecture. Investigation documents own calibration evidence and unresolved contracts. The handoff owns exact branch/source inclusion, candidate evidence, active todo, and next integration step.

## 17. Git checkpoints, integration, and checkout hygiene

### Baseline and branch handling

Before repository edits, inspect git status --short --branch. Fetch the relevant remote and inspect documented integration branch, upstream tracking, git branch -vv, worktrees, and source ancestry. Report a real fetch failure rather than treating stale refs as current.

The supplied 310620bc reference may be an ancestor, a reviewed branch tip, or work already integrated elsewhere. Determine which before choosing a base. Prefer the verified reconciled integration tip; do not assume either main or a feature-looking branch is the right source.

Before any production branch is created, publish the complete source-selection record against fresh refs. Then use codex/native-power-palettes unless an appropriate existing branch already owns production work. The current codex/power-palettes-plan branch owns documentation only. Never switch a checkout another active task is modifying. Preserve unrelated user changes and stage only task-owned files.

### Recommended coherent commits

1. docs: freeze Power Palette contract, baseline, decisions, and acceptance map.
2. diagnostics: record passive stock power, drag, ownership, and lifetime evidence.
3. native: define unified target-build candidate bindings and validation.
4. native: prove independent keyless power control and invocation in developer configuration.
5. refactor: share native UI context with movement parity.
6. refactor: share scene lifetime with movement parity.
7. feat: add complete palette model, edit semantics, limits, and schema.
8. feat: add character-bound store, writer ownership, reset epochs, and recovery.
9. native: add current-generation power resolver and placeholders.
10. native: integrate production palette runtime and transactional native views.
11. native: add palette drop targets and guarded Shift-drop creation.
12. feat: complete multi-palette editing, locking, removal, and constrained layout.
13. feat: complete restoration, status/control operations, and concurrent clients.
14. hardening: validate callback, targeting, focus, scene, fault, and shutdown lifetimes.
15. packaging: enforce profiles, production boundaries, schema, and installed status gates.
16. acceptance: record exact candidate evidence and integration handoff.

These are logical checkpoints, not an instruction to force unrelated changes into a fixed commit count. Split a large unit further when reviewability requires it. Keep both shipping profiles buildable after every committed checkpoint; validate the developer configuration where relevant.

For each checkpoint:

- Run the relevant safe validation.
- Review the unstaged diff and stage only owned changes.
- Recheck the staged diff and commit a coherent unit.
- Push with upstream tracking when a remote is configured and appropriate.
- Update the user with what passed and the next active todo.
- If push is blocked, leave the exact branch/commit ready and report the cause.

### Integration and final audit

A pushed task branch is not integrated delivery. Keep the repository handoff discoverable with exact pushed SHA, integration destination, PR/review status, included source tips, remaining excluded work, and next step.

Do not merge without required review/authorization. After verified integration, retire only obsolete task-owned branches/worktrees whose tips are retained in intended remote history and which have no active task or unpreserved files.

Prefer a clean canonical shared checkout when safe, with fast-forward updates only. Report actual checkout separately from delivered branch, commits, push status, integration/PR status, uncommitted/untracked leftovers, and next todo. If cleanup must wait, record why.

## 18. Decision register and remaining calibration questions

### Product and architecture decisions established by this expansion

| Decision | Contract |
|---|---|
| New palette gesture | Shift at drop over valid empty HUD; new palette unlocked. |
| Source semantics | Powers copies; palette moves by default and Shift copies. |
| Occupied destination | Insertion/reorder rules preserve every shortcut. |
| Same-slot drop | No-op with either modifier state. |
| Locked palette | Full rectangle remains UI-owned; rejecting drop target with no Shift-create or world fall-through. |
| Removal | Independent native action via verified control or context command; cannot activate; outside drop never deletes. |
| Stock-hotbar transfer scope | Both extension transfer directions excluded initially; ordinary stock workflows preserved. |
| Grid authority | Explicit rows/columns and cells; normalized anchor, native cell metrics. |
| Constrained display | Temporary native paging; no loss or automatic rewrite of saved grid. |
| Duplicate powers | Allowed; distinct stable shortcut-instance IDs. |
| Missing power | Disabled placeholder, editable/removable, never substituted. |
| Same-character clients | Single writer; other runtimes read-only for layout edits. |
| Reset | New epoch prevents stale-save resurrection. |
| Native failure | Separate safe normal teardown from fault containment. |
| Execution owner | In-process UI-thread native path; no host dispatch dependency. |
| Feasibility sequence | Independent native proof precedes production; failure stops the feature line with a bounded calibration report. |
| Native qualification | Participation in the game UI hierarchy and lifecycle; verified stock class or verified game UI ABI. |
| Routing | Owning stock target first for stock sources; eligible cell next; rejecting palette consumes; Shift-create last. |
| Activation | Revalidate at stock native activation phase; one admission per native pointer sequence. |
| Mechanism selection | Calibration chooses verified resize/removal/unlock/drag indication routes while preserving required behavior. |
| Character identity | Stable server-issued character ID plus shard first; discriminated exact-name fallback only when unavailable. |
| Callback retirement | Drain fetched/executing calls or use verified process-pinned terminal pass-through without retired receivers. |
| Release proof | Installed exact candidate plus connected native-effect evidence. |

These are explicit planning defaults, not assertions that the current client already supports the required native contracts. Changing one requires updating the behavior matrix, schema/model where applicable, tests, and acceptance checklist together.

### Facts still requiring repository/native evidence

1. Refresh the recorded source tip and integration destination before production; this documentation pass selected the fetched 310620bc source without starting native work.
2. The packaged client identity and whether all existing bindings can be unified.
3. Native power registry identity/token semantics across supported builds.
4. Learned observation completeness and freshness, including granted powers and rank changes.
5. Independent factory/private-model construction without global hotbar or key side effects.
6. Tooltip/cooldown/active-state subscription ownership outside the stock hotbar.
7. Drag finalization/provenance contracts, especially unsupported transfer rejection.
8. Reversible native view publication and callback reentrancy.
9. Pre-HUD-retirement cleanup and references held by pending targeting/actions.
10. Native frame/chrome/page controls and current input ownership behavior.
11. Exact character key guarantees, including any rename/recreation ambiguity.
12. Actual platform store/lease/replacement primitives and shutdown scheduling.
13. Stress-supported limits and accepted native cache behavior.

These questions are discovery deliverables with phase gates, not permissions to invent offsets, substitute implementations, or claim readiness prematurely.

## 19. Definition of done

Power Palettes are complete only when all of the following are evidenced for the release candidate:

- The independent native feasibility gate is proven before production phases; a failed gate ends in a bounded report, never a fallback implementation.
- The production source-selection record predates production branching and matches refreshed source/ownership evidence.
- Shift-drag from stock Powers to empty HUD creates a qualifying native palette without altering its source.
- Stock Powers/hotbar interactions, stock config, stock slots, and F-key registrations retain their ordinary behavior.
- A palette shortcut uses the stock native activation phase and targeting lifecycle, with immediate interaction-token revalidation and at-most-once pointer-sequence admission.
- Tooltip, cooldown, resource/disabled, rank, stance/toggle, and active-state presentation match native behavior.
- Multiple palettes support the complete move/copy/reorder/resize/lock/remove contract.
- Occupied cells, gaps, chrome, closing/stale destinations, limits, same-slot drops, unsupported transfers and cancellation follow normative owning-target precedence; full visible rectangles never leak world input.
- Every shortcut remains reachable after resolution changes without silent layout loss.
- Stable identities survive save/restart/relog; missing powers remain truthful placeholders and retraining reactivates them.
- Current observations and generations prevent stale identity or native pointer activation.
- Layout storage is character/server-bound, bounded, schema-validated, recoverable, and protected against concurrent stale writers.
- Reset and character changes cannot resurrect or misroute older saves.
- Manager-closed use, status, export, disable, retry/recovery, and same-character read-only behavior work.
- Modal/focus/capture, movement/camera, scene/character/HUD, pending targeting, and multi-client boundaries pass.
- Normal teardown is balanced and UI-thread-owned, accounts for fetched/in-flight callbacks and leaves only explicitly inventoried safe terminal infrastructure where required; fault containment never calls invalid cleanup or unloads referenced code.
- Unsupported profiles fail before feature hooks/construction and do not alter stock behavior.
- No synthetic-input, overlay, hidden-hotbar, packet, or host-dispatch substitute exists.
- Pure, platform, ABI/runtime, package, installed-candidate, and connected stress gates pass with recorded evidence. Any unresolved required failure blocks completion; external test limitations are documented with the alternative evidence expressly permitted by the acceptance contract.
- Source SHA, profile/client identity, package hash, pushed branch, PR/integration destination, source inclusion, and handoff are current and discoverable.
- Required review/integration steps and task-created leftovers are accounted for.

No screenshot, demo spawn, successful build, or one-time activation substitutes for this complete definition.

## 20. Current todo state and next action

This checklist records planning readiness only. It does not mark implementation or calibration as completed.

- [x] Review the supplied implementation plan.
- [x] Expand the behavior, ownership, persistence, lifecycle, delivery, and validation contracts.
- [x] Define phase exit gates and distinguish verified facts from required discovery.
- [x] Incorporate all eleven second-review requests into the contract, phases and validation gates.
- [x] Fetch and record the documentation source, ancestry, reuse boundaries and protected worktrees; adopt the plan in repository documentation.
- [ ] **Active next implementation item: complete Phase 0 readiness — refresh the source record, finish facility verification and establish required test/profile baselines before production branching or native changes.**
- [ ] Phase 1 — passive exact-build calibration.
- [ ] Phase 2 — independent native shortcut feasibility proof.
- [ ] Phase 3 — shared native UI/lifetime extraction with movement parity.
- [ ] Phase 4 — complete pure model, resolver, schema, and store.
- [ ] Phase 5 — production palette runtime integration.
- [ ] Phase 6 — native drag/drop and complete editing.
- [ ] Phase 7 — restoration, controls, concurrency, and hardening.
- [ ] Phase 8 — exact package acceptance and integration handoff.

The requested plan revision and documentation source-selection work are complete. No native calibration, production branch, implementation, package, deployment or integration merge is claimed. Phase 0 remains partly open because baseline test/profile execution and complete native-facility verification were outside this documentation task.
