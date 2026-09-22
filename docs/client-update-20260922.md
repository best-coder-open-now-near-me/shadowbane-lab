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
