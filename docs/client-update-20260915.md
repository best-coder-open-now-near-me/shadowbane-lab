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
