# PvE/PvP attack-list delivery plan

Updated September 12, 2026. Integration destination: codex/native-lifecycle-hardening.
User priority is PvE/PvP; door work is separate and does not gate this delivery.
This document records a plan, not an implemented combat capability.

## Agreed behavior

Blacklist means ATTACK LIST, never an exclusion list. Entries may be added by an
explicit chat command or by the response system identifying an attacker. List
membership expresses the user's target intent; it does not prove native attackability
or authorize bypassing client restrictions. Preserve ordinary PvE and accepted
navigation/manual movement ownership. No selection/proximity inference of aggression.

## Sequence and completion criteria

1. COMPLETE — Consolidate current delivery status.
   Reconcile candidate receipts and focused live acceptance into the branch-map entry:
   installed 1.7.8 movement/chat baseline, verified but uninstalled 1.8.0 remapping,
   unfinished particles and doors, and identity work outside integration. Remove
   contradictory current/pending wording from active summaries while preserving
   historical evidence. Distinguish package checks, source review and live acceptance.
   Complete when a reader can identify the installed source and next work without
   reconstructing the incident history. Commit the focused documentation checkpoint.

2. COMPLETE — Integrate completed identity, party and pet observations.
   Review the behavior delta through identity branch 8552552 against the current
   integration source; preserve newer movement/lifecycle code and omit unrelated
   portal/renderer documentation changes. Validate exact keys, player/NPC classification,
   coherent party snapshots, positive pet-owner edges, dismissal and same-address reuse.
   Do not reinterpret absent ownership information as proven non-ownership. Wire needed
   observation channels through the existing runner, with passive evidence first.
   Run focused reader/controller tests and applicable checks; commit a coherent slice.

3. ACTIVE — Finish durable target identity and command behavior.
   Follow work package A below. Storage and chat routing exist; cross-login enemy
   rebinding and final user-facing labels remain incomplete. Do not mark this step
   complete merely because records survive a restart.

4. PENDING — Complete response ingestion, target protection and combat transitions.
   Follow work packages B through E in order of their actual dependencies. Source
   investigation may overlap, but maintain one active implementation checkpoint.

5. PENDING — Complete combined review, package checks and focused acceptance.
   Follow work package F. No install request or finished-feature claim before its
   developer-controlled gates pass. Keep the installed accepted baseline untouched.

## Detailed remaining implementation plan

The following is the execution specification for steps 3–5, replacing their earlier
high-level descriptions. Scope is an attack list integrated with existing PvE, not
unrestricted PvP strategy, new combat rotations, a new manager or a renderer overhaul.

### A. Durable identity and command completion — active

Outcome: an entry still identifies the intended enemy after logout/restart, while
another character at the old address or with an ambiguous display name never inherits it.

1. Trace existing native object keys and remote-character identity fields against the
   exact supported image. Distinguish durable character identity from object-instance
   identity. The local config name/server proof does not automatically prove remote
   identity, uniqueness, rename behavior or cross-login stability.
2. Record field provenance, layout, lifetime and invalidation rules in the existing
   client-observation evidence. Reuse exact keys, population and active-character
   readers. Avoid a parallel entity registry with conflicting ownership.
3. First use static source/image evidence and retained captures. If necessary, request
   a single bounded passive observation of the same known remote player before/after
   relog or unloading/reloading, with an independently identified second player as a
   negative control. Record image and process lifetimes. This is identity calibration,
   not a broad gameplay run or a request to install an incomplete feature.
4. Separate durable entry identity from the current runtime binding. The binding
   includes the current process/character/scene and observed object lifetime; discard
   it on identity change. Retain the saved entry until explicit removal. Unresolved
   entries remain visible but cannot select or attack a guessed replacement.
5. Upgrade the existing record schema transactionally, preserving revision and provenance.
   Existing session-scoped records must migrate as unresolved retained intent unless
   evidence explicitly establishes their durable identity. No silent deletion or
   automatic name-based conversion. Preserve a complete old or new file after failure.
6. Keep server/local-character ownership explicit. Document any native identity limits
   around character renames or same-name characters before choosing migration behavior.
   If a stable identifier cannot be obtained, report the specific evidence limitation
   and the resulting product decision; do not call session-only persistence complete.
7. Finish /blacklist add, remove, list and clear through the actual listener. Add uses
   the selected character; show a readable verified label and an unambiguous removal
   handle. Validate syntax before opening/scanning a client. Selection, local character,
   foreground and list revision must not silently change the command's intended subject.
   Expose unresolved bindings and party protection clearly in list/status output.
