# Katana mod pack on a hardware Windows PC — October 8, 2026

This installation uses a separate active `Wonderbane-Modded` client and the
normal Wonderbane server. Its dedicated launcher verifies the complete immutable
package before starting `sb.exe`, clears inherited VM-only Mesa/software-rendering
environment overrides for that child process, waits for an exact-process full
renderer status, and opens Graphics Lab on the Katana tab. The normal client is
independently usable. This is not a rollback copy.

Source is based on the new-machine handoff at `e404d06` from PR #106. The initial
native candidate was built from `e0bc03e64775042121512ccac0b14f2cacb40805`:

- Native DLL SHA-256: `27c31699f7c3e27be415e6a129528f79e823efbde247c4de18042d6fa3cc8d60`.
- Official executable SHA-256: `381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5`.
- Prepared executable SHA-256: `e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437`.
- Full profile, host 0.3.78 / native 1.8.54, katana channel schema 2.

Only CObject `0:6000280` (Commander's Tlanarion Long Sword of the Spriggan) is
redirected to Archon's Blade `0:7307`, using render `0:9996101`. Independent
full decoding verified unchanged gameplay/animation data, matching RHELD
attachment, scale and location, and absent female/low-detail alternate renders.
All 10,691 resources were checked; exactly one payload changed, preserving its
native compression mode. Mesh `0:29243` and texture `0:8029210` were verified.
The override affects that subtype wherever this local client renders it.

## Qualification and runtime

The Windows build service compiled successfully. Its moon-fire test failed the
visible-pixel assertion, and the hosted job remains failed. The workflow retains
the candidate and the failure evidence explicitly; an uploaded candidate is not
an installation qualification. The native implementation and assertions were
not weakened to bypass this result.

On the destination PC, the same binary passed the moon-fire pixel, pulse,
occlusion, clipping, depth/stencil and state tests. All 238 required native tests
passed after translating hosted fixture paths to this checkout. The three
private-image checks passed separately against the actual original/prepared
executables. The two pre-existing transparency stretch diagnostics are outside
this required suite; arbitrary translucent-scene ordering remains unqualified.

Nineteen focused katana/appearance/visual tests and 68 bootstrap/package/panel
checks passed, including two subtests. Actual Tk panel construction also passed.
Complete package verification passed and all 79 Config/wasd settings files were
preserved. The client started and published its identity-bound full-renderer
status; its loaded modules include the expected DLL and NVIDIA `nvoglv32.dll`.
The panel connected with the approved 80% length and six fire defaults. At this
checkpoint login/in-world dual-weapon acceptance was pending. A subsequent
identity-checked read observed two owned Archon render instances, two weapon
draws, two moon-fire draws and no suppression in the live hardware client.
Visual tuning remains user-controlled.

## Launch and upkeep

The local launch entries are `Play-Wonderbane-Modded.cmd` and
`Open-Katana-Panel.cmd`, with desktop shortcuts `Wonderbane Modded` and
`Katana Mod Panel`. Their local configuration binds the exact package inventory,
client/DLL hashes, and panel source files. `scripts/start-wonderbane-mod-pack.py`
accepts `--config`, `--check`, and `--panel-only`.

Use the dedicated launcher for the modded copy. The upstream patcher owns the
normal official installation; a later client update requires deliberately
qualifying and rebuilding the modded copy. Preserve settings and follow
[the deployment policy](deployment-policy.md). No old runtime is retained for
rollback. Exact machine paths, launch receipts, client assets and test captures
remain private local artifacts.

This branch targets main after dependency PR #106. It does not merge that draft
or claim broader Visual Inspector, animation or transparency acceptance.

## Selected-character moon-fire update

The Katana tab now offers **My character** and **Selected character**. Both
length and moon-fire follow the chosen owner. Selected mode uses the existing
bounded attachment resolver and rechecks the selected actor identity before
rendering; losing the selection suspends the effect without falling back to
self. Only that actor's two matching Archon render instances are eligible.
Changing the selection follows the newly selected actor on subsequent frames.
The effect remains local to this client.

Katana channel schema 3 uses the first reserved word at byte 84 for owner mode
(0 self, 1 selected), retaining the 96-byte allocation. The panel and native
extension reject older schema versions and invalid owner values. Native tests
cover wrong-owner exclusion, selection loss and identity change, switching back
to self, malformed mode and old schema rejection. Python protocol and cosmetic
asset checks pass (20 tests), as do 59 package/status/control tests and two
subtests. The updated Tk panel constructs successfully; lint passes.

Installed native source: `8dce4031eb8e463ffdf3cef6514079db3e2f90ce`.
Installed DLL SHA-256: `73d39571a7ccd3461a7617c97b45dce61b400121075642a43dfc1150c69975dd`.
GitHub run `37840764690` compiled this candidate successfully. Its selected-owner
test passed; its combat-power-entry optional-state fixture and moon-fire
visible-pixel test failed. The hosted job remains failed and its full test log
is retained locally. The uploaded LastTest.log was overwritten by the inventory
query, so the failure evidence was retrieved from the Actions job log itself.

On this PC, all 238 required native tests passed, including those two hosted
failures, plus all three checks against the actual original/prepared client
executables. Three private-image tests skip in the generic suite and pass when
provided the exact client images. No assertions or native behavior were relaxed.
The candidate was installed after normal logout; all 79 Config/wasd files were
preserved. No cache or executable change was needed. Superseded native binaries
and the download archive were removed; validation receipts remain.

The launcher accepts optional local `katana_startup` settings and applies them
before opening the panel. This installation restores the user's saved six fire
sliders, 80% length and selected-character mode. The updated client and panel
have reopened. After the user reselected the intended remote character, an
identity-checked live read confirmed selected mode 1, the requested/applied
sequence in agreement, 80% length, two matching katanas, two weapon draws and
two moon-fire draws with error 0 and suppression 0. Exact character identity and
runtime captures remain private. This verifies the selected render path; visual
tuning remains available through the panel.
