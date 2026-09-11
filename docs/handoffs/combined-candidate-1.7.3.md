# Terrain/movement integration candidate 1.7.3

Exact package source `04b7bdb298606f381618e8a66537955d7451b426`, branch
`codex/native-lifecycle-hardening`, common base
`14d117e8c5194c6dff55dac608b2d3f683187d31`. Native product 1.7.3.0,
wheel 0.2.3; ABI/wire unchanged. Adds movement owner
`622a688a8cf41e74cd5b5ba14df55f9c83252108` as `0c8ddb4` to the preceding
[1.7.2 candidate and connected finding](combined-candidate-1.7.2.md).

The previous candidate rejected the existing four-byte terrain repair during
movement admission. The shared terrain owner now validates its exact active,
complete owned patch set before normalizing only movement's comparison copy.
Unrelated, partial, changed, and unowned modifications still fail. Disk and live
code are not altered by verification. The real terrain startup/stop path is now
part of the original/prepared movement-image test; diagnostics asserts disabled
terrain behavior. This preserves the working terrain and navigation behavior.

## Artifact identity and executed checks

Package directory `E:/Projects/shadowbane/artifacts/combined-packages/3cbb5e38`:

- ZIP SHA256 `d66e81c36ca8ec6cc9248b3b3c04992b01b421eb19ba1690bdc38368c7afe1b8`
- Full DLL `2f173c46098c2731dc8bef9efa8f2a4a4a54fd66ca8235e1aa968e1613e87dee`
- Diagnostics DLL `552a856ad1e41ee6127c783e6b3c64cf77d4701a597963af6a71e1ea91e11dbb`
- Wheel `e5d483887652b0195177eec66c715d618106e127e36269a13963a2a3b9af7e73`

Existing clean-source package builder completed. All 57 receipt files matched
size/hash; ZIP CRC passed and private prepared executables were excluded.
Python: 1834 passed, 12 skipped, 238 passing subtests; Ruff passed. Each profile:
105 native cases executed and passed, 3 no-argument private-data skips followed
by explicit passing selected/sky/original-prepared movement gates. Each profile
also executed 30 passing real movement IPC tests with zero skips. Actual terrain
startup ownership/restoration and rejection cases ran in the private image gate.
All installed-wheel panel/status/entry-point/trace checks passed outside source.
Profile runtime source lists were checked by the existing builder.

Independent Astra review of the focused runtime, version and CMake changes found
no blocking issues (source/assertion review, no independent VM execution). The
existing particles owner stayed paused for implementation and touched no VM state.
Previously deferred ideal transparency diagnostics remain explicitly failed;
particles remain suppressed. New PvP identity work is excluded. Accepted highlight
appearance, deferred hand-material observation and demonstrated navigation retain
their prior status.

Hosted CI [34046458077](https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34046458077): all seven jobs succeeded on the exact source.
Python 3.11/3.12/3.13 each executed 1839 passing tests, 4 skips and 241 passing
subtests. Both native logs explicitly confirm startup-failure and actual settings
runtime execution. Full log: `artifacts/combined-1.7.3-ci.log`.

## Connected acceptance

Use the same full-profile bootstrap preparation and software-renderer environment
as 1.7.2, with this candidate's exact DLL/wheel. Preserve current Config. Replace
only the designated diagnostic client after exact-lifetime verification and normal
close. Keep other clients untouched. No new trace collection or PvP action is needed.

First verify a nonterminal movement snapshot and the settings panel. Then use
clear space for keyboard/controller movement, release-to-stop, chat/focus recovery,
manual/automation handover and multi-client isolation. Physical controller input
is a separate live question from successful movement runtime admission. Do not ask
for broad navigation replay or revisit accepted highlight appearance.

The owner-approved installation completed in a separate 1.7.3 guest directory.
The 1.7.2 diagnostic client closed normally after exact path/lifetime verification.
Its Config was copied to the new prepared client, and 1.7.2 remains available.
The obsolete 1.7.1 client copy was removed under prior backup-deletion approval
to free space; its Python environment and private receipts were retained.
The exact 1.7.3 loaded DLL hash was verified with 32-bit module enumeration.
No unrelated client was stopped.

At the login screen movement status was unpublished rather than the previous
terminal rejection. Successful startup does not publish until the first owning
world update, so this alone is not proof of admission. The owner was asked only
to enter the world; next is a bounded exact-lifetime read and settings check,
then the remaining physical input/safety checks. No connected movement success
is claimed yet. Private installation, launch and read-only status receipts are
in the existing diagnostics share under `combined-acceptance-1.7.3-3cbb5e38`.

### In-world startup and settings confirmed

After the owner entered the world, the installed read-only consumer returned a
live snapshot (sequence3474, flags23, scene1, exact HWND/process lifetime) with
controls disabled and no movement owner. The installed production
`open_native_movement_settings` interface discovered the exact client and returned
success opening its native panel. This closes the reported startup/settings
unavailable defect on the actual package. It does not yet certify physical
controller movement, stop/chat/focus behavior or manual/automation handover.
Next: owner enables the desired input in the now-open panel and performs the
short movement/release-to-stop check in clear space, followed by targeted safety
checks. Private results are retained with the installation receipts.

### Follow-up: independent keyboard startup remains open

The owner reports that WASD works only after the first right-click. WASD and
mouse steering are separate controls; keyboard movement must initiate from idle
without any mouse prerequisite. Earlier ambiguity about button rebinding was
resolved: a guessed right-button rebind is not the fix and is excluded.

The movement owner found that existing runtime manual regressions first establish
an automation destination and backend fixtures seed moving/path state. They are
adding genuine keyboard-first cold-idle coverage and tracing native movement
initialization. Root will require the new regression in the existing package gate.
No behavioral fix or new live acceptance is claimed yet. The working 1.7.3
startup/settings path is preserved, and no additional user focus retry is requested.