8. Preserve the existing commands and their private-chat handling. Test the actual
   listener callback during a blocked PvE operation, not just the parser. Confirm chat
   handling/command edits do not accidentally start an attack or route to another client.

Touched boundaries: pve/attack_list.py, pve/attack_list_commands.py, native identity/
population readers, existing chat/listener command routing and their tests. Dependency
injection belongs in the owning modules; do not extend CLI-wide namespace mutation.

Required evidence: cross-login/reload identity, recycled pointer/key, ambiguous name,
rename/unknown identity behavior, two local characters/servers, add/remove/list/clear,
missing selection, foreground change, concurrent updates, corrupt state and failed
publication. Exercise real spawned processes for shared-file races and crash/recovery.
Completion: durable identity and actual command routing are proven, with migrations
and unresolved-entry behavior documented. Commit and push this coherent slice.

### B. Attributed response events — pending

Outcome: a verified attack against the controlled character adds the actual attacker
through the same persistent store; the current selected target is never used as a proxy.

1. Inspect existing combat-log/HUD/event data and native callers for actor/victim keys,
   attack occurrence, ordering, timestamps and event lifetime. Current parsed messages
   contain names; do not claim they already supply exact attacker identity.
2. Reuse a verified exact identity join if available. Otherwise complete a narrowly
   scoped native event observation on the existing instrumentation boundary. No competing
   hooks or background-thread gameplay calls. Preserve original call-through, rollback,
   callback lifetime and bounded event buffering.
3. If live evidence is needed, use one known attacker and known victim while an unrelated
   character is selected. Observe attack, miss, periodic damage and environmental damage
   only as needed to distinguish native event types. No automated retaliation during
   calibration. An ambiguous/environmental/unattributed event records its reason and
   adds nobody. A miss counts only when verified as an attack attempt by that actor.
4. Normalize evidence with exact client/victim/attacker identity, source event ID/sequence,
   process/scene lifetime and observation time. Define stream restart, sequence reuse,
   overflow and maximum event age. Do not retroactively consume historical logs on start.
5. Deduplicate persistently within that source lifetime. Both manual and response entries
   stay until removed. Removal/clear must invalidate already queued old responses so
   replay cannot immediately recreate a deleted entry. A genuinely new verified attack
   after removal may add the attacker again; record this as new evidence.
6. Keep response capture and list editing independent of slow launch/dashboard work and
   use existing per-client ownership. A response may record intent while manual control
   is active, but cannot steal movement ownership or start automation automatically.

Tests: unrelated selection, two attackers, victim mismatch, duplicate/reordered/stale
messages, process/scene replacement, stream reconnect, overflow, clear/remove racing
publication, environmental damage and unknown actor. Test the real producer/consumer
boundary and serialized store transition. Complete only when real source evidence
reaches the store; a fabricated-event unit test alone does not finish response delivery.

### C. Resolve eligible listed targets and apply party protection — pending

Outcome: list membership supplies attack intent, subject to fresh identity, native
restrictions and the user's temporary party protection.

- Use one resolver over a coherent population/party/ownership frame plus list revision.
  Preserve the existing NPC PvE policy separately: adding players to that NPC-only
  strict gate would misrepresent its contract.
- Party membership temporarily prevents selecting/attacking a listed member without
  deleting the list entry. A member leaving becomes eligible only after a fresh,
  complete observation. Unknown party status withholds a new PvP attack rather than
  proving someone is outside the party.
- Preserve self, protected service NPC, and known friendly-pet protection. Do not infer
  that a pet's owner attacked merely because the pet attacked; attribution and any
  owner escalation are distinct. Default scope adds the observed attacker, with no
  owner escalation. Flag a genuine policy conflict before extending this behavior.
- Validate each candidate's current binding, life/health, supported kind, reachability
  and native restrictions. Peace-zone restriction is a rejection fact; its absence is
  not proof of universal attackability. Let the ordinary client/server action path
  decide native legality without field writes or bypasses.
- Carry list revision, identity evidence, party state and rejection reasons into the
  existing trace. Do not flatten unresolved/party-protected/out-of-range into one flag.
- A party join, removal, death, identity change or stop between evaluation and dispatch
  invalidates the decision. Revalidate at the actuation boundary; a previous successful
  check is not an action lease. Explain limits for an action already submitted to the
  native client and use the verified native stop path for subsequent activity.

Tests: listed party member joins/leaves, incomplete roster, pet owner appears/disappears,
self/service NPC, same-address reuse, list revision change and native restriction change
between evaluation and dispatch. Verify no unwanted selection/action is emitted.

