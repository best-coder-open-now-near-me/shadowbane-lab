# Guard crest lists and hostility workflow

Status: investigation and read-only observation; no hostility command is implemented
or admitted. Continue on `codex/guard-upgrades`. Integration destination remains
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
The native update is required for that optional channel. Current source checks:
99 focused host tests, Ruff, four native callback/rollback tests, and full DLL
compilation pass. Exact committed package validation, installation and live reply
qualification are still pending; no deployment or gameplay effect is claimed.

## Next work

1. **Complete:** loaded Condemn row, separate crest scopes and corrected raw HUD flags.
2. **Complete:** static root ownership, scope selection, request construction and
   response dispatch mapping; read-only live city catalog and scope correlation.
3. **Active:** implement the manager-owned hostility job, including native response
   capture, one request in flight, exact building/scope receipts and duplicate
   avoidance. Keep it independent of the guard spending job and existing resume history.
4. Qualify the native action and response end to end, nation/subguild coverage,
   and whether an additional source is needed for guilds without cities.
