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

On October 7, the live original .14 private-server reader captured seven current
equipped items, eight applied runes and all five attributes. A complete watcher
session then captured three native/diagnostic samples and sealed its verified
evidence bundle, with input and microphone disabled. Raw evidence stays local in
captures/recorder-acceptance/watch-0f027bf1fa7e4b2b90aa0111c36d4f3d.
The private source's GameObjectType enum uses PlayerCharacter=52 and Item=30;
Wonderbane's existing player guard remains 53. Only the explicit Private SB
capture reader accepts 52. No bot/action authorization is changed.
Populated item-effect and Wonderbane live acceptance remain required. Synthetic
corruption/change tests do not replace those checks. The prepared-image code
receipts are checked at startup; no live prepared-image acceptance is claimed.

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


## Recorder package qualification

The portable recorder built from source dc7b10851237b835ba8a417dd1e0c2ea7297bd41
passed its embedded Windows widget, disabled-hook lifecycle, native-profile
resource, dictation-helper resource and verified-evidence-bundle checks.
Local deliverable:
E:/Projects/shadowbane/artifacts/character-recorder/ShadowbaneRecorder-dc7b10851237.zip
SHA-256: 5ace8e3c3f564cf572b489a6a731b46f4652df8867e02f26274efd13567b6e43.
The adjacent qualification-dc7b10851237.json retains the embedded check receipt.
The package directory includes its source revision and hashed file inventory.
Failed intermediate build output and successful build scratch were removed;
the current distributable and its expanded runnable folder remain.

An installed MS-1033-80-DESK en-US recognizer transcribed two synthetic WAV phrases
through both the PowerShell helper and Python bridge. This used no microphone.
Real microphone accuracy and game vocabulary remain a tester acceptance item.
Implementation uses the documented [System.Speech dictation API](https://learn.microsoft.com/en-us/dotnet/api/system.speech.recognition.speechrecognitionengine.-ctor?view=netframework-4.8).
Transcripts retain confidence and audio-stream offsets; stream alignment is
approximate, and corrected notes are separate records linked to the original
transcript IDs. Dictation does not interpret speech as commands.

135 focused automated tests passed before packaging. No real input was injected.
The task worktree retains ignored research evidence in artifacts/watcher-layout
at its original paths (static disassembly, scripts and synthetic-audio receipts),
an isolated build toolchain in artifacts/recorder-build/venv, and the private live
capture under captures/recorder-acceptance. These are not pushed or packaged.