### D. Verified player selection and attack dispatch — pending

Outcome: the intended player can be acquired and attacked through the current semantic
actuation architecture with the same exact-client and cancellation protections as PvE.

1. Check current committed actuation code as well as historical native-action documents.
   Distinguish transport support, verified native execution and the legacy desktop-input
   path; a document or semantic action name alone does not prove native execution.
2. Establish whether the existing acquisition action actually enumerates players. The
   current PvE path is calibrated for Target Next Mob. Do not assume it reaches players
   or substitute repeated screen clicks. Prefer the existing verified selection owner;
   coordinate shared selection/lifetime work with the movement owner without waiting
   for the complete door feature or creating another hook authority.
3. Verify the native action receiver, payload ownership, owning-client-thread boundary,
   selection notifications and reentrancy. After callbacks, revalidate the selected
   exact identity/scene and eligibility before attack dispatch. Do not assume same-thread
   execution excludes nested selection changes.
4. Admit commands through the existing exact process/window lifetime, owner generation,
   sequence/deadline and stop rules. Keep selection, action submission, native rejection
   and observed effect separate. Do not report submission as damage or a successful kill.
5. Implement native cancellation/stop for target invalidation and manual takeover. No
   post-stop queued command may regain ownership. Preserve camera-only input behavior.

Tests: wrong selection, callback changes selection, target disappears, stale generation,
expired deadline, rejected native action, queued command after stop, two clients and
startup/shutdown rollback. Use actual production adapters and authenticated private-image
checks where appropriate, followed by passive/plan-only integration before actuation.

### E. PvE-to-listed-enemy transition and recovery — pending

Proposed default behavior, to implement and document without inventing a new combat AI:

| Trigger | Behavior |
| --- | --- |
| Fresh verified attacker is eligible and listed | Prioritize that encounter over ordinary PvE acquisition while automation owns the session. |
| Listed enemy appears without attacking | Eligible during an explicitly running combat session, within existing pursuit limits; not an always-on attack service. |
| Multiple eligible enemies | Prefer current valid engagement to avoid thrashing; a newly verified direct attacker gets response priority, with stable deterministic tie-breaking. |
| PvE is already engaged | Cancel the old target/action/movement through existing ownership before acquiring the response target; never count cancellation as a kill. |
| Enemy dies, disappears, becomes protected, or exceeds pursuit limits | Stop the relevant engagement, retain list intent, and re-evaluate the current session. |
| Automatic encounter ends normally | Resume the active PvE session only after fresh safety/resource checks and no eligible higher-priority target. |
| Manual takeover, /stop, disconnect or invalid client lifetime | End automation ownership. Do not resume merely because controls are released or focus returns. |
| Explicit combat restart | Create a fresh operation/ownership generation; do not reuse pending old attacks. |

Preserve health/resource recovery, bounded pursuit, camp/zone restrictions and existing
kill evidence. Do not chase a listed player indefinitely or remove camp limits by default.
If the actual controller cannot express these transitions cleanly, refactor its touched
ownership boundary rather than layering a second controller that can issue competing input.

Tests must drive complete production runner transitions, including active PvE -> response
selection -> engagement -> recovery, manual interruption at each stage, removal/party join
mid-fight, target loss and concurrent client activity. Use controlled event fixtures and
barriers; retain reasons and ownership transitions in the existing trace.

### F. Candidate review, package verification and owner acceptance — pending

1. Declare scope: durable attack list, manual commands, attributed response additions,
   party protection, verified player selection/attack, and PvE interruption/recovery.
   Doors, particles, additional combat rotations and broad architecture cleanup are excluded.
2. Verify integration tests and all applicable existing Python/lint/native/PowerShell
   gates. Confirm required test names actually executed; skipped/missing gates are not
   passes. Include command presentation and multi-process store/dispatch tests.
3. Pin the complete clean source and obtain one independent focused review of identity,
   attribution, persistence/removal races, party protection, shared selection/lifecycle,
   command routing and interruption. Route fixes to the existing owner and revalidate
   affected gates; retain exact reviewed revisions. Do not reopen the whole repository.
4. Use the existing builder from the final clean commit with a new product/wheel identity
   as required. Keep product, wheel, ABI and wire versions explicit; change wire/schema
   only with a migration/compatibility decision. Rebuild after source changes.
5. Verify both native profiles, private-image bindings, installed wheel outside checkout,
   actual controls/commands, included assets/capabilities, hashes and source identity.
   Retain build logs, test outputs, review and package receipts. Earlier packages cannot
   certify these changes. No new release pipeline or shared VM replacement by implication.
