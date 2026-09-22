# Guard crest lists and hostility workflow

Status: host response qualification, durable enable progress and native action
helpers are implemented. Command routing and the manager executor are unfinished;
no automatic hostility action is admitted. Continue on `codex/guard-upgrades`. Integration destination remains
`codex/vendor-rolling` → `codex/native-lifecycle-hardening` → reviewed `main`.

## Verified workflow

The user obtains a crest, saves it in Heraldry, and drags it into a building's
Enemies menu. A continuous window-identity capture recorded the map, Heraldry,
KOS and crest-options classes during that sequence. It finished at its configured
deadline with 8,077 successful window samples. The old recorder did not decode
crest entries, visibility or the drop arguments; this is not proof of an accepted
list mutation.

A later process lifetime retained one saved Heraldry entry. Its character,
guild and nation identities are separate typed keys. Guild and nation keys can
be equal while retaining separate roles. KOS and Antagonist windows
were also present, with no loaded entries and zero KOS context. Their visibility
was not established by the memory reader. This does not
mean the previously edited building's list is empty.

## Reviewed client mapping

The official client SHA-256 is
`a32275aabab8d5955f4d45adde6e84a666f44be54c951ccf8dc2d538237e8be4`.
The prepared client admitted by this reader is
`e277e5a4e1e4e1df048a32c07bdbac6fec0591c7d01588b984577251cf475891`.

Their complete `.rdata` sections match. Their complete `.text` sections differ
because the prepared client is patched; the compared crest range RVA `0x5ACD10`
(length `0x5700`) and thunk range RVA `0x1000` (length `0x29000`) match exactly.
Do not extend crest admission to older vendor builds merely because other vendor
observers admit those builds.

| Class | Vtable RVA | Purpose |
| --- | --- | --- |
| ArcHeraldryHud | 0x1168CA8 | Saved crests |
| ArcKOSHud | 0x1168E94 | Building condemn/allies list |
| ArcAntagonistHud | 0x1169080 | Related antagonist windows; kind distinguishes variants |
| ArcCrestOptionsHud | 0x1168AD4 | Individual/guild/nation choice |
| ArcHeraldryEntry | 0x11693EC | Typed list entry, kind 0x1D |
| ArcWorldMapHud | 0x1170BC8 | Map; no guild-directory decoder yet |

The shared drop dispatcher at RVA `0x5ADDE0` checks a recognized source control
and its owning HUD kind, then calls virtual offset `0x134`. The KOS override
at RVA `0x5AFEA0` obtains the selected Heraldry entry's three identity keys,
retains them at KOS `+0x3E0/+0x3E8/+0x3F0`, and opens crest options through
RVA `0x6CD970`. These are static control-flow findings, not live execution hits.
No native function was invoked by this investigation.

The options initializer references `BTNINDIVIDUAL`, `BTNGUILD`, `BTNNATION`
and their friend variants. Do not assume a crest drop selects nation scope or
that a nation entry necessarily covers subordinate guilds. The errant checkbox
is separately labeled for errant characters; it is not evidence of an
attack-everyone toggle. `BTNINVERTKOS` is not qualified for automation.

## Durable observation boundary

`native_crest_lists.py` exposes a read-only reader and the workflow recorder
has a separate `crests` channel. It observes:

- HUD class/kind and an uninterpreted +0xFC byte; visibility remains unverified;
- typed list rows through HUD/list/control ownership;
- separate character, guild and nation object keys, plus independent raw text fields;
- selected row membership, raw row keys and raw flags;
- KOS raw context and pending identities, and options-dialog raw flags.

Every read is checked again for consistency. Unsupported builds, broken ownership,
duplicate entry pointers, a selection outside its list and changing observations
reject the snapshot. Unknown HUD classes are not parsed. A loaded empty list is
not treated as an active empty building list, and no current asset-manager
building is substituted for an unbound KOS context. The reader cannot prove a server response, management
permission, town completeness or command admission.

Validation: 31 focused observer/recorder tests pass, including regression cases
for nation-only KOS rows and uninterpreted HUD flags. The corrected reader passed
against the loaded building KOS list described below. It still cannot establish
on-screen visibility or command admission.

## September 21 loaded Condemn row

The user reported an open Condemn list containing a crest. A new read confirmed
one KOS row whose character and guild keys were zero and whose nation key was
nonzero, type 23. Its raw flags were [0, 0, 1]. Its nation key matched the nation
key in the selected saved Heraldry crest; that source crest had a different
guild key. The KOS context was a nonzero type-8 building key matching the current
building management selection. This verifies a loaded nation-scoped row
associated with the selected building, not inheritance to all subordinate guilds
or an acknowledgement of an automated write.

The live case corrected two assumptions from the first checkpoint:

- KOS puts its displayed nation name in the first text field even when its
  character identity is zero. The reader now preserves text fields independently
  of the character/guild/nation identity keys.
- HUD +0xFC was 1 in the user-reported open windows. The reader no longer labels
  it hidden/visible or rejects values based on that interpretation. Earlier
  capture visibility labels are invalid; the raw flag is retained and
  visibility_verified is always false.

The KOS +0x104 owner was zero and the inspected asset-manager window slots did
not reference the KOS HUD. Matching the building keys must not be promoted into
a verified manager ownership link or permission to call the native handler.
The response-population override at RVA 0x5B1C80 and the loaded row support keeping
scope keys separate from text; request/response correlation remains unfinished.

The observer source was exercised directly in a bounded private diagnostic
recorder without modifying installed host/client files. No new product version
or native extension deployment is implied. Private captures, scripts, names and
object IDs remain outside Git.

## Root ownership and request/response mapping

The normal client resolves KOS through the root HUD registry, not the asset
manager's menu slots. Root virtual +0x80 dispatches to RVA 0x7A03E0, which refreshes
when root +0x138 is nonzero, then calls RVA 0x77EF80. In world state 2, that lookup
walks root +0x20, skips HUDs with nonzero +0x271, and returns the first matching
+0xDC kind. KOS kind is 0x39. A live read found one eligible KOS matching the
loaded building context and no pending root refresh. These flags are now retained
in the crest observer; they are not visibility or action-admission claims.

The asset manager's BTNKOS action 0x59D (RVA 0x6C7196) opens KilledOnSite through
the root and passes manager +0xF8 to RVA 0x5B11D0. That method stores the typed
building key at KOS +0x3D0 and queues ArcCoupMessage operation 0x0B to request
its list.

The crest-options handler RVA 0x6CB6A0 reads checked button state +0x393.
Individual, guild and nation map to scopes 2, 4 and 5 respectively. It resolves
KOS from the root and calls RVA 0x5B04E0 with scope and warrant mode. Ordinary
mode creates ArcCoupMessage operation 0x0E, sets building context +0xC0 from
KOS +0x3D0, and copies the selected pending identity into the corresponding
message field. Character uses +0x90, guild +0xA0 and nation +0x98. The native
builder can enqueue even when a pending key is invalid, so a future command must
validate the exact nonzero identity before entering it.

ArcCoupMessage response handler RVA 0x303F00 resolves a global KOS HUD for
operations 11 through 22. Success operations 12 and 13 populate rows through
virtual +0x128 (KOS override 0x5B1C80); operation 12 also clears the old list.
Operation 14 itself has no success-row append in the reviewed dispatch. Operation
13 is a candidate incremental-add response, not a live-qualified receipt yet.
The reviewed list-population path does not compare the response's building key
with the current KOS context. Therefore the job must allow one request at a time,
retain the response context and scope, and prevent a building switch while a
write is unresolved. Finding an already loaded row is not an acknowledgement.

No request builder or hostility toggle has been invoked. Nation inheritance,
errant/invert semantics and response correlation remain unqualified.

## Downloaded city crest catalog

The map idea is usable: ArcCityDataMessage response RVA 0x3EC5E0 populates a
city cache at RVA 0x16ABBF0 and refreshes WorldMap. This is distinct from
ArcRequestGuildListMessage/ArcSendGuildEntryMessage, whose reviewed paths route
to the guild-leader manager rather than establish a complete world directory.

The cache is a counted tree: header root/min/max at +4/+8/+0xC; node parent,
left and right at +4/+8/+0xC; typed key +0x10; retained ArcCityData pointer +0x18.
ArcCityData construction at RVA 0x8506F0 copies these fields:

| Record offset | Observed meaning |
| --- | --- |
| +0 / +0x28 | Typed city key / city name |
| +8 / +0x10 | Typed nation key / nation name |
| +0x88 / +0x90 | Typed guild key / guild name |
| +0x118 / +0x190 | Reviewed virtual-base table / class table |

The nation/guild roles were cross-checked against the selected saved Heraldry
crest, whose distinct guild and nation keys matched the same city's respective
fields. The nation also matched several other cities. Equal guild and nation
keys are retained in both roles; equality does not collapse scope.

`native_city_registry.py` now observes this cache and the workflow recorder has a
`city_registry` channel. It rejects broken parents, cycles, aliasing, wrong class
layouts, duplicate city identities, mismatched record keys, count/endpoint
mismatches and any changed read. It returns no partial catalog on failure and
never requests data or modifies the client. Zero crest keys are retained but do
not grant action permission.

Live qualification read 89 city records containing 88 distinct nonzero guild
keys and 49 distinct nonzero nation keys. These are counts from one private
snapshot, not stable configuration or a claim of complete guild coverage. The
cache can omit landless guilds and can outlive a particular map opening; its
freshness and completeness remain explicitly unverified. Private names, IDs and
captures are not published.

The exact official and prepared clients also matched these newly reviewed ranges:

| RVA | Length | SHA-256 |
| --- | --- | --- |
| 0x77EF80 | 0xE6 | 5fd74f9b327a3d74dcf7f83c6faff687c75b0c0a662939b508e30a1268f5c21f |
| 0x7A03E0 | 0x23 | 658fb0d4de1aabcd282fb34462f9ce350f62779328f2e866542d514ccd7fddc6 |
| 0x6C6B10 | 0x6E0 | d43a64d07e1f869fa30e01ef8a7804cbf04f5e62e6fee6260061689db22f41ef |
| 0x6CB6A0 | 0x700 | ae7181bdcc1f76f8cbcb78a36dc322ad3b3da0fdcd0a8962b179e167f8c1570d |
| 0x303F00 | 0xE80 | eb3b1934513c2473e45bda95f6c008d419cee91e52120b0d194cc7c1344765ac |
| 0x304DD0 | 0x730 | 6601cd40afd3dea18c0d78799efc91add3030f4c297cc13b524bb317c70fc2a8 |
| 0x3EC5E0 | 0x2C0 | 09e56612484b6d53663eed0a7fce9a5f837a60e3c132f08bdbd9dbedbe5a65e1 |
| 0x3EE0B0 | 0x80 | dcbe85e7357cd7af1365a406047fed2b7ceb78a9e550e2686e35c35339428f1b |
| 0x3EE620 | 0x80 | e2495e7306f8405cca1715d0dd854154e68137f6461f66a687c86bb788ed47d9 |
| 0x8506F0 | 0xE30 | 6e12d6727ef912df89b924255bb1cfe89d1ab022f92d38cac9f43c5b7b9a2568 |

Validation: 63 focused city/crest/recorder tests and Ruff pass. The city and crest
readers were exercised in the running test client without an installation or
native extension change. This checkpoint does not deploy a hostility command.

## Condemn response recorder source checkpoint

Native 1.8.23 / host 0.3.34 adds passive response evidence; it does not add a
hostility command. ArcCoupMessage slots +4, +0x14 and +0x1C observe destruction,
processing and deserialization, using the reviewed class at RVA 0x114F198.
The ordinary decoder return RVA 0x3625BC and active ArcLinkedSocket class are
required for receive records. Exact prepared executable and loaded-image checks
precede installation. Partial startup restores all slots; call-through code and
original targets stay pinned for late callbacks. Native returns, exceptions and
Windows error state retain their ordinary behavior.

The bounded shared ring retains decoded, processing and returned stages, building
and entry keys, serialized scope fields, and up to 512 typed rows. Fields absent
from a particular operation are zeroed instead of interpreting recycled message
storage. Row wrappers contain a CoupEntry pointer; its typed character/guild/nation
keys are at +0x30/+0x38/+0x40, flags at +0x48..+0x4A. The wire counter at message
+0xCC is separate from the decoded list length. Names and borrowed pointers are
not published. Destroy/redecode consumes old pointer tickets; matching copied
payload plus unchanged scene lifetime retains diagnostic decode lineage.
This does not prove network-queue freshness, request ownership or server acceptance.

The host reader binds to PID plus process creation time and validates the entire
retained ring twice. It reports initial history, overwritten records, rejected
payloads, lost tickets and closure. Counter regression prevents reattachment;
missing/unstable reads and losses mark the capture incomplete. It never promotes
returned handlers or preexisting rows into accepted writes.

Use the existing workflow recorder with `--condemn-responses` to retain these
events beside window, crest and map observations for a whole bounded session.
The native update is required for that optional channel. Source checks include 99 focused host tests and four native callback/rollback
tests. Exact-source package d300a7ca10067e4403677207080d61dd37092ffa passed
2,886 host tests, Ruff, both native profiles' required suites, reviewed client
bindings, movement IPC and installed host contracts. Eighteen conditional host
tests were skipped; the three client-dependent native bindings skipped by each
plain CTest run were separately exercised with the reviewed client. The two
previously documented graphics transparency stretch diagnostics remain deferred,
so this is a diagnostic package, not whole-product acceptance.

Native 1.8.23 / host 0.3.34 is installed and verified in the test VM after the
user closed Shadowbane. Four installed observer modules match the exact source
package. The manager restarted healthy; 8,503 saved files were verified unchanged,
and five replaced runtime/launch metadata files have rollback copies. The game
was launched by the user from the existing shortcut. Its exact-process heartbeat
confirms 1.8.23, and the response mapping validates. A bounded full-workflow
capture was recorded and stopped after the completed manual workflow. Two
rejected startup decodes predate that capture; their empty
payloads and incomplete-history status are retained, not treated as successful
responses. The manual nation add/enable/reopen sequence is qualified below.
Automatic hostility writes remain unfinished. Package SHA-256:
`7bfd54442468aaabe660891ce52ad8779fa2730b3991a0c2b6a62d4d4b211068`.
Full DLL SHA-256:
`6d48cc4c98f4dfb133e52bad9424f75e347c778a788be2764bac5ee2424751c2`.

Private build output is retained under `artifacts/guard-packages/5410c490` and
`artifacts/guard-deploy/1.8.23-d300a7c`; earlier failed package attempts remain
local with their failure logs. No client binary, private capture or credential
is published. The source lane still targets vendor-rolling, then
native-lifecycle-hardening, then reviewed main; it has not been merged.

The official, prepared and loaded current client match the following additional
response-lifecycle and row-layout ranges (private live receipt retained locally):

| RVA | Length | SHA-256 |
| --- | --- | --- |
| 0x303BB0 | 0x80 | 944f88bda267b63a628cabafa395bc6053a537fbad35bf7d5da3a6503f0d0e6a |
| 0x362500 | 0x180 | d5fdae8ba28b844223449ebea5a9354c469df234d7cd412c9b16ae85a0619ba8 |
| 0x7F7ED0 | 0x410 | cf71d27ad0f5b1485f88284ac65ea26047b75a0f8869ef4152d6921bd16dc614 |
| 0x5B1C80 | 0x4D0 | 5a3b2624cd40cc90544513a9a978c08990bc95974c539ab2e360ec5da6d64458 |
| 0x5B4330 | 0x50 | 8275863ad921e52a2d2fff74fe8f0427c2d97f2467818bc5c19d36c7e98f31ed |
| 0x5CF50 | 0x20 | c8bb8bd1d5516e7b730e78ca89f7084a5c2cd23d8d6645503a0ca4b73558de56 |

The previously listed 0x303F00 and 0x304DD0 ranges also matched the running client.

## Manual nation workflow qualified - September 21

The user added an existing saved nation crest to a different tower and reopened
that tower's Condemn list. Dragging from the map was not required. The map cache
remained readable with 89 city records; this does not establish a fresh download,
a complete guild directory, or map-to-list drag support.

The bounded recorder stopped on request and flushed its final record. All 4,067
samples of the response, crest, window and city-catalog channels were readable.
There were no missing response records or lost lineage tickets. Two rejected
decodes preceded capture; one additional unqualified three-stage response occurred
before the relevant list opened. Its payload remains unknown and is not silently
classified as unrelated or successful. Thus whole-workflow completeness remains
false even though the following four response triples validate individually:

