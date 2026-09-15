# Client update: September 15, 2026

The normal test VM client in Downloads was patched to WonderBane 1.3.38.7.
The desktop Vendor Test shortcut correctly opens its isolated C: runtime, but
that copy still contains prepared 1.3.38.6. The user reports a patch-required
message inside the game during login. Patching the Downloads copy does not
update Vendor Test. The older S: modded shortcut also retains 1.3.38.6.

## Exact executable review

- Original 1.3.38.6: `feb351f0fae87d47549fa43c37836405a753d76fbcd0b02232fc1c0733550dff`.
- Original 1.3.38.7: `ac9ca46467997667d49b85cd6076954813a72b56f71e2ad85a4085f3a9f391ca`.
- Prepared 1.3.38.7: `b646ae32ebc44be45a7a65da3c764e1cd67f63f45fca91262b75f21fd11002f3`.

The complete files have identical lengths (21,143,613), PE headers and section
layouts. Exactly 314 bytes differ in 11 ranges. Unlike the September 4 update,
this changes actual code as well as the version string. Changed .text ranges
start at RVAs 0x6c981, 0x7600a, 0x760f5, 0x766e0, 0x76715, 0x76739,
0x76790, 0x76800, 0x76823 and 0xbafe3; the .data version byte is 0x12dc18b.
All .rdata, .idata, .rsrc and .reloc bytes are unchanged. Offline profile
alignment finds no intersections with 50 anchors across 16 native profiles.

Disassembly confirms calls at 0x6c980, 0x760f4 and 0xbafe2 now reach added
routines at 0x76800, 0x766e0 and 0x76790; 0x7600a changes a local value and
removes an earlier check. The new routines preserve their original call-throughs
and use existing native data. No modified range overlaps the extension loader,
scene/update boundary, native building selection/collection, hireling controls,
production serialization, queue handling, or character config routines.
This is an offline binding review, not proof of unchanged server behavior.

All seven loader spans resolve without relocation or alteration of their recipe.
The native whole-file verifier accepts only the two reviewed original hashes or
their complete seven-span prepared transformation, then independently compares
relocated loaded code. It still rejects unknown, partially patched and modified
images. Host vendor commands and readers use a narrow two-prepared-image set;
the generic native-layout family cannot admit vendor operations.
Affix calibration is deliberately separate: the new build keeps unqualified
modifiers as unknown, with no disposal authority.

## Source validation and delivery

Native 1.8.7 / host 0.3.16 contain these bindings. Focused Python regressions
cover supported/unsupported images, stale lifetime rejection, queue and roster
ownership, character identity, and conservative affix handling. Native checks on
the actual original/prepared files passed relocated-code authentication, terrain
repair ownership, bootstrap/code/data mutation rejection, scene-boundary digest
and every-byte drift checks, plus 64,256 native collection sequences and 144
continuation cases. Exact committed package validation follows the checkpoint.

The pre-launch guard scripts/check-vendor-client-baseline.ps1 compares the normal
client against the package's reviewed original digest. Install it in the runtime
and call it from the desktop launcher before launching sb.exe. A later normal
client patch must produce an explicit update-needed error before login. It must
never silently patch the prepared executable or spoof the game version.

Delivery branch: codex/vendor-rolling. Integration destination:
codex/native-lifecycle-hardening, then reviewed main. This is not merged.
Private binaries and alignment/disassembly evidence remain under
E:/virtual-machines/shadowbane-testing/diagnostics/vendor-client-patch-20260915.

Next: validate/package the exact source, compare normal game data, prepare a
rollback-preserving executable/DLL/host update, wire the launch guard, and verify
the same desktop shortcut. VM access currently awaits renewed direct approval
because automatic review rejected saved setup credential use despite the earlier
approval recorded in the town-vendor handoff. No migration is installed yet.
Then resume corrected automatic building/vendor discovery; recipe/inventory
opening, durable selections, town scheduling and multi-building qualification
remain unfinished. Never replay old crafting or discovery journals.

## Exact package ready; VM installation pending

Source c64eb0da18b45127488a61fcdd792bb51a8a73e5 is committed and pushed.
The first package attempt (51df4142, source a684e55) caught the remaining native
API version declaration and is not a usable package. c64eb0d fixes it.

Verified package: E:/Projects/shadowbane/artifacts/vendor-packages/e52a5732.
Archive SHA-256: a9b89dd8cd7f0e257fe96a180dc1f8c7a28921c68434a2e5ca9c9a7f4d983280.
Full DLL SHA-256: 79edb54d7cfaab4b2c3ef98ec3a254e94b2ed5dde9a456a806016fd87fbced1c.
Host wheel SHA-256: d5ec7cc70075c7819a4c5d88816b6a90e1ae39a7663445292040aa2c40f33159.