6. Prepare one targeted first acceptance procedure after developer-controlled gates pass:
   a known selected enemy added/removed through chat; persistence after reconnect; a known
   attacker while another target is selected; temporary party protection; PvE interruption
   and recovery; /stop/manual takeover; and a second unaffected client. Confirm the expected
   visible behavior and capture only the specific diagnostic evidence needed for each.
   Reuse accepted zone navigation and movement/chat evidence unless touched behavior warrants
   a narrow non-regression. Separate optional failure-case observations from required checks.
7. Deliver source/base/included feature SHAs, scope, actual test results, DLL/wheel/package
   hashes, launch/configuration instructions and remaining live findings. No main merge,
   forced history rewrite or branch retirement is implied. Mark complete only after required
   connected checks pass; otherwise retain the exact candidate and specific open item.

## Execution cadence and blockers

Each work package ends with reviewed diff, relevant tests, a focused commit/push and an
updated status here. A source-only dependency may be integrated during development but
must remain identified as unfinished; do not ask the owner to accept it as the feature.

Start now with A's native durable-identity evidence. Investigate B/D using current code
and retained evidence when independent useful work is available. Request live input only
for a named missing fact, explaining the exact observation and why existing evidence
cannot settle it. No general VM reconnect exercise or broad repeated navigation testing.
An unresolved identity or attribution contract blocks combat activation, not unrelated
implementation or review. Do not weaken the agreed behavior merely to make gates green.

## Relevant review findings retained for future work

The supplied review assessed old source 310620b. Reproduce findings on current source;
its old candidate/visual status must not replace newer receipts or user acceptance.

- Release status vocabulary: keep package validity, runtime safety, declared feature
  completeness, installation readiness and connected acceptance distinct. Check current
  manifest/UI semantics before adding more status fields.
- Build-contract drift: assess duplicated CMake/package source and required-test lists.
  Consolidate only if a concrete maintenance gap warrants it, within the existing builder.
- Release-builder responsibility boundaries: a focused internal split may help later;
  no rename/new pipeline is a prerequisite for combat work.
- Movement transition properties: add targeted coverage for demonstrated gaps, preserving
  existing production-boundary tests rather than substituting a separate model.
- Branch reconciliation: preserve useful missing deltas by behavior; never wholesale-merge
  stale runtimes. Record retirement candidates; no bulk deletion or PR closure implied.
- Release destination protections and immutable candidate refs: inspect current hosting
  policy before recommending changes; do not claim the old protection finding is current.
- Feature availability and deferred transparency: keep controls and release scope truthful.
  Do not make completing particles or a unified mod framework a combat prerequisite.
- Version domains: maintain explicit product, wheel, ABI and wire identities. Change wire
  versions only with a compatibility decision.

Deferred items do not expand the active implementation scope. Exactly one step above
is active; update this plan and the user at each validated checkpoint.

## September 12 validated integration checkpoint

Steps 1 and 2 complete. Status cleanup 6c6aa42; selected identity/party/pet commits
9e343a4, ae7f885, 6ebeb81, 1954739, 4c5a925, 1a475f7, ab8f440; exact-client
party factory e496398. Live PvE launcher now supplies the same-process group reader
and passive authority channel with existing context-managed cleanup. No strict PvP
combat activation or package installation is implied.
Validation: full Python suite 1902 passed, 14 skipped, 249 subtests; Ruff src/tests
passed. Native sources unchanged by this identity slice; full candidate native,
package and independent integration review remain step 5 gates.
Current combat messages expose names, not attacker object keys. Response insertion
must resolve that evidence gap; current selection is not attribution. Next: storage
scope and chat commands using exact observed identities and honest persistence rules.
## September 12 attack-list implementation checkpoint

User confirmed both manual and response additions persist until removed, and party
membership temporarily prevents attacking a listed character without deleting intent.
Storage/chat source a8147f0 uses the existing interprocess record transaction. Commands
are /blacklist add (selected character), remove (selected character or listed entry ID),
list and clear. Commands bind the current foreground lifetime and native active character
on the listener processor rather than waiting behind an active PvE run. Storage is
per native server/character, and corrupt state is not silently replaced.

Full Python suite at a8147f0: 1917 passed,14 skipped,249 subtests; Ruff passed.
Multiprocess testing reproduced a shared record-lock first-creation race; initialization
now occurs under the byte-range lock, using unbuffered I/O. Focused storage, manager,
chat and CLI tests passed after repair. Exact-current-image active-character calibration
748d44c separately passed51 focused tests and Ruff after three existing native routine
fingerprints matched the current prepared image.

