# Automatic character-build capture

The transfer command now reads current equipment, applied runes and attribute
components on exact original/prepared .14 clients. Earlier reviewed clients can
still use --guided-only. Supplemental screenshots remain useful for checking
item names, effect descriptions and base versus modified attributes.

## Qualification and provenance

Original .14 SHA-256:
e703e7cf5ba7edc04e6851336343fb69ab119672ae5e5409846e8760a0e73a2e.
Prepared .14 SHA-256:
78199b9ffc012b2de3bd2901204d87ee4ceb91acc1c4800f3d4437ad4c2be903.
The new reader additionally verifies bounded disk-code spans against original
.14 receipts in character_capture/build.py. An image-family match alone cannot
enable these fields. Original identity load/save/UTF-16 routines match the
existing reviewed 267/243/288-byte fingerprints at 795da0/7963e0/1485b0.

Static evidence: ArcCharacter deserialize 5cfb0, equip 556e0, current rune attach
69350 and multimap insertion 2ec1d0, stat access 68020 and lookup 88760,
InstanceInfo application 272150, stack setter b8b30 and charge setter b8cb0.
All addresses are image-relative hexadecimal RVAs. ArcItem/Rune primary vtables
are 1142748/1143278; effects use descriptor 1147930. The existing native
actor_inventory_native.cpp and actor_effects_native.cpp independently describe
the shared item keys and effect descriptor layout.

Current equipment uses player+BA8, 19 pointers, rather than the login-only
778/780 array. Current runes use the BF4 tree, rather than login-only 77c/784.
Attributes use the CB0 tree. The 19th array index would overlap BF4 and must never
be read as an equipment slot. Item 6B8 is stack count; 744 is remaining charges.
Item durability is 5cc/5d0, and active item effect token/rank records use 58c.
No prefix/suffix role is inferred from effect ordering.

On October 7, bounded reads of a private-server character confirmed current
equipment identities/slots and five stat-node shapes. The client then logged
out/exited before end-to-end reader acceptance. Current-rune and populated-effect
live acceptance remain required; synthetic corruption/change tests are not a
substitute. Static code receipts may reject a prepared image whose code differs.

## Guarantees and limits

Readers bind one process lifetime and character. Counts, pointers, parent links,
cycles, ordered tree extrema, object classes, identifiers, strings and finite
durability are bounded and checked; every captured block is reread before
publishing. An observed mutation rejects that sample. External rereads cannot
provide game-thread atomicity or detect a change-and-restore between reads.

Raw attribute components are retained; wire adjustments can include effective
updates, so they are not represented as permanent point allocations. Equipment
and rune IDs remain source identifiers. Destination mapping and database import
are unfinished and database_import_ready remains false.

No raw memory dump, process write, debugger attachment, input automation,
server credential, client binary or capture is included in source delivery.