| Step | Operation | Response content | Correlated loaded UI |
| --- | --- | --- | --- |
| Open new tower list | 12 | Empty rows, zero building key | Exact tower context, empty list |
| Add nation crest | 12 | One kind-5 nation row, state flags zero, zero building key | Same tower context, nation row appears |
| Enable row | 17 | Exact typed tower and entry keys, status 0, state 1 | Same row's nation flag changes from 0 to 1 |
| Close and reopen | 12 | Same nation row with nation flag 1, zero building key | Recreated row under the same tower context remains enabled |

Every qualified response retained decoded, processing and returned stages with
matching copied payload, scene epoch and local character identity; decode lineage
was preserved and timestamps were ordered. Private capture, keys, names and
qualification receipts remain outside Git.

This live add sequence returned operation 12, not the earlier candidate operation
13. In particular, a successful list refresh may carry a **zero building key**.
Never fill that missing field from whichever tower menu happens to be open or
promote the list into a building-specific acknowledgement. Operation 17 is the
observed keyed row-state reply. It has an entry key but no serialized scope field;
retain the separately verified row scope instead of guessing from scope zero.
This is manual state-response qualification, not proof of an automated request,
request nonce, nation inheritance, or observed guard combat.

### Ordinary native toggle path

Action 0x59E dispatches at RVA 0x7CC51F: resolve root HUD kind 0x39, then call
RVA 0x5B1640. The handler reads the selected entry at KOS +0x3B8, obtains its
character/guild/nation keys, and reads the corresponding flag at entry
+0x84/+0x85/+0x86. It creates operation 17 with selected entry key +0x88, current
KOS building +0xC0, and the **inverse** of that existing flag at message +0xC8.
It is a toggle, not an unconditional enable operation. Never replay it after an
uncertain submission or invoke it on an already enabled row.

Success dispatch for operation 17 reaches RVA 0x304835, which calls RVA 0x5B1340
with entry key and state. The setter finds the entry and writes the state to each
nonzero identity's associated flag, then refreshes KOS. It does not independently
compare the response building with the displayed tower. The manager must make
that comparison itself and keep the target context fixed while unresolved.
The ordinary Condemn description states that its list denies tradesman services
and causes guards to attack on sight; global inversion changes the list's meaning.
The captured list was not inverted. Errant and invert actions remain out of scope.

Official, prepared and loaded client bytes agree for these additional bindings:

| RVA | Length | SHA-256 |
| --- | --- | --- |
| 0x5B1340 | 0xE4 | 342f9c5ba532e6fbe5e5fc545f6596244305190f0ba0594809b07658d7ba3780 |
| 0x5B1640 | 0x1D8 | c48515ad5b45a94f241de5f4865a805fa11da116a1b1c12cd0d10b2a6cd2adaa |
| 0x7CC4BE | 0xCC | 814545fa8a12ff8850723e77d314b41c0fc9641299a44b0b513f2bea7e19fc70 |
| 0x7CDCEC | 0x149 | 7120623851fad91866febb2605cba24831e02bab108ccdee055069ed1b51c2ff |
| 0x5B0E8B | 0x68 | d4f0179348c6ffbe7b66f9610496d48a453df295c4287ba983e447c32038bafe |

### Consequences for the pending manager job

Keep scope-specific target identity and catalog provenance separate from names.
A list row is an observation used to locate the requested entry; the keyed state
reply and freshly verified row state are separate evidence. Submit on the native
owner thread only after rechecking exact tower, non-inverted list, selected row,
foreground, scene lifetime and desired current state. Permit one unresolved native
request, journal it before invocation, and prevent context switches or automatic
replay after ambiguity. A fresh enabled row may avoid a toggle; an unkeyed list
alone cannot clear an unresolved write. Equal guild/nation IDs must not silently
collapse scope or imply nation inheritance. Keep progress independent of guard
upgrade spending history and preserve completed targets while moving around town.

No product files were changed or redeployed for this qualification step. The
manager-owned hostility executor and its native commands remain unimplemented;
these results remove the manual response-mapping blocker, not the implementation.

## Next work

1. **Complete:** loaded Condemn row, separate crest scopes and corrected raw HUD flags.
2. **Complete:** static root ownership, scope selection, request construction and
   response dispatch mapping; read-only live city catalog and scope correlation.
3. **Active:** implement the manager-owned hostility job, including native response
   capture (implemented and live-qualified), one request in flight, exact
   building/scope state evidence and duplicate
   avoidance. Keep it independent of the guard spending job and existing resume history.
4. Qualify automated native actions end to end, nation/subguild coverage,
   and whether an additional source is needed for guilds without cities.

## Production response qualification - September 21

`client_extension/condemn_evidence.py` now assembles complete decode/process/return
triples within one explicit process, scene and character interval. Baseline history
is retained separately; it cannot complete new work. Gaps, new rejection/ticket-loss
counters, read interruptions, clock or scene changes, incomplete lineage and stream
rebind permanently invalidate that interval. Interleaved responses are bounded.
Immutable copied evidence preserves the response digest and all original stages.

The exact row-state predicate accepts only the keyed successful operation-17 enable
reply. Scope remains a separate checked UI-row fact. Unkeyed operation-12 lists,
labels, mixed identities, inversion and ambiguous duplicate rows do not qualify.
This is an evidence boundary, not command admission or proof of a request nonce.

Validation: 84 focused tests pass, including fault/replay/scope cases and existing
wire-reader tests; Ruff passes. Private offline replay of the captured manual
workflow qualifies the four expected triples and the reopened enabled row without
promoting either unkeyed list into an acknowledgement. No native action, manager
button, deployment or automated acceptance is implied. Next: durable progress and
native owner-thread action integration.


## Durable enable progress - September 21

`client_extension/condemn_progress.py` now owns a separate local Condemn journal.
It atomically retains a disabled scoped-row intent before invoking the native
adapter, accepts only matching typed submission ownership, and never replays a
request. A submitted attempt finishes only with a complete keyed enabled response
from its original healthy interval and a later enabled row in the same root/KOS
context. Confirmed targets are available by exact lifetime and retain guild/nation
scope. Guard spending and its history are unchanged.

The native adapter contract still requires owner-thread admission, producer/window
checks, UI serialization and a validated exact command receipt before constructing
`Submission`. No such adapter is connected yet; the journal is not an alternate
memory-write or command API. Its completed state is named `state_verified`, not a
claim that the server returned a unique request acknowledgement.

Write failures, lost submission replies, uncertain native outcomes, deleted or
corrupted records, host restarts and overlapping runners preserve the pending
barrier. Completed records revalidate their copied response and row evidence on
read. A separate read-error counter now exposes new read failures even when the
historical recorder state was already incomplete. Original window membership is
required; constructing equivalent-looking evidence cannot substitute another
window or qualify a response that the original window did not drain.

Validation: 178 response, journal, workflow, crest and city-catalog tests pass;
Ruff and the private manual-workflow replay pass. There is no deployment or live
automated acceptance from this source checkpoint. No additional user capture is
needed for this step. Current native/host installation remains 1.8.23 / 0.3.34.

Next active item: implement and connect native owner-thread open/add/enable actions
and their typed receipts, serialize their UI ownership with existing jobs, then
connect scoped catalog planning and manager controls to the progress journal.
Test the complete automated workflow together before requesting a live update.
Nation inheritance and guilds without cities remain separate coverage questions.


## Native action helpers - September 21

`native/wonderbane_extension/condemn_native.cpp` now implements owned-window
capture and ordinary open/add/enable call-through. This is the low-level action
implementation, not yet a registered command consumer or a live manager runner.
The owner-thread adapter must supply image verification, producer/deadline checks,
foreground and shared UI ownership; no command route currently calls these helpers.

Capture verifies the exact building manager/selection, root HUD chain, KOS class
and kind, list/row/entry ownership, complete bounded row membership, selected-row
membership and separately scoped identities. It rejects duplicate entry keys,
unknown refresh dispatch and ambiguous target identities. All effects require
fresh capture after admission; add/enable require the frontmost exact building's
non-inverted Condemn list. Existing enabled rows cannot reach the toggle.

Opening uses the verified owned BTNKOS control's ordinary callback. Adding uses
the native key assignment routine for only the requested guild or nation, clears
other pending scopes, checks the resulting snapshot, then invokes ordinary
scope-specific add with warrant mode off. Enabling uses the ordinary list selector
and KOS selected-row refresh, rechecking ownership between selection and refresh
and again before the toggle. A changed scene, context, row or enabled flag stops
before the request. Results distinguish no initial invocation, submitted call-through
and uncertainty; none constitutes a server acknowledgement. No automatic retry is
implemented in these helpers; the transaction owner must retain its journal barrier.

