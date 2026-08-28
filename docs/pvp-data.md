# PvP data catalog

PvP simulations need two different kinds of data: legal character identities and the
mechanics that make those identities fight differently. Keep those layers separate so a
client-screen observation cannot silently become an assumed combat formula.

## Current catalog

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

## WonderBane character-creation capture

The character-creation menu is the preferred source for the current client-visible identity
layer. A single continuous screen recording is sufficient if it clearly shows the client build
and every selection pane. Capture the following without creating or deleting a character:

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

The menu does not establish later promotion choices, discipline-slot rules, complete power
rank curves, equipment statistics, resource formulas, hit/defense/resistance behavior, or
interrupt and crowd-control rules unless it explicitly displays them. Those remain separate
coverage domains.

## Evidence priority

For WonderBane parity, prefer evidence in this order:

1. Current WonderBane server data or observed server behavior.
2. Current, build-identified WonderBane client data and UI captures.
3. Repeatable live-client experiments with recorded conditions.
4. Revision-pinned emulator source.
5. Revision-pinned legacy wiki pages.

Conflicts do not get averaged or guessed. Preserve both sources, mark the affected domain
unresolved, and design a focused observation that distinguishes them.

## Remaining acquisition order

After character creation is captured, collect promotion and discipline legality, racial and
class passive effects, ranked power definitions, equipment and enchantments, and finally the
combat formulas needed to turn those records into PvP state transitions.
