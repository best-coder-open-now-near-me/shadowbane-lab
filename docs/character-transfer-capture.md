For continuous capture, incident marks and speech-to-text, use [the tester recorder](character-recorder.txt).

# Current automatic capture update

The default now includes the exact .14 automatic build reader. See [coverage and acceptance limits](automatic-character-build.md). Use --guided-only for the earlier screenshot-led workflow described below. Automatic records still require destination mapping before database import.

# Capture a character for transfer

Run `scripts/capture-wonderbane-character.ps1` **on the Windows machine/VM
running Wonderbane**, with the intended character logged in and standing still.
The script produces a private, versioned evidence folder for one character.

## What the capture contains

- Native character/server identity and exact process/executable provenance.
- Level, unspent ability/training points, attack ratings and defense.
- Every skill/power record exposed by the existing reviewed reader, including
  numeric tokens, trained and effective ranks, and unknown catalog entries.
- Current/maximum health, mana and stamina as observations.
- Guided PNG captures of the character sheet, applied runes/disciplines,
  equipment overview and each equipped item's readable tooltip.
- A manifest with file sizes and SHA-256 hashes, section coverage and status.

**Equipment effects, equipment slots, base attributes and rune selections
require visual review/transcription.** Their exact native layouts are not
qualified by the existing readers. The script never fills them with guessed
values, treats an effective value as a base allocation, or claims an empty
equipment list. Every bundle has `database_import_ready: false`.
Capturing images does not prove that every tooltip is readable or every slot
has been covered. Compare the overview with the individual item images.

This is the requested capture side. Destination mapping/import remains separate:
reconcile images into structured build/item records, verify server templates,
allocate destination IDs, and validate a logged-out character before writing
through the server's persistence contracts. Never execute this bundle as SQL.

## Run

Use Python 3.11+ with the repository's client dependencies (Pillow for pictures).
The launcher checks the checkout's virtual environment, the existing VM lab
environment, then python.exe. It installs nothing. An explicit Python executable
can be selected with `-PythonPath`.

From a checkout containing this change:

```powershell
.\scripts\capture-wonderbane-character.ps1 -CharacterName "YourCharacter"
```

With more than one client, use its Windows PID:

```powershell
.\scripts\capture-wonderbane-character.ps1 -CharacterName "YourCharacter" `
    -ProcessId 1234 -CaptureDelaySeconds 12
```

If the source reports another server spelling/name, provide `-ServerName`.
The expected name and server are checked before any output folder is created.
A changed character invalidates the session; it cannot silently switch to the
next character. Start the script again for each roster member.

For each section, type a descriptive image label in the console, press Enter,
then focus the game within the countdown (eight seconds by default). Open the
requested panel or hover the item so its entire tooltip is readable. Return to
the console after the countdown. Repeat for additional pages/items; type
`/done` to advance. A section with no images is explicitly marked
`not_captured`.

Keep gear and training unchanged through the session. Hide chat if desired;
visible game chat can appear in the pictures. Avoid fighting so numbers are
easier to interpret. Capture base-versus-modified stat tooltips where available.
An equipment-overview image should include empty slots too; label each item
image by its actual slot. Include off-hand equipment, jewelry and alternate
loadouts as separate, clearly identified captures.

The script checks foreground PID, process creation time, window identity,
physical client-area dimensions and native character identity around every
image. It rejects a wrong foreground window, changed window or black frame;
retry in windowed mode if necessary. Images still need visual QA, including
checking for overlays. These bounded before/after checks do not claim atomic
game-state capture or protection against a switch away and back between reads.

It opens the client for query/read only, sends no game input, attaches no
debugger, changes no client settings and connects to no server database.
Exact executable compatibility checks remain enforced.

## Transfer and interruption

The default output is an ignored `captures/character-transfer/<unique-name>/`
directory under the checkout. `-OutputRoot` selects another private directory.
Transfer the **whole folder**, including `manifest.json`, both native JSON
observations and the images. Compare each file with its manifest hash after
transfer. Captures may contain private character data; do not commit them.

A normal finish has status `review_required`, never import-ready. Ctrl+C or
input EOF retains already saved evidence with status `interrupted`; an error
marks it `failed`. A hard process termination can leave `collecting`, which
also means incomplete. Every run has a unique directory; earlier captures are
never overwritten. Manifest replacement uses a temporary file only for the
current write, with no retained rollback copy.

`-NativeOnly` is available for diagnostics. It omits all pictures and therefore
does not collect equipment, base attributes or runes.

## Validation and delivery

Source branch: `codex/character-transfer-capture`; integration destination:
`main`. This source is outside main until its PR is reviewed and merged.
Validation: 53 focused tests passed; Python lint, PowerShell parsing and CLI
help checks passed. Tests cover identity changes, process replacement, training changes,
wrong/changed foreground windows, black/mis-sized frames, interrupted sessions,
unique outputs, checksums and overwrite refusal. Native-reader tests are run
alongside them. Live capture and visual review of a real character remain the
next acceptance step; synthetic tests do not establish tooltip completeness.
