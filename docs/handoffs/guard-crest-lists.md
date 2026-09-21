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
be equal while retaining separate roles. Hidden cached KOS and Antagonist windows
were also present, with no loaded entries and zero KOS context. This does not
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

- HUD class/kind and explicit hidden/visible state;
- typed list rows through HUD/list/control ownership;
- separate character, guild and nation display names and object keys;
- selected row membership, raw row keys and raw flags;
- KOS raw context and pending identities, and options-dialog raw flags.

Every read is checked again for consistency. Unsupported builds, broken ownership,
duplicate entry pointers, a selection outside its list and changing observations
reject the snapshot. Unknown HUD classes are not parsed. Empty hidden lists remain
explicitly hidden, and no current asset-manager building is substituted for an
unbound KOS context. The reader cannot prove a server response, management
permission, town completeness or command admission.

Validation: 27 focused observer/recorder tests passed, covering identity-role
preservation, hidden cached menus, unrelated HUDs, ownership failures, stale
selection and changing state. The exact new reader also passed against the
running prepared client, observing the retained crest and hidden empty lists.
The saved-crest/list layout is live-qualified; active building KOS binding and
crest-options state still need live qualification.

The observer source was exercised directly in a bounded private diagnostic
recorder without modifying installed host/client files. No new product version
or native extension deployment is implied. Private captures, scripts, names and
object IDs remain outside Git.

## Next work

1. **Active:** reopen the original building's Enemies list and verify its context,
   loaded entry and individual/guild/nation flags with the new recorder.
2. Finish tracing scope selection, request construction and response reconciliation.
3. Establish whether map data provides a complete directory, including landless
   guilds, and qualify nation/subguild coverage and list ownership scope.
4. Implement the manager-owned hostility job with explicit target identities,
   durable receipts, duplicate avoidance and observed response checks. Keep it
   independent of the existing guard spending job.
