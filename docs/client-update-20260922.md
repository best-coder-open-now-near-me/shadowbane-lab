# Client update: September 22, 2026

The official patch manifest now supplies client 1.3.38.10. Compared with the
September 19 manifest, exactly three official files changed: sb.exe,
Config/Config.wpak and cache/CObjects.cache. Manifest version/gameVersion labels
remain stale; the executable's embedded version and exact hashes identify it.
Downloads match each manifest SHA-256 and byte count.

## Exact compatibility review

Original SHA-256: `cae5311b5b6134bf25155b16c70b1743c1216c0bd0c88f1240d7e92388211d26`.
Prepared SHA-256: `761f375e422332cac2512398bb935af38b30267b9b3a7a5cede9f87e98982442`.
Reviewed reference: `a32275aabab8d5955f4d45adde6e84a666f44be54c951ccf8dc2d538237e8be4`.

Both files are 21,143,613 bytes. Exactly two bytes differ at file offset/RVA
0x12dc18b through 0x12dc18c: `39 00` becomes `31 30`, extending the embedded
version string from 1.3.38.9 to 1.3.38.10. Headers, section layouts and every
other byte match, including the complete executable code, imports, relocations,
loader spans, scene boundary, guard/vendor controls and Condemn handlers.
Offline alignment confirms zero intersections with 50 anchors in 16 profiles.
The seven-span reviewed loader resolves exactly. This is offline compatibility
evidence; successful login and server behavior still require live verification.

Native and host admissions add only the exact reviewed original/prepared keys
appropriate to each reader. Vendor and crest operations still reject original
unprepared files and unknown hashes. Affix qualification remains separate; no
new-client token is silently promoted to a known disposable affix.

Native 1.8.25 / host 0.3.36 includes the complete Condemn workflow from package
source 0e3f058 plus this narrow client update. The earlier staged 1.8.24 / 0.3.35
payload was never applied and is superseded for this installation. Focused host
validation passes 111 tests; the full package and actual-file native checks follow.

## Installation

New Config.wpak SHA-256: `a8e669958a2a1ce779b2743d4e951984f94f5e578ccd86a84ea43aa8621a6998`.
New CObjects.cache SHA-256: `710b54dd95be0fa6ecb43333712318ffca4bdbac9a1732f2473385655ed41cb4`.
Textures and renderer assets have no new official changes. Preserve existing
settings, renderer DLLs, DoubleFusion files, manager identity and job records.
Update the official client and Vendor Test copy together, using the prepared
executable only in Vendor Test. Keep exact backups and update launcher/package
identities consistently. No game files have been replaced at this source checkpoint.

Next: validate the exact-source package, prepare rollback and dry-run the combined
client/extension migration, apply with Shadowbane closed, then verify user login
and the selected-building Condemn workflow. Do not launch the game automatically.
Source branch: codex/guard-upgrades, for integration through codex/vendor-rolling
and codex/native-lifecycle-hardening to reviewed main. No merge is implied.


## Installed and verified

Exact package source `f534588623745878aadaeab0bd54b6143815351b` is installed in
the isolated test VM. The original source checkpoint `92e99e4` was followed by
a native whole-file byte-array identity correction; the actual original/prepared
image, relocation and mutation checks then passed. The earlier failed package
was not installed.

The final package passed 3,228 Python tests (18 skips), Ruff, both native profiles'
required tests, actual-file bindings, 63 movement IPC tests per profile, and
installed wheel/entry-point/panel/contract checks. All 61 artifact hashes and the
archive integrity were verified. The two known graphics transparency diagnostics
remain deferred in each profile; this is not graphics or live Condemn acceptance.

- Archive: `2b0cdb5f89357c9ec3f3c747671e7d78e10245192f478b4d55ed01d80ad1cc70`.
- Full DLL: `af33485a8cc7d139be998723b12665c48470d097cfc7452aa837719cea11260d`.
- Host wheel: `947b086a63f0f96f8fd1a9764def837097f393390fd645e6ea33222a37baa341`.

Shadowbane was observed closed before preparation and again before applying.
The idle manager and its verified wrapper were stopped; no game was terminated.
The migration dry run passed, then updated three official-client files and four
Vendor Test inventory entries (prepared EXE, two assets, extension DLL). Eleven
verified rollback files cover both clients and the extension/launcher metadata.
All 8,543 retained settings and history files matched before and after the new
manager started. Native DLL version 1.8.25.0 and host/source identity are verified.
The authenticated manager is healthy, with no bound client or active job.

The existing WonderBane Vendor Test shortcut still starts the same isolated
runtime. The WonderBane Vendor Dashboard shortcut was backed up and retargeted
from its older host 0.3.31 interpreter to 0.3.36. The other desktop shortcuts were
not changed. The game remains closed for the user to launch.

Superseded 1.8.24/0.3.35 staging and private failed-build/rollback evidence remain
retained locally and must not be applied. No client binaries, credentials or
captures were published. Source and this handoff are pushed on codex/guard-upgrades;
normal main remains clean. Integration is still through vendor-rolling and
native-lifecycle-hardening to reviewed main; no PR or merge has occurred.

Completed: official client patch, matching extension/host, preserved records,
manager activation and shortcut verification. Next: user login through WonderBane
Vendor Test, then combined selected-building Condemn preparation/execution and
pause/resume qualification. No automatic Condemn action was performed here.


## Subsequent startup repair

A later launch stopped before creating the game because package verification
reported changed Config/ArcaneLanguage.cfg. Inspection found all 343 bytes were
zero, with SHA-256 `f2d162d2e45635314786973be896bd5a389a6c993b5c5933be55b26f13f587b4`.
The ordinary client and previous runtime both retain the intact language file,
matching the packaged hash `b56fb71e2591b7c138ffc1275ca2433bac83b7fea3c4f0892e355d73968116ac`.
The cause of the zero-filled write remains unknown. Windows Defender is enabled;
no recent detection was found. No antivirus setting was changed.

The corrupt copy was preserved, then that one file was restored from the exact
matching ordinary-client copy. ArcanePref and character settings were intact and
were preserved. No runtime-policy allowlist, package evidence, source binary or
host version was changed; the verifier correctly rejected corruption.

The existing Vendor Test launcher then passed full package verification and
started the reviewed client with extension 1.8.25. Its text-fixed Mesa settings
remain LIBGL_ALWAYS_SOFTWARE=true, GALLIUM_DRIVER=llvmpipe and
MESA_EXTENSION_MAX_YEAR=2001, with GL/GLSL overrides cleared. The game remained
responsive on a subsequent check. The manager restarted successfully, attached
one client and had zero active operations. Repair/startup evidence and the damaged
file remain private under the runtime's repairs/language-config-20260922 folder.

Startup repair is complete. Next: user login and the pending selected-building
Condemn live qualification. No hostility or spending operation was dispatched.