Additional reviewed bindings (official/prepared byte equality, not live invocation):

| Method | RVA | Length | SHA-256 |
| --- | --- | --- | --- |
| Typed-key assignment | 0x111BA0 | 0x14 | aa02eb1f9499959a511f461e4dfdae6d93e21d73233e623bb8fd6bcf85a899e0 |
| List selection | 0x613520 | 0x10 | ddb8877afd3295a95c8d8c36729ae7578482235bb95884c58317552fd94929ae |
| KOS selected-row refresh | 0x5B1C40 | 0x24 | f58b95837d9c97d7029301cfe7856b06eb93dad50e37dc3dd7975b4265aa3698 |

The KOS virtual refresh slot +0x12C must remain bound to thunk RVA 0x3B5C.
Previously reviewed add/toggle and building-open dispatch ranges match too.
Private disassembly and binding receipts remain in the designated artifact root.

Validation: full and diagnostics-only DLLs compile with warnings as errors. The
native helper fault suite passes in both profiles; the full-profile Condemn
response/rollback and adjacent guard-funding/navigation tests pass (seven tests).
251 host evidence, progress and package-gate tests and Ruff pass. Packaging now
requires the native Condemn helper test and exactly one owner for both native
Condemn sources; test fixtures cannot enter the runtime. No package was deployed,
no game methods were invoked, and installed versions remain 1.8.23 / 0.3.34.

Next active item: typed native command/receipt routing and one-in-flight transaction
ownership, including composite add/enable handling that does not treat an unkeyed
list refresh as add acknowledgement. Then connect scoped catalog planning, shared
UI ownership and manager controls; qualify the complete automated workflow together.


## Native response ownership boundary - September 21

The recorder now provides a locked, bounded process-local copy API. It never
exports its live view and rejects stopped capture, changed process lifetime,
new rejection/ticket loss, ring overrun, corrupt slots and future cursors.
`condemn_evidence.h` qualifies complete copied response triples in a non-rearmable
process/scene interval. It handles interleaving and split drains, requires ordered
lineage and matching bodies, and discards all completions from a damaged drain.
Historical counters remain in the baseline; old decodes cannot complete new work.
Only a successful exact-building/exact-entry operation-17 enabled reply qualifies
as keyed state evidence. This still requires separate owned scoped-row observation
and command ownership; neither an unkeyed list nor a response alone is authority.

Validation: five response/evidence/rollback tests pass in full and diagnostics
profiles; both DLLs build with warnings as errors. 258 focused host and package-gate
tests and Ruff pass. The evidence test is now a mandatory package gate. Source
only: installed 1.8.23 / 0.3.34 remains unchanged, and no game actions ran.

Next active item remains the typed native transaction controller and command route,
followed by composite host journaling, scoped catalog planning and manager controls.
No additional manual capture is required by this checkpoint.


## Composite native controller - September 21

Typed packed Condemn payloads reserve verbs 23 (inspect/continue) and 24 (ensure
one explicitly scoped crest is enabled). They serialize each snapshot field
explicitly and fit the existing 576/384-byte transport payloads. The controller
retains immutable submission receipts by UUID and owns one open/add/enable chain.
Only inspections naming the original transition, producer, window and scope can
advance it. An unresolved callback, timeout, lost evidence, changed scene/context
or incompatible row retains the barrier and never replays an action.

An add remains pending through an unkeyed list refresh. A freshly observed scoped
disabled row can proceed to one enable; completion requires a later keyed enabled
response and fresh enabled row in the original owned context. Preexisting enabled
rows are a separate read-only result. New responses arriving before dispatch defer
the action until drained. Replies alone never certify a request nonce or nation
inheritance. The controller is source-tested but not yet routed from IPC/runtime.

Validation: controller fault tests pass in full and diagnostic profiles; 150 package
gate tests and Ruff pass. The controller test is mandatory for packaging. No new
package, installation or live automated action occurred. Next active item: register
the queue/owner-thread route and share UI exclusion with vendor/guard jobs, then
connect composite host journaling, scoped plans and manager controls.


## Native command route and shared UI ownership - September 21

Verbs 23/24 now enter a dedicated typed queue through the existing authenticated
producer lease/deadline transport and execute on the admitted native owner thread.
The runtime drains its bounded response copy before capturing the scoped row;
active transactions continue observation each owner frame even without host polls.
Only an original-owner continuation inspection can initiate the next action.
Foreground, producer, deadline, lifetime and all competing transaction owners are
rechecked at native admission. Vendor crafting, city navigation, guard upgrades,
guard reopens and funding all respect Condemn's retained ownership barrier.

Captured snapshots now retain their own explicit building/identity/scope target.
An inspection for another scope arriving on a completion frame cannot relabel an
old nation observation as guild state. The receipt separately reports observation
and transition targets. Submission receipts stay immutable and duplicate original
commands never repeat a callback. Channel expiry only cancels a still-queued call,
not an executing native call. Pending deferral for the original UUID is transported
as a retained command receipt, not mistaken for a proven submission or completion.

Validation: both DLL profiles build with warnings as errors. All nine Condemn
native tests pass in both profiles. Six adjacent command-channel tests were rebuilt
and pass (15 full-profile tests total). The owner-service test runs the actual
runtime with simulated game calls and validates complete open/add/enable routing,
both directions of UI exclusion, response-before-row ordering, process-generation
changes, lost focus/lease, wrong-thread calls, scope handoff and duplicate commands.
278 focused host and package tests and Ruff pass. Queue/runtime tests are mandatory
package gates. This is source validation, not a packaged or live accepted release.

Installed native/host remains 1.8.23 / 0.3.34. The user's current in-world session
needed no further manual capture; no game actions, install or restart occurred.

Completed: native action helpers, bounded response qualification, composite native
ownership, typed IPC route and shared UI exclusion. Next active item: host wire
adapter and durable composite journal (the older enable-only journal cannot stand
in for a new add/enable transaction). Remaining: scoped catalog plans and manager
controls, exact-source package validation, then one combined live qualification.
Source remains on codex/guard-upgrades for integration through vendor-rolling and
native-lifecycle-hardening into reviewed main; no merge or PR is implied.


## Host wire contract - September 21

`condemn_wire.py` now matches the explicit native 20-byte target, 132-byte snapshot,
576-byte command and 384-byte receipt layouts. Immutable guild/nation targets,
owned snapshots and continuation UUIDs remain separate. Receipt validation checks
observation versus transition targets, phase/ownership flags, keyed completion
counters, unknown padding and signature. Already-enabled state is distinct from a
newly verified enable; pending and uncertain receipts cannot certify completion.

Validation: 66 wire tests cover native offsets, round trips, malformed payloads,
scopes, empty/expired observations and contradictory metadata. All 181 selected
wire/evidence/progress/response tests and Ruff pass. No host transport session is
connected to the wire yet; no new package or installation is implied.

Next active item: native host session plus durable composite journaling. An INSPECT
with a transition UUID can advance the native operation and is therefore not a
read-only/retryable inspection. Do not copy the existing session retry loop for
those continuations. Preserve the original producer/transition, journal before
ENSURE and before continuation dispatch, validate each exact receipt, retain lost
replies, and qualify completion against the original healthy response interval.
The latest action floor/tick may change from open to add to enable; the initial
submission is not necessarily the enable boundary. Then connect scoped plans and
manager controls before packaging and one combined live test.


## Host session and composite progress - September 22

The host now dispatches the typed Condemn commands through the existing producer
lease and validates command ID, producer generation, exact HWND, request UUID,
consumer thread, transport status and observation scope. Read-only inspect carries
no transition UUID. Action-capable continuations retain the original target,
producer and transition, use a fresh dispatch UUID, and never retry a lost reply.

The existing per-client Condemn journal now stores composite transactions under
schema 2; legacy enable-only records remain readable and share the same active
barrier. Intent is persisted before ENSURE and before every continuation. Phase
boundaries preserve the actual enable floor/tick and scoped disabled row. Completion
requires a keyed operation-17 reply consumed by the original healthy response
window and a later enabled row for that same entry. Existing enabled rows are a
separate result. Uncertain dispatches, storage failures, replaced producers/windows,
and restarts retain the pending intent and prohibit replay. Saved completion proof
is revalidated when loaded. No restart can take over an unfinished native chain.