All 61 recorded artifacts and the archive CRC were independently checked.
Clean-source host tests: 2,261 passed, 14 skipped; Ruff passed. Both native
profiles passed required gates, actual updated original/prepared image checks,
real IPC, installed host and vendor navigation contract checks. The new verifier
also passed the earlier 1.3.38.6 original/prepared pair. The two known deferred
ideal-transparency findings remain unchanged; this is a diagnostic package.
The launch guard passed matching, changed and missing original-file checks.

Private replacement payload: E:/virtual-machines/shadowbane-testing/diagnostics/
vendor-1.8.7-c64eb0d. It contains the exact DLL, wheel, prepared sb.exe, authored
bootstrap manifest, launch guard and package-verification.json. It is on the host
only; no guest files, running game, dashboard or jobs were modified this turn.
The guard is not wired into the current desktop shortcut yet.

CI: https://github.com/best-coder-open-now-near-me/shadowbane-lab/actions/runs/34953416615.
Six of seven jobs passed at the last check; native full was still running.

The saved-credential connection was rejected, then rejected again after checking
and citing the existing September 14 authorization. The reviewer said repository
documentation could not establish that authorization. A direct, scoped approval
question is pending with the user; no alternate authentication route was attempted.

Next active todo: finish the VM update after connection approval. Compare normal
static game data with the frozen baseline, read the current launcher, adapt the
existing rollback updater for both executable and DLL, preserve all eight crafting
and three failed-discovery records, wire the guard and verify the same shortcut.
Confirm the game has exited before replacement. Then verify loaded identities,
login and resume one new corrected building/vendor discovery operation.
The previously installed 1.8.6/.15 runtime remains unchanged.

## Installed and launched

The owner reaffirmed the existing saved test VM setup credential authorization
with "you know the answer" in response to the scoped approval question. The same
connection succeeded. The earlier connection block is resolved; no alternate
credential source or connection method was introduced.

All seven CI jobs for c64eb0d passed. Comparing the complete normal Downloads
client with the frozen baseline found 228 identical files and no added files.
Besides sb.exe, the actual changed game assets were cache/CObjects.cache and
Config/Config.wpak; remaining differences were client-written settings/logs and
DoubleFusion data. The update includes both assets, while retaining user settings.

- CObjects.cache SHA-256: 3d7c1467d4ac8abfea3fa2d5acdc887e3557a13fd23f12f2da3dc42c9ca2f9af.
- Config.wpak SHA-256: 1c1e6273dde7d950cd2d44ab8fb703d023590819e8d761b307f72f6c27633f6b.

Shadowbane was already closed. After the new host and payload passed a read-only
dry run, the exact idle manager (zero client slots) was stopped. The updater
verified the entire existing runtime, backed up eight files, replaced exactly
four client inventory entries (EXE, DLL and two game assets), updated package
metadata/launchers, and reverified the complete installed inventory. Eleven
historical vendor/discovery records and sixteen .cfg files matched their saved
hashes at installation. All eight rollback copies passed hash verification.
No crafting, Keep, disposal or discovery operation was issued.

The existing desktop WonderBane Vendor Test shortcut now launches prepared
1.3.38.7 from C:/ShadowbaneLab-Guided/vendor-1.8.3-bd08ffc/client/sb.exe.
The retained directory label is not the game/extension version. Its launcher
pins and invokes the new official-client drift guard before startup and displays
a clear update-needed message if the normal original EXE changes again.
WonderBane Vendor Dashboard now uses host-0.3.16; its prior shortcut is backed up.

Fresh launch: PID 6916, creation FILETIME 134339397355274201, HWND 787324.
The loaded EXE and DLL hashes match this exact package. Manager/worker status
independently confirms this process lifetime, native 1.8.7, one healthy worker,
and no queued or active operation. Refresh identity before subsequent actions.
The user has been asked to log Treehugger into Rooty; login acceptance is pending.

Private activation evidence is in vendor-1.8.7-c64eb0d under the diagnostics
share; guest rollback and receipts are under upgrades/1.8.7-c64eb0d in the runtime.
activation-verification.json and activation-launch-receipt.json supersede the
host-payload-only status. Keep original rollback/captures and the failed package
attempt for traceability; none are in Git. Source remains outside the shared
integration branch. The normal main checkout stays untouched.

Next active todo: verify successful login and run one fresh corrected automatic
building/vendor discovery through host-0.3.16 against this new exact identity.
Then finish recipe/inventory opening, durable town selections and scheduling.
Do not replay historical jobs or infer that town-wide automation is complete.
