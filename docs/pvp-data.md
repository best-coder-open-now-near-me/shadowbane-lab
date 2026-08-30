# PvP data catalog

PvP simulations need two different kinds of data: legal character identities and the
mechanics that make those identities fight differently. Keep those layers separate so a
client-screen observation cannot silently become an assumed combat formula.

## Source order

Use the current WonderBane calculator first for static identity, rune, discipline, progression,
and published resource formulas. Treat its outputs as `wonderbane_calculator_derived` until a
representative live-client cross-check agrees. Use build-identified live observations next,
then executable or memory analysis only for fields the calculator omits or where the two sources
disagree. Revision-pinned emulator and wiki data remain comparison fallbacks.

Conflicts do not get averaged or guessed. Preserve both sources, mark the affected field
unresolved, and design a focused observation that distinguishes them.

## Pinned combat formulas and executable profile boundary

The combat runtime now ports a revision-pinned MagicBane server formula set, with exact source
files, locators, and hashes recorded in
`evidence/pvp/combat-formulas/magicbane-combat-formulas-3649c629.manifest.json`. It covers basic
and power hit curves, weapon and power attack rating, defense, weapon damage, stat/focus scaling,
centered health-effect rolls, resistance/protection/armor piercing, and effect overwrite rules.
The same manifest pins the historical editor power-hash table. Current WonderBane native training
data confirms Shadow Touch as `ASS-013` / `428918601`, Shadow Bolt as `ASS-018` / `429213513`,
and Steal Breath as `ASS-019` / `429246281` on client SHA-256
`ef43784ba6ffa0de6c0c16c76569f864393ad1530e7149395bb560e5cca30f13`.

These formulas are not treated as silently current. `CombatSheet` carries its exact formula
revision and a `live_verified`, `source_revision_accepted`, or `unverified` compatibility state.
The complete-sheet compiler requires all runtime inputs and rejects absent resistances, passive
defenses, weapon/skill data, power-focus values, unresolved selected powers, incompatible source
revisions, and unaccepted ruleset overrides. See the complete profile and batch commands in
[simulation-rollouts.md](simulation-rollouts.md).

The simulator now represents the five stances as one exclusive state and models the observed
travel-to-normal transition on an unavoided hit. It also distinguishes caster-centered areas
from entity- or ground-target-centered areas, with explicit relation filters, radius, optional
target caps, and per-victim power-hit checks. This supplies the durable execution boundary but
does not invent stance modifiers or AoE rows: current values for offensive, defensive, and
precise tradeoffs, each power's origin/radius/cap, and edge behavior such as fully immune hits
remain acquisition fields.

Timed effects now carry deterministic periodic schedules, scalar multipliers, resistance
adjustments, and stateful damage breakpoints. Steal Breath and Psychic Shield exercise those
generic primitives in the checked level-75 source matchup. The Psychic Shield breakpoint remains
source-conflicted (`1000` in the pinned power table, `750` in later MagicBane patch history), so
the row stays `compiled_with_override` until current WonderBane data resolves it.

## Legacy comparison catalog

`shadowbane_legacy_catalog_v1.json` is a normalized, revision-pinned comparison baseline. It
contains 12 races, 4 base classes, 22 professions, 47 disciplines, and 319 legal combinations
of race, base class, profession, and sex. The loader fails closed on unknown references,
contradictory racial-discipline access, and illegal builds.

The catalog targets WonderBane but has `legacy_baseline` status. It must not be treated as a
statement of current WonderBane parity. Each coverage entry says whether a data domain is
complete, partial, or unresolved.

```python
from shadowbane_lab.progression import (
    CharacterSex,
    CoreBuildIdentity,
    load_shadowbane_legacy_catalog,
)

catalog = load_shadowbane_legacy_catalog()
catalog.validate_core_build(
    CoreBuildIdentity("irekei", "rogue", "assassin", CharacterSex.MALE)
)
```

## Pinned WonderBane calculator

