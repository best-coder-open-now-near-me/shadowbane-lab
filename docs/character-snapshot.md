# Read-only WonderBane character snapshots

The character collector reads declared fields from a running `Shadowbane.exe` and writes a
versioned JSON document suitable for build presets and simulator calibration. It is deliberately
external and read-only: it requests process-query and VM-read rights, sends no game input, performs
no injection, writes no client memory, and does not create a whole-process dump.

The first revision provides two pieces:

1. bounded discovery commands for locating a character object; and
2. a hash-pinned layout reader for capturing only reviewed fields.

The layout offsets still have to be recovered from the WonderBane client analysis. The bundled
template is therefore live-locked and cannot capture until its offsets are filled in. It includes
the previously audited client hash `0bc19747ebc5f5f821eea7b0a5e4cecdf685ddf6d7fed84e24bac1f18b66e555`;
`inspect-process` must confirm that the currently patched client still matches before we reuse any
recovered offsets.

## Install in the VM

From a checkout of the repository:

```powershell
py -m pip install -e ".[test]"
```

Run PowerShell or the terminal at the same Windows integrity level as the game. Ordinary user mode
is preferred. Administrator elevation is only needed when the client itself was launched elevated.

## Pin the running client

Log into the character, then record the process identity and exact executable hash:

```powershell
shadowbane-lab character inspect-process --json > wonderbane-process.json
```

The output contains the PID, installed `Shadowbane.exe` path, SHA-256, pointer size, and loaded
modules. Layouts are expected to name the executable and should pin that SHA-256 so offsets from an
older patch cannot be applied silently to a changed binary.

When more than one client is open, pass the selected PID:

```powershell
shadowbane-lab character inspect-process --pid 1234 --json
```

## Bounded discovery

Search readable committed pages for the exact character name:

```powershell
shadowbane-lab character scan-text "CharacterName" `
  --max-scan-mib 512 `
  --max-matches 50 `
  --json > character-name-matches.json
```

The scanner checks CP-1252, UTF-8, and UTF-16LE by default. It streams memory and retains only a
small context around each match; it does not dump the process. Additional encodings can be selected
with repeated `--encoding` options.

A promising string address can be followed by searching for 32-bit pointer references to it:

```powershell
shadowbane-lab character scan-pointer 0x12345678 `
  --max-scan-mib 512 `
  --json > character-name-xrefs.json
```

This is useful for confirming a static-analysis candidate and finding the live owner object. It is
not intended to replace the executable analysis: stable module-relative roots and field offsets
should come from the code/data structures whenever possible.

## Layout format

Copy `configs/wonderbane-character-layout.template.json` to
`configs/wonderbane-character-layout.local.json`. The `.local.json` file and `captures/` output
are ignored by Git so a character snapshot is not committed accidentally. Then:

1. set `target.expected_sha256` to the installed executable hash;
2. replace the root and field placeholder offsets;
3. verify pointer size and equipment slot order;
4. add values/records/collections for the recovered character structures; and
5. set `target.live_capture_enabled` to `true` only after review.

Validate without opening the process:

```powershell
shadowbane-lab character validate-layout .\configs\wonderbane-character-layout.local.json
```

An address is explicit rather than implied:

```json
{
  "base": "module:Shadowbane.exe",
  "steps": [
    {"offset": "0x01234567", "dereference": true},
    {"offset": "0x20", "dereference": true},
    {"offset": "0x14", "dereference": false}
  ]
}
```

Supported bases are `module:<name>`, `root:<name>`, `record`, and `element`. Supported scalar types
are signed/unsigned integers, floats, pointers, booleans, C strings, UTF-16 strings, raw byte
arrays, and hexadecimal byte strings. Fixed collections cover structures such as the equipped-item
slot array; each element may itself be a pointer.

## Capture

```powershell
shadowbane-lab character snapshot `
  .\configs\wonderbane-character-layout.local.json `
  --output .\captures\my-assassin.json
```

The output is limited to fields declared in the layout. A complete layout can include:

- identity, level, race, base class, and promotion;
- attributes and current/maximum health, mana, and stamina;
- attack rating, defense, movement, resistances, and derived values;
- skill and power ranks;
- equipment slot, instance/template IDs, name, durability, prefixes/suffixes, and item effects;
- inventory records; and
- active buffs/effects when their structures are known.

Optional fields become warnings when unreadable. Required fields fail the capture, which prevents a
partially stale layout from looking authoritative.

## Privacy and safety boundaries

The collector does not retain unrelated memory. Discovery output contains only the requested match
and a small byte context. Even so, process memory can contain chat text or transient session data,
so inspect discovery JSON before sharing it. The final layout should avoid network, account,
credential, and chat structures entirely.

Use this only against the user's own running client and within the live service's rules. The tool
contains no anti-detection, anti-cheat bypass, packet tampering, or automation behavior.