Validation: 249 selected Condemn/transport/session tests pass; three existing
platform-specific transport tests are skipped. Ruff and diff checks pass. Tests
include write failure before/after dispatch, lost replies, changed scope/owner,
response loss, corrupted saved proof, restart retention and a complete simulated
open/add/enable flow through the actual session and journal. No new package,
installation, game action or live acceptance occurred; installed versions remain
native 1.8.23 / host 0.3.34.

Completed: typed native runtime and host session with durable composite progress.
Next active item: manager exact-building cycles and scoped catalog plans, followed
by durable manager controls, exact-source packaging and one combined live test.
The 89-record map catalog does not establish landless-guild coverage or nation
inheritance. Source still targets guard-upgrades -> vendor-rolling ->
native-lifecycle-hardening -> reviewed main; feature integration remains pending.


## Exact-building manager cycle - September 22

The manager now has a durable cycle for an ordered, explicitly scoped crest
selection on one building. It opens that exact building through the existing
navigation spending journal, waits for confirmed ownership, closes that producer,
and then runs the real Condemn session/journal. Every continuation checks the
original character and scene. The cycle records selected targets and request IDs
before native dispatch, distinguishes existing enabled rows from newly qualified
state, and refuses to repeat an existing operation ID. A requested pause finishes
the current crest before stopping between crests; lost dispatch authority stops
immediately with pending intent retained. No gold or guard upgrade is sent.

Saved Condemn uncertainty now blocks all existing manager UI runners under their
shared execution lock, including discovery, building navigation, vendor rolling
and guard funding. This host barrier remains effective after the client restarts.
Native exclusion continues to protect the live owner-thread interval as well.

Validation: 420 selected Condemn, manager, guard, vendor and transport tests pass;
three existing platform-specific tests are skipped. Ruff and diff checks pass.
Integration tests run the actual host session and both durable journals, covering
building-to-Condemn handoff, guild/nation separation, pause boundaries, wrong
scene/character, lost building/Condemn replies, response failures and cross-job
blocking. No new package, installation or game action occurred.

Next active item: scoped catalog/selection planning and the durable multi-building
job, then manager controls and packaging. The cycle is a production execution
boundary, not a live dashboard entry point yet. Current catalog completeness and
nation inheritance remain unverified. The existing 4,096-attempt journal/native
history and 512-row building bounds must be accounted for in admission; do not
silently truncate a requested town selection or claim all guilds were covered.


## Scoped selection and multi-building progress - September 22

Immutable preparations now retain the raw map catalog and process/scene-bound
nearby guard-building source. Selectors use typed keys, never names. Shared city
crests deduplicate within one role, while the same key in guild and nation roles
remains two targets. Missing keys do not become identities; conflicting labels
remain visible. Selections are pinned to a source digest, reject unobserved keys
and duplicate targets, and admit the entire requested workload against remaining
history capacity rather than truncating it. Cached coverage flags remain false.

A finite multi-building job now owns the selected order and each building-cycle
ID. Pause/Stop finish the current crest before retaining progress; a paused idle
job can stop without another worker dispatch. Resume counts only native-qualified
completion tied to exact saved cycle actions. Worker termination after native
completion, before either cycle/job receipt publication, can recover that proof
and proceed to remaining crests without replay. A missing cycle, lost native reply,
changed source/client/character, altered sealed evidence, or unproven crest leaves
the job for review. Each selected scope is independent and source digests are
rechecked; completed status never substitutes for receipt evidence.

Validation: 475 selected catalog, Condemn, guard and manager tests pass; Ruff and
diff checks pass. New integration tests use actual host sessions and journals for
two buildings and both scopes, including pause/resume, restart recovery across
both persistence gaps, missing/corrupt proof and retained uncertainty. This source
has not been installed or live-qualified. No game action was performed.

Completed: exact-building cycle, scoped selection and durable finite town job.
Next active item: worker preparation/admission and dashboard selection/buttons.
Then build one exact-source package and perform combined live qualification.
The current prepared source requires the same game lifetime/scene for resume;
expanding a selection into another area is not yet a supported Condemn control.
Guard Travel remains its separate existing workflow. Catalog freshness, landless
guild coverage, full town coverage and nation inheritance remain unverified.


## Dashboard and worker integration - September 22

The existing manager now exposes Condemn preparation, explicit crest/building
selection, start, pause, resume and stop. The selection dialog survives dashboard
polling and keeps guild/nation roles separate; its exact source digest and typed
keys cross the authenticated local route. An immutable selected request is saved
before the exact-worker operation is submitted. Worker capability/lifetime,
character, scene and competing jobs are checked again at execution. Guard and
vendor admission cannot take over an unfinished Condemn job between building cycles.

Preparation opens City Command through the existing discovered-building path and
brackets the cached map read with exact native scene observations and a calibrated
local-player key/character read. No manual crest dragging is required. The reader
still does not claim cache freshness or guilds absent from the map. Condemn area
expansion is not yet a control; the existing guard Travel workflow is unchanged.

Validation: 1,056 selected manager/Condemn/guard/vendor/identity tests pass, with one
existing platform-specific skip. The authenticated-route tests cover bounded
selection payloads, stale/busy workers, preserved selected requests, duplicate
start prevention and changed worker ownership. An isolated headless dashboard
check confirms guild/nation separation, preserved selections through a status
poll, one exact start payload and no script errors; its screenshot was inspected.
Ruff passes. Synthetic tests performed no actual game operations.

The combined candidate is versioned native 1.8.24 / host 0.3.35. Source packaging
now requires the full Condemn host/manager module set in the wheel. It is not yet
installed or live accepted. Installed remains native 1.8.23 / host 0.3.34.
Next active item: exact-source package validation, then stage/install once and
perform the combined live preparation/selected-building workflow qualification.
Only request a game close when the complete verified payload is ready to replace
its loaded extension. Integration remains guard-upgrades -> vendor-rolling ->
native-lifecycle-hardening -> reviewed main, with no PR or merge implied.


## Combined package validation - September 22

Exact source `0e3f058b16fd2666bcbddb581aed965936f8e717` is pushed on
`codex/guard-upgrades`, including the complete dashboard/worker workflow from
`f06ebcf`, consistent API release metadata, and the package source-path correction.
The native 1.8.24 / host 0.3.35 diagnostic package completed all required gates:
3,225 Python tests pass (18 platform/optional skips), Ruff passes, both native
profiles pass their required tests, and both profiles pass 63 movement IPC tests.
The three standalone native binding tests skipped without file arguments are
separately executed successfully against the reviewed client. Wheel installation,
entry point, panel, observer and contract checks pass. All 61 recorded artifacts
and the archive digest were verified before staging.

Archive SHA-256: `02c14c4967de9292956f14381decec3150c762be9c738c498771783aea44d5e4`.
Full DLL SHA-256: `39164dcd4ec534ef00e84ada46b8048adc8a82f531ed84b2ceb5874501159aa8`.
Wheel SHA-256: `da88ba216e6dc88a49d5c2593374669a5425b8cf1e73433200a81ab8fb7116de`.
The package remains diagnostic-only: the two previously deferred ideal graphics
transparency findings remain in each profile's diagnostic results. This package
record does not claim visual acceptance or live Condemn acceptance.

The complete payload is staged in the isolated test VM. Host 0.3.35 is installed
alongside the existing host; the existing-client dry run passed with exact
old/new identities, unchanged executable and no journal changes. Native
1.8.23 / host 0.3.34 remains the running installation. No game action, menu capture,
process restart or extension replacement has occurred. The prepared updater
checks exact old/new identities and retains rollback plus historical records.

Next active item: await the requested game closure and apply this one complete
update. The user launches the existing shortcut afterward;
combined live qualification still requires catalog preparation, selected building
and crest execution, native completion proof, and retained pause/resume progress.
Integration remains guard-upgrades -> vendor-rolling -> native-lifecycle-hardening
-> reviewed main; no PR or merge has been performed.


## Client patch and combined installation - September 22