Step 3 remains active until durable target rebinding is established. Current saved
entries retain intent but their generated identity includes the observed process/local
character/target lifetime; no cross-login target equivalence is assumed. This is a source
dependency checkpoint, not a complete attack-list combat feature or an install request.
Remaining concrete evidence: exact remote-character identity across login, damage-event
attacker identity, and verified player acquisition (current PvE action cycles mobs).
Party protection must be applied in the final combat resolver; no combat consumption
of the list has been enabled. Steps4/5, full package gates and connected acceptance are
still pending. Do not certify this source with an earlier package receipt.
## Identity evidence migration checkpoint

Storage schema2 retains the observed image, process lifetime, local/target native keys
and character kind. Legacy entries stay unresolved rather than having identity inferred
from labels. A matching fresh observation may enrich evidence without replacing manual
provenance. This is historical evidence, not proof of cross-login identity or actuation
permission. Existing records migrate on the next successful mutation under the same
interprocess transaction. Focused store/identity/chat/CLI tests:94 passed,8 subtests;
Ruff passed. Private native tracing remains outside source control.

Step3/A remains active: determine the durable remote-character identity and verify it
across reconnect. A narrow two-character reconnect observation has been requested;
no attacks, package installation or broader gameplay acceptance is requested.


### September 12 identity checkpoint

A bounded read-only observation of the same owner-identified remote player before
and after reconnect retained its native key, exact name and server while its
allocation address changed. This evidence applies to prepared image
`bb63469eb35917e6b3f58be75d29f94855c9868024271222465b4db62f0e3a87`.
It does not establish global uniqueness, rename behavior or survival of a server reset.
Private captures remain outside the repository.

The selected-player reader now brackets bounded name/server reads with selected
object, vtable, key and local-character validation on that exact image. Schema 3
retains server-scoped player keys and exact names separately from historical process
evidence. Legacy entries remain unresolved; a matching key with a changed name
requires explicit resolution. No attack authority is inferred from a saved entry.
Malformed chat commands are rejected before opening a client.

Step 3 remains active: finish command feedback and current binding/protection before
calling identity integration complete. Next dependent work remains attributed
response ingestion, party protection and verified combat transitions. Buffs and
stance are combat-strength context, not identity or evidence of aggression.

Validation: full Python suite 1,933 passed, 15 skipped, 249 subtests passed; final
attack-list suite after adding schema-2 migration coverage: 28 passed. Ruff passed.
This is a source checkpoint, not a newly certified installed package.


### Command feedback and selection validation checkpoint

The existing listener now displays saved-player versus unresolved identity, removal
handles, and positive exact-key party protection. Missing party observations remain
explicitly unknown; a failed status read does not undo or conceal a successful edit.
These labels are informational and do not grant combat authority. Party members
remain on the saved list. Add/remove-selected re-read selection, local key and player
identity before mutation, rejecting changed subjects without writing the list.

Validation: full Python run 1,938 passed, 14 skipped, 249 subtests passed; final
attack-list suite 32 passed including changed-selection and unavailable-party cases.
Ruff passed. Source-only checkpoint; the installed client has not been replaced.
Step 3 remains active: current combat binding and listener concurrency validation
remain, followed by attributed response ingestion. Inspection of the existing combat
parser confirms hit/miss messages expose a name but no attacker native key; exact
attribution still needs verification before automatic additions can be activated.


### Listener concurrency and command transaction checkpoint

A barrier-controlled test drives the real listener callback while its PvE operation
is held, clears a real saved list, and cancels that operation before release. This
confirms existing command isolation; no duplicate listener dispatcher was introduced.

Commands now capture the list revision before target reads and compare it inside
the existing interprocess read/merge/write lock. A changed revision rejects add,
remove or clear without overwriting intervening work. A spawned two-process test
confirms exactly one writer can commit against the same revision. Independent adds
without a command precondition retain their existing merge behavior. Persistent
player records from another server are rejected on both write and load.

This is command concurrency protection, not response-stream deduplication: source
sequence/lifetime and removal invalidation for queued responses remain work package B.
Step 3 stays active; current-target combat binding and remaining identity evidence
must be completed before combat activation. No installed package was changed.

Validation: 38 focused attack-list tests passed; full Python suite 1,945 passed,
14 skipped, 249 subtests passed. Ruff src/tests and diff whitespace checks passed.
