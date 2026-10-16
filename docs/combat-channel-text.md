# Combat channel text — October 16, 2026

Source branch: `codex/combat-channel-text-20261016`, based on refreshed shared
`main` at `ef02070f`. Integration destination: reviewed `main`. The user requested
combining this translation candidate with vendor testing; it is now installed
in the test VM alongside the six-worker launcher, with numeric/newline acceptance
still pending. No live acceptance is claimed. The active request includes compact two-line formatting, numeric
weapon drains, and incorrect self-drain wording.

## Confirmed findings

The current official manifest pins `Config/DataStringENGLISH.txt` to SHA-256
`4919261e7c9f9887bde63d128717849062eea7ce37214891676992c832b26845`.
The inspected local reference has exactly this identity, despite its older
directory date. It is UTF-16LE with a BOM.

Six weapon-drain translations (health and vitality, each in outgoing, incoming
and third-person forms) say `drains some of` and contain no `%DAMAGEVAL%`.
Ordinary health-drain spell translations already contain that placeholder.
Missing numeric display is therefore confirmed in the weapon translations;
whether the weapon-drain event substitutes that placeholder remains unverified.

Localization records contain a quoted lookup key and quoted display value.
The keys include the original English sentence and must remain unchanged.
Other existing translations use the literal `\n` escape. This supports preparing
two-line values, but does not establish combat-channel rendering behavior.

## Candidate and validation

`python -m shadowbane_lab.client_extension.combat_text SOURCE OUTPUT` creates
a new offline candidate `DataStringENGLISH.txt`. It requires the exact reviewed
source hash and refuses to overwrite an existing output. It changes only nine
display values: the six weapon drains and three standard fire-damage templates.
It preserves the original keys, unrelated content, BOM and line endings.

Examples after substitution (line break shown as an actual break here):

```text
You -> Enemy
999 weapon health drain

You -> Enemy
999 Weapon Fire
```

Three regressions cover source rejection, preservation of lookup keys/encoding
and unrelated content, and missing expected records. Compilation against the
actual official resource succeeded, producing 2,843,486 bytes with SHA-256
`4b21d60fc382d4b5047561a60bcdcdf088b46a750a2f10b533faefa6db01a9aa`.
Original lookup keys and unrelated translations are preserved. The separate
official client is unchanged, and no candidate binary is published with source.
The vendor test installation updates its one translation resource and package
inventory in place, preserves 17 settings/layout files and leaves host/native
software unchanged. See [combined test evidence](vm-renderer-performance.md).

## Active todos

- [x] Find and verify the shared weapon-drain translations.
- [x] Prepare and test the hash-pinned two-line translation candidate.
- [ ] **Active:** verify weapon-drain numeric substitution and two-line rendering
  in the installed combined test. Trace signed health changes before broadening
  classification; the installed values remain a test candidate, not a qualified
  repair of loss/recovery semantics.
- [ ] Correct the self-drain wording using actual event direction. The available
  emulator reference sends separate source-to-target loss and source-to-source
  recovery messages; it does not prove current WonderBane behavior. Do not hide
  all self-target events, infer healing from the sentence, invent amounts, or
  equate damage with restored health.
- [ ] Verify two-line channel rendering and supported emphasis controls;
  bold/underline remains unimplemented. Preserve raw semantic events consumed
  by observers when broadening formatting to melee/miss/death messages.
- [ ] Complete the remaining combat-message families, review, package and live
  qualification, then install through the established runtime workflow.

This candidate deliberately leaves the self-drain issue unresolved. A static
translation cannot select different wording from the sign of a numeric event.
Do not integrate it as a completed combat-channel repair or mark the user request
complete until the event and rendering checks above are satisfied.