The user's required official-client patch superseded the staged 1.8.24 package.
[Client 1.3.38.10](../client-update-20260922.md) is now installed with native
1.8.25 / host 0.3.36, exact package source `f534588`. It includes the complete
Condemn manager workflow plus narrow reviewed-build identities for the two-byte
version-only executable change. All required package checks and the VM migration
passed; 8,543 retained files match and the manager is healthy. The game was left
closed, with the existing Vendor Test shortcut ready for user login. The earlier
1.8.24 payload must not be applied. No Condemn action was performed during patching.
Next active todo: verify user login, then prepare the catalog and qualify the
selected-building native completion and retained pause/resume workflow live.



## September 22 — cold-login roster preparation

The first in-world preparation on 1.8.25 / host 0.3.36 read 91 cities and
141 scoped crest identities, but offered zero guard buildings. City Command
contained 65 nearby structures with empty cached hireling lists immediately
after login. Cached hirelings therefore cannot decide which buildings have guards.

Host 0.3.37 prepares the selection by visiting each nearby building once through
the existing correlated navigation channel and verifying its actual hireling
roster. It does not open individual guard upgrade menus. City Command releases
its producer before navigation begins; character and area checks bracket the
capture. Inaccessible or zero-slot structures retain partial coverage.

New schema-2 plans retain both the original cache and the verified roster evidence,
including typed identities, native snapshots, and durable navigation attempts.
Old schema-1 plans remain readable. No cached labels confer ownership or complete
town coverage. This is a host-only change; native 1.8.25 stays loaded. Source belongs
to `codex/guard-upgrades`, awaiting integration through `codex/vendor-rolling` and
`codex/native-lifecycle-hardening` into reviewed `main`. Next: install the verified
host and qualify automatic preparation, then one selected building/crest transaction.

Validation: 3,248 host tests passed, 12 skipped; Ruff passed. The final evidence-check refinement also passed all 104 focused preparation/navigation tests. Native code is unchanged.


Host 0.3.37 is installed without restarting the game. Live preparation verified
35 building rosters and 168 guards across 28 selectable towers from 65 nearby
structures. Partial coverage remains explicit. The selected Wankers nation / one
tower start then exposed a missing `selection` argument on the production live
configuration facade; no request, job, cycle, or hostility write was admitted.
Host 0.3.38 forwards that field and includes an HTTP-to-live-facade-to-control-to-
worker regression test. Existing verified preparation is retained for the next
live qualification; native 1.8.25 remains unchanged.


## September 22 - installed host and live single-tower result

Host 0.3.38 source `4b0253b` is installed and its 430 packaged files verified.
The dashboard shortcut and launcher use that host. Native 1.8.25 and the same
in-world game process remain loaded. The facade correction passed 61 related
HTTP, configuration, manager, and Condemn tests; Ruff passed.

One selected nation crest was submitted on one freshly verified six-guard tower.
Native building navigation, list opening, and adding the scoped row succeeded.
The response stream retained two complete operation-12 triples: empty list and
added nation row with its state disabled. Row selection succeeded, and the native
toggle handler returned, but no operation-17 reply arrived. The row remained
disabled through the 45-second deadline. No response records or lineage tickets
were dropped or rejected. The transaction and job correctly retain uncertainty;
no toggle retry, journal reset, or larger run was sent. This is not enable or
aggression acceptance.

A read-only close/reopen observation was requested to distinguish persisted server
state from the current loaded row. The existing full-workflow recorder is armed
for that observation with a ten-minute bound. Next: inspect the fresh list and
resolve the enable boundary; retain the unresolved native and host journals.
Pause/resume qualification, wider crest application, and outer-town coverage
remain pending. No further client reinstall is currently prepared or requested.

## September 22 - manual enable comparison and callback ABI correction

The reopened server list confirmed the automatically added nation row was disabled.
The user then checked that row once and reopened the list. Operation 17 confirmed
state 1 for the exact building and entry; the next operation-12 list retained the
enabled nation flag. This qualifies manual permission and persistence only. The
earlier automatic request remains uncertain, with its original journals retained.
The bounded read-only recorder ended normally and its private capture is archived.

Review of client 1.3.38.10 found that the selected-row callback at RVA 0x5B1C40
ends with `ret 4`. Our wrapper omitted the unused event argument. Native 1.8.26
passes that argument explicitly; the ABI-faithful regression stub reproduces the
old failure and passes with the correction. Neighboring open, select, assign, add,
and enable call signatures were checked against the same reviewed executable.
All nine focused native Condemn tests pass. Host 0.3.39 packages the current host
with the corrected extension. Full exact-source package validation and staging
are next; the running game remains 1.8.25 / host 0.3.38 until installation.

This is a verified calling-convention defect, not yet a live-qualified fix for
automatic enable. After installation and a new game lifetime, qualify automatic
enable and fresh-list persistence, then pause/resume, before a wider selected run.
No uncertain action will be replayed or relabeled as automatically completed.
Source remains on `codex/guard-upgrades`, for integration through
`codex/vendor-rolling` and `codex/native-lifecycle-hardening` into reviewed `main`.

## September 22 - callback correction package staged

Native 1.8.26 / host 0.3.39, exact source `cb30014077299347971ef376f98552ecc7a3093f`,
is staged and read-only validated in the test VM. It contains callback fix
`1debb06` and the matching API version correction. The installed game and active
manager are still 1.8.25 / 0.3.38; game closure has been requested before replacing
the loaded extension. No automatic enable success is claimed yet.

The exact-source package passed 3,242 host tests (19 skipped), Ruff, all required
native gates in both profiles, 63 IPC tests per profile, reviewed-client bindings,
and installed-wheel checks. Each profile's native suite has 172 cases: 169 passed
and three file-dependent cases skipped there and checked separately with the
reviewed client. The two known graphics transparency stretch failures per profile
remain recorded diagnostic limitations, outside the required Condemn gates.

All 61 package artifacts were hash-verified. Guest preparation verified 430 host
module files and inventories 8,613 retained records/settings. Installation changes
one client inventory entry, the extension DLL; the prepared 1.3.38.10 executable
is unchanged. The earlier uncertain transaction is retained without replay.
Next: apply after game closure, verify the loaded extension, then qualify automatic
enable/persistence and pause/resume before wider town application. The branch
remains unmerged, with the integration destination documented above.

## September 22 - callback correction installed and launched

After the user closed Shadowbane, native 1.8.26 / host 0.3.39 from `cb30014`
was installed in the test VM. The detached idle manager was stopped; the installer
verified the replacement DLL and entire client inventory, retained all 8,613 saved
records/settings, and kept a verified rollback copy. The existing dashboard
shortcut now starts host 0.3.39. Manager activation passed and the same Vendor Test
launcher started a new game lifetime with the exact expected extension hash.
The 1.3.38.10 executable remains unchanged. Private receipts are archived.

Login into town has been requested. Automatic enable/persistence and pause/resume
remain unqualified; the earlier uncertain attempt is preserved as historical
evidence and is not retried. Next: fresh in-world preparation and one selected
crest transaction on a verified tower, observing both server response and row
state before widening the run. Integration into reviewed main is still pending.

## September 22 - live Condemn qualification passed

The installed callback correction passed automatic nation-row enabling: the
server response and checked row confirmed completion. A multi-tower job paused
at a confirmed boundary and resumed to completion without changing or repeating
previously completed requests. Revisiting the first tower fetched an enabled
server list and recognized the existing state without another toggle.

Private captures and exact transaction receipts remain outside the repository.
The earlier uncertain attempt is preserved separately. The wider run will exclude
the user's own guild and nation; the exact friendly identity still needs
confirmation because city ownership does not establish character membership.
Next: confirm that identity and run the saved finite selection. Full-town and
landless-guild coverage, nation inheritance, and guard combat remain unverified.

## September 22 - nation-only rollout and bounded observation correction

The user selected whole-nation exceptions and clarified that individual-player
exceptions and a separate guild pass are unwanted. The saved rollout selection
contains only nation targets and omits all three friendly nations.

The run stopped for review on an interrupted host response observation after a
completed tower and additional confirmed rows on the next. The pending intent and
all prior proof remain preserved; no action was retried. A subsequent read parsed
the settled response stream successfully without native rejection or ticket loss.
The original diagnostic retained only the exception class, so the exact failing
copy cannot be reconstructed.

Host 0.3.40 bounds snapshot stabilization to three read-only pairs and recognizes
the native ring-wrap publication window before accepting a cursor. Identity,
record validation, lost-history reporting, and counter-regression barriers remain
strict. Persistent instability and malformed payloads still stop the job. Session
errors now retain the underlying diagnostic. Tests cover changing copies, ring
wrap, bounded failure, lost records, and stable corruption. Validation: 3,255 host
tests passed, 12 skipped; Ruff passed. Native code is unchanged.