The public [WonderBane Character Calculator](https://wonderbane.com/) says it mirrors server stat
formulas and exposes race, base-class, promotion, starting-rune, stat-rune, and discipline inputs.
The 2026-08-28 snapshot is preserved under `evidence/pvp/calculator` with its SHA-256 manifest and
normalized catalog. Its reviewed declarations contain:

- 22 race/sex records across 12 race families;
- 4 base classes;
- 23 promotions, including Ninja;
- 179 combined rune records, 48 of which are classified as disciplines;
- attribute starts, caps, modifiers, costs, prerequisites, skill/power grants, and rune legality;
- level-point, base/promotion growth, health, mana, stamina, defense, and discipline-limit
  declarations.

The importer uses a restricted array/object/string/integer grammar and never evaluates downloaded
JavaScript. It accepts only the known `RACES`, `BASES`, `PROMOS`, `RUNES`, `BOON`, and reviewed
formula declarations. It also limits downloads to two MiB from the exact WonderBane HTTPS home
page. A full-page SHA-256 preserves the source snapshot; a separate declaration SHA-256 prevents
unrelated page changes from silently changing calculator data. Declaration or record-count drift
writes a `review_required` candidate and disables formula evaluation until the review profile is
updated deliberately.

```powershell
shadowbane-lab progression import-wonderbane-calculator `
  --download `
  --output evidence/pvp/calculator `
  --json
```

The pinned catalog retains seven unresolved legality references: several runes name Saetor, but
the calculator has no Saetor race/sex record. Those edges are preserved rather than invented.
The calculator also adds a universal `BOON = 5` to derived attributes. The controlled creation-pane
observation did not display that extra five for the selected Aracoix/Fighter values, so the boon
formula remains calculator-derived; it may describe a post-creation server adjustment, but a live
character-sheet comparison is required before promotion.

The reviewed normalized catalog is bundled for offline simulator and harness use. Discipline
eligibility can be queried without accessing the web or running downloaded code:

```python
from shadowbane_lab.progression import load_bundled_wonderbane_calculator_catalog

catalog = load_bundled_wonderbane_calculator_catalog()
disciplines = catalog.eligible_disciplines(
    race_id=2013,       # Irekei, Male
    base_class_id=2502, # Rogue
    promotion_id=2504,  # Assassin
    level=59,
)
```

## WonderBane character-creation capture

The character-creation menu is the live verification source for current client-visible values and
calculator conflicts. A single continuous screen recording is sufficient if it clearly shows the
client build and every selection pane. Capture the following without creating or deleting a
character:

1. Record the capture date, client version, and executable SHA-256.
2. Select each race and show its description, creation cost, starting attributes, attribute
   caps, racial effects, and available sexes.
3. For each race and sex, cycle every base class and show both enabled and disabled choices.
4. Cycle every creation trait or starting rune and show cost, effects, and prerequisites.
5. Show any profession, discipline, or special-class choice exposed during creation.

Use screenshots instead when text becomes unreadable in the recording. Preserve the original
capture as provenance; transcribed values should cite the capture identifier and frame or image
number. Values are promoted to `wonderbane_verified` only after all affected legality edges are
cross-checked and the resulting catalog passes validation.

### Passive incoming capture

If manually cycling the menu is impractical, capture the server payload delivered when the
creation screen is entered. With WonderBane running and logged in, launch this from a regular
PowerShell window inside the VM; accept the Windows administrator prompt required by Packet
Monitor:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\start-wonderbane-incoming-capture.ps1
```

Leave and re-enter character creation once. The collector is read-only and filters traffic to
the TCP and UDP endpoints currently owned by that exact `sb.exe` process. Stop and export it
with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  \\VBOXSVR\codexrepo\scripts\stop-wonderbane-incoming-capture.ps1
```

The stop command converts the bounded circular ETL to PCAPNG and copies the PCAPNG plus a client
hash/endpoint manifest to `\\VBOXSVR\codexdiag\incoming-captures`. Raw network traffic may
contain account, session, or chat data. Keep captures private and extract only the game-definition
records needed by the catalog.

The VM launcher also writes a redacted `wonderbane-incoming-active.json` marker after Packet
Monitor starts. Startup failures write `wonderbane-incoming-start-error.json`, allowing the host
to distinguish a successful capture from a transient elevated-shell failure without reading raw
packets. The stop script removes the active marker after finalization.

### 2026-08-28 capture result

The first bounded WonderBane capture covered one confirmed leave/re-enter transition on client
SHA-256 `ef43784ba6ffa0de6c0c16c76569f864393ad1530e7149395bb560e5cca30f13`.
The private PCAPNG is valid and untruncated, but its application bytes are opaque at the NIC
boundary: 772 incoming bytes and one 4-byte outgoing payload have 7.7137 bits/byte Shannon
entropy, random-like printable density, and no printable run longer than seven bytes. This is
consistent with encrypted or session-obfuscated transport rather than plaintext creation records.
The redacted structural evidence is preserved in
`evidence/pvp/wonderbane-incoming-20260828T061802186Z.summary.json`; the raw capture and endpoint
metadata are not committed.

This observation promotes no catalog values. Repeating the same passive capture is unlikely to
expose more semantics. The next acquisition boundary is inside `sb.exe`, immediately after its
transport decoder, or in the decoded character-definition table populated by that handler. A
focused trace should correlate the single 4-byte client request and following fixed-size incoming
segments with writes to candidate decoded buffers, then export only normalized definitions and
their capture provenance.

### 2026-08-28 decoded creation cache

A subsequent read-only observation located the post-decryption creation-definition cache for the
same executable SHA-256. The redacted summary in
`evidence/pvp/wonderbane-native-creation-20260828.summary.json` preserves 28 identified race,
base-class, and promotion descriptions/effect strings. It contains no process id, heap address,
arbitrary memory, or account/session data.

The cache is a definition population table, not an active-selection pointer: selecting Centaur
did not replace the anchored Aracoix record. Shade and Mage were not present in the bounded table
segment and remain known missing cache keys. The controlled Aracoix/Fighter and Centaur/Fighter
selection values agree with calculator race starts plus Fighter modifiers before `BOON = 5`, which
is why the boon remains an explicit unresolved cross-source difference.

The menu does not establish later promotion choices, discipline-slot rules, complete power
rank curves, equipment statistics, resource formulas, hit/defense/resistance behavior, or
interrupt and crowd-control rules unless it explicitly displays them. Those remain separate
coverage domains.

## Remaining acquisition order

Cross-check representative calculator builds against live character sheets, starting with the
universal boon and resource totals. Then collect current WonderBane complete combat sheets and
ranked power definitions. The pinned emulator source now supplies explicit candidate formulas for
hit/attack rating, weapon damage, resistance, power scaling, interrupts, and effect stacking;
representative live differentials are still required before profiles may be labeled
`live_verified`. Use focused executable analysis for current equipment/enchantment rows, full
Assassin and Warlock power data, and any field where the deployment differs from the pinned
formula revision. The ranked power pass must explicitly record stance transitions and modifiers,
plus each area power's caster/target origin, radius, relation set, target limit, and hit/avoidance
behavior.