Next: stage and verify the host-only update. The existing uncertain transaction
remains blocked; a fresh game lifetime and fresh list observations are required
before continuing the desired nation states without blind replay.


## September 22 - host observation fix activated

Host 0.3.40 from `fd49969` is installed and running. All 430 packaged host files
passed identity checks. Activation preserved all 8,760 durable worker files;
the only changed existing file was the temporary dispatch permit, which correctly
denied dispatch while no game was bound. The dashboard shortcut now uses the new
host. The same Vendor Test launcher started a fresh game lifetime with the
unchanged native 1.8.26 extension and reviewed client executable.

The stopped attempt remains retained in its original lifetime. Login is requested;
next is fresh town preparation and a nation-only selection excluding all three
approved friendly nations. Existing enabled rows must be recognized from fresh
server lists without another toggle. No wider rollout completion is claimed.
The branch remains outside reviewed main; integration follows the guard lane
through vendor-rolling and native-lifecycle-hardening.


## September 22 - lease maintenance across durable progress work

The host 0.3.40 nation-only run recognized previously enabled rows and advanced
through three complete towers plus confirmed rows on the fourth. It then stopped
with an expired native producer lease and no pending Condemn intent. All completed
proof remains saved; no uncertain action was retried.

Host 0.3.41 renews the Condemn session's existing lease independently of journal
validation and atomic saves. The maintenance thread never submits a game action,
cannot reacquire an expired or replaced lease, latches failures before further
dispatch, and joins before transport shutdown. The normal Resume action now
admits the specific idle lease-expiry stop only after all saved cycle actions
match durable native completion and both action journals are idle. Other review
errors, missing proof, unfinished intents and changed ownership remain blocked.

Validation: 3,264 host tests passed, 12 skipped; Ruff passed. Regression cases
cover slow writes, failed renewal, shutdown ordering, proof-checked continuation,
no repetition of completed requests, and normal manager routing. Native code is
unchanged. Next: verify an exact-source host-only package, validate the stopped
job on a private copy, and restart only the idle manager/worker before continuing
the same selection. Full-town coverage and rollout completion remain open.


## September 22 - lease fix installed and same-job continuation verified

Host 0.3.41 source `ec63ea1` is installed, with all 430 host module identities
verified. Recovery against a private copy of the stopped job retained all 163
confirmed actions and selected only the remaining 1,181. The original journals
were unchanged. Only manager/worker processes restarted; the same game lifetime
and native extension remained running.

The existing job resumed through the normal manager control. Its first 163
completion records remain identical; four towers are now complete and the fifth
is progressing. All targets remain nation-scoped and omit the three approved
friendly nations. No guild or player pass is enabled. The dashboard shortcut
uses the new host. Private installation, recovery and live proof remain outside
Git.

Next: finish the 28-tower selection and review further town coverage. The active
batch is still running; full rollout completion, nation inheritance and guard
combat are not claimed. Integration remains guard-upgrades through vendor-rolling
and native-lifecycle-hardening into reviewed main.


## September 22 - growing-journal workload and retained lease timing

The 0.3.41 run subsequently stopped after six sealed towers and 40 confirmed
rows on the seventh. It retains 328 completed attempts and one submitted
transaction in its original lifetime. Unlike the earlier idle boundary, that
pending transaction cannot use Resume recovery or be adopted by another session.
No request has been replayed or journal cleared.

Private isolated probes reproduced substantial renewal delays during repeated
whole-journal validation. A comparison of memory-access primitives did not improve
timing, so transport ordering and the one-second native lease limit are unchanged.
Host 0.3.42 instead reuses validation only for identical canonical bytes of fully
validated terminal attempts. Every read still loads fresh storage and validates
the journal envelope, request uniqueness, schema and active-intent consistency.
New, changed and pending records are fully checked; returned objects are never
cached. The immutable validation set is bounded by the existing journal limits
and pruned to the current validated snapshot.

The current-size isolated workload's maximum renewal gap dropped from 531 ms to
266 ms in the observed comparison. A synthetic 1,344-completion workload completed
20 rounds without expiry, with a maximum renewal gap of 422 ms. These are isolated
performance observations, not proof of the exact earlier scheduling stall or live
rollout completion. Future expiry diagnostics retain heartbeat age and renewal
wait time without changing the admission deadline.

Validation: 3,274 host tests passed, 12 skipped; Ruff passed. Tests cover fresh
reads, changed completion proof, duplicate requests, missing journals, invalid
schema/owner/active state, pending-record revalidation, bounded cache lifecycle,
and unchanged heartbeat values after expiry. Next: stage the exact-source
host-only update, then obtain a fresh game lifetime for the preserved pending
transaction and recheck the selected nation states. Full-town coverage remains
unverified.


Host 0.3.42 source 8cca2d9 is now staged and installed alongside the active
host, with all 430 module hashes verified. It is not activated yet. The game
closure request is pending so the retained in-flight transaction remains attached
to its original lifetime; the manager can stay open until the controlled switch.
The existing native extension and client executable do not need replacement.


## September 22 - journal scaling update activated

After confirmed game closure, host 0.3.42 source 8cca2d9 was activated and the
dashboard shortcut updated. All 430 host module hashes and 8,880 unchanged durable
worker files were verified; the temporary unbound dispatch permit was correctly
refreshed. The same Vendor Test launcher started a fresh game lifetime with the
unchanged reviewed native extension and client executable. The manager is healthy.

Login into town is requested. Next: fresh preparation and the nation-only
selection, recognizing existing enabled rows from fresh server lists. Earlier
uncertain transactions remain preserved in their original lifetimes. No rollout
completion or additional town coverage is claimed. Integration remains pending
through the documented guard, vendor and native-lifecycle branches.


## September 22 - bounded recovery from unexecuted queue expiry

Town login and preparation succeeded on host 0.3.42. The 48-nation, 28-tower
selection confirmed 139 already-enabled entries before an initial Ensure expired
in the native queue. Its correlated STALE receipt is empty, idle and carries no
controller or transition state: command_channel.h atomically cancelled the queued
request before the game owner thread took it. Both durable journals are idle.
This differs from an uncertain or already-submitted action.

Host 0.3.43 recognizes only that exact validated initial-receipt shape. Each
rejection ends and seals its building cycle without counting the crest complete.
The job reopens/observes the remaining target under a new request identity;
completed crests and the original rejection remain unchanged. Three queue
expiries on one target stop for review, with the limit derived from durable cycle
history so restart/resume cannot reset it. Nonempty STALE, availability, invalid,
exhausted, missing and uncertain receipts are not eligible. Pending journals still
block all recovery. The existing Resume admission can recover the older manager's
stop at this proven boundary; the dashboard exposes that admission for review.

Validation: 3,284 full-suite tests passed (12 skipped), plus the subsequently
added manager admission case in an 18-test focused pass; Ruff passed.

Next: activate the manager-only update, preserve the current game
lifetime and continue the same nation-only selection. House of Shinobi,
Celestials and BIB remain excluded as whole nations. No full-town coverage,
nation inheritance or guard combat acceptance is claimed. Integration remains
through vendor-rolling and native-lifecycle-hardening into reviewed main.


Host 0.3.43 source ca983d7 is now installed and active in the same game lifetime.
All 430 module hashes passed. Private-copy recovery retained all 140 original
attempts and recovered exactly 139 completed targets. During activation, 8,885
saved files remained unchanged; five capability records, the launch reservation
and dispatch permit refreshed for the verified replacement worker. No action,
job or earlier-lifetime proof was changed. The existing dashboard shortcut now
uses the updated host. The normal Resume action continued the same saved job;
live observation confirms it passed the former stop, with 160 enabled targets
confirmed and the original 140 attempt records unchanged. The batch is running.
Next: finish this selected batch and review additional town coverage.


## September 22 - confirmation queue expiry retains its original action

The host 0.3.43 batch reached 894 confirmed nation entries (18 full towers and
30 entries on the next), comprising 280 existing enabled rows and 614 newly
verified enables. It then stopped with the original action still pending.
Read-only captures show the second continuation was atomically cancelled by the
native queue before the owner thread took it: an empty correlated STALE receipt.
The earlier continuation had already invoked Enable. The former host treated
that empty confirmation receipt as an owner mismatch, preserving its write-ahead
intent and stopping. This active transaction has not been replayed or reset.

Host 0.3.44 retains these exact cancelled continuation receipts separately from
owner/phase evidence in the existing native attempt. The original live host,
producer lease, response interval, transition identity and completed phase remain
required. Only a fresh continuation UUID can follow; the original Ensure and
native phase action are not repeated. A cancelled poll is neither completion
proof nor an idle transaction. Three cancellations on one composite stop further
continuation while preserving the active barrier. Lost, contradictory or nonempty
receipts, failed receipt writes and replacement sessions still block continuation.
Legacy attempts keep their existing bytes; cancellation evidence is added only
when an exact queue cancellation occurs and is checked on every fresh read.

Validation: 3,301 host tests passed, 12 skipped; Ruff passed. The end-to-end
job test confirms a cancelled enabling-phase poll can finish under its original
owner, with all original phase and response proof retained.

The current stopped host already released its original session, so this update
cannot adopt its unfinished transaction. Next: validate and stage the host-only
update, obtain a fresh game lifetime, then freshly observe existing enabled rows
and finish the same approved nation selection. The three friendly nations remain
excluded; no individual or guild pass is authorized. Integration remains through
the documented feature lanes into reviewed main.


## September 22 - confirmation-expiry update activated

After confirmed game closure, host 0.3.44 source 2432777 was activated in the
test VM. All 430 installed module hashes passed. All 8,928 retained worker files
were unchanged; only the temporary dispatch permit refreshed while no client was
bound. The dashboard shortcut now uses the updated host. The same reviewed
client relaunched into a fresh process with the unchanged native 1.8.26 extension
verified as loaded. The manager is healthy and its new worker was started through
the normal Resume action. No fresh Condemn job has been submitted.

Next: Poley logs into City of Temple, then fresh preparation and the approved
nation-only selection can continue. The 894 confirmed entries and unfinished
transaction in the prior game lifetime remain preserved. House of Shinobi,
Celestials and BIB stay excluded as whole nations. Full selected-batch completion
and wider town coverage remain open. Source integration is still pending through
vendor-rolling and native-lifecycle-hardening into reviewed main.


Town login is confirmed. Fresh preparation observed 141 scoped crests and 29
accessible guard buildings; the same 48 nations were selected, excluding the
three friendly nations by their whole-nation identities. The new finite batch
contains 1,392 targets. Two buildings are newly observed and one from the prior
28-building view is no longer loaded, so this is not a complete town census.
The batch is running: six towers are sealed, 288 existing entries and 27 newly
verified entries are confirmed. The prior lifetime's records remain untouched.
Next: finish the selected batch, then review the coverage difference.


## September 22 - dispatch renewal under growing summary load

Host 0.3.44 reached 1,299 native confirmations: 895 already enabled and 404 newly
verified. Twenty-seven towers are sealed (1,296 targets), with three further
confirmations in the active tower. The next Add remains submitted and retained;
no continuation poll was pending. The operation stopped because its manager
permit expired by 0.196 seconds. No cancelled poll occurred in this run.
Do not resume, reset or adopt the released transaction. Earlier uncertain
lifetimes remain unchanged.

A bounded, read-only eight-status-call probe against the stopped job measured
3.234–4.032 second status reads and a maximum permit issuance gap of 2.088
seconds, exceeding its unchanged two-second validity. Each dashboard summary
constructed fresh proof stores, discarding the existing completed-proof cache.
Host 0.3.45 retains an exact-instance job/proof store per client, drops changed
or unbound instances and limits inactive slots to the manager's 32-client bound.
It caches only canonical validated terminal proof; every summary still reads
fresh job, cycle and native records. Changed and pending proofs remain validated.

Supervision now starts on a 250ms monotonic cadence, charging inspection time to
the interval instead of adding 750ms after every check. Slow checks never reuse
stale observations for catch-up renewals. Permit TTL, identity checks, shutdown
revocation and uncertain-action barriers are unchanged.

Next: complete validation, package exact source, then compare the same stopped
job's dashboard latency and permit gaps in the VM before requesting a new game
lifetime. House of Shinobi, Celestials and BIB remain whole-nation exclusions.
Full batch completion, broader town coverage and source integration through
vendor-rolling/native-lifecycle-hardening into reviewed main remain unfinished.

Validation: 3,308 host tests passed, 12 skipped; Ruff and diff checks passed.
Regression coverage includes changed proof/job/cycle rejection after warming the
cache, fresh summary results, lifetime eviction, the slot bound, slow supervision
checks and exception propagation to shutdown revocation.


### Host 0.3.45 installed and stopped-job timing compared

Exact source 90faae014046fd8bac6c21ad7b05b3793e6c4e7b was packaged from the
clean pushed feature branch. Wheel SHA-256:
`c6122988ec8d5f29599fd40a86701803c504b94dde9ee46331374d65ed92db95`.
All 430 installed module hashes passed. The manager was switched through normal
dispatch Pause while the game stayed open and the Condemn job remained in review.
Of 9,072 prior worker files, 9,064 are unchanged; the eight changed files are the
launch reservation, dispatch permit, replaced worker heartbeat and five exact
worker capability records. Saved jobs, receipts and pending native intent did
not change. The existing dashboard shortcut now points to host 0.3.45.

The identical bounded eight-refresh probe measured 1.547–2.469s dashboard reads
and a maximum permit issuance gap of 0.287s (previously 2.088s). The probe's plain
file observer saw one transient PermissionError during atomic replacement;
production read/retry behavior was unchanged. This qualifies renewal timing for
this stopped-job workload, not every future load or full selected-batch success.
The two-second permit lifetime and native one-second lease remain unchanged.

Twenty-seven towers already have sealed proofs covering 1,296 targets. The two
unfinished towers contain the remaining 96 selected targets, including three
already confirmed entries that can be freshly observed. After the requested game
restart, prepare fresh observations and select only these two remaining towers;
do not repeat the 27 completed towers or adopt the retained old transaction.
The exact private identities and source proof remain in the local deployment
handoff. The three friendly nations stay excluded. Next: user game closure,
relaunch/login, finish the two-tower selection, then review broader coverage.

The user confirmed closure. The same reviewed client has now relaunched in a
fresh game lifetime with the unchanged native extension verified. The manager
recognizes it with no Condemn job or active operation; normal Resume starts its
new worker. Next: Poley login, then fresh preparation for only the two remaining
towers. No old transaction was adopted or replayed.


## September 22 - remaining towers completed; observed coverage audited

Poley's fresh session prepared 140 scoped crests and 29 accessible towers. The
48-nation preflight stopped before submission: the current catalog no longer
lists Legacy as a nation. Its same city, Light of Saedron, is now attributed to
BIB, while Legacy remains a guild. The unchanged whole-nation exclusion policy
therefore selected 47 current nations. No Legacy guild entry was added, no new
exception was inferred, and no old transaction was adopted.

The one submitted batch covered only the two unfinished towers: all 94 targets
completed, comprising 91 newly verified entries and three already enabled rows.
Both building cycles are sealed; the worker is healthy, with no active operation
or pending request in this game lifetime. No queue-expiry recovery was needed.
The earlier interrupted Add and all earlier completion proofs remain unchanged.

The final read-only audit verified the new 94 targets against the prior 27
sealed towers. Filtering the previous selection to today's 47 target nations
produces 1,363 verified entries across 29 towers. The prior run also has a sealed
proof for the one tower now outside view, raising observed coverage to 30 towers
and 1,410 current-nation entries. Previously stored Legacy nation entries remain
historical records; they were not converted into guild entries or silently erased.
This is not a full-city census or proof of guard combat/nation inheritance.

All 9,064 retained job/proof records checked before host activation still match.
The same eight runtime-authority files changed during the already recorded host
switch. A bounded eight-refresh probe during actual updates measured dashboard
reads of 0.469–0.984s and maximum permit issuance gap 0.404s, with no probe read
errors. Host 0.3.45 source 90faae0 remains installed; no code or package changed
in this completion step. Private selection, job/progress snapshots and the final
audit remain in the local deployment evidence directory.

Next: Poley moves to an outer-town group, then fresh discovery selects only newly
observed towers. The 30 completed towers should not be reiterated. Full-town
coverage and nation-inheritance/combat qualification remain open. Source is still
on codex/guard-upgrades for review through vendor-rolling and
native-lifecycle-hardening into main; no merge is implied.
