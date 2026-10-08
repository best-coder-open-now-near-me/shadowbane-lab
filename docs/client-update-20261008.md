# Wonderbane official client update — October 8, 2026

## Delivery status

PR #105 merged the reviewed source `6c8ea10aa34d9f585a8d6d8166a1af8707687ec7`
into `main` at `500fe40df1ed5d12218368fb076c4957eefd68ce` after all 15 hosted
checks passed on that exact head. Package B54/40841b71 contains host 0.3.78 and
native 1.8.54 from the same source. Independent review and qualification passed;
installation and first-launch verification passed. Fresh native in-world readiness
passes, but the later character identity read reports `ictus`, not Umbra;
live attack and buff behavior is not yet validated. The bounded-run preflight
stopped at the existing foreground-client guard before dispatch because another
window was foreground. No gameplay was started. Before any retry, resolve the
intended character; foregrounding alone does not satisfy the Umbra identity check.

The delivery record branch is `codex/client-update-delivery-20261008`, based on
that merge and targeting `main`. Pending recovery PRs #92 and #94 remain
separate; this compatibility update does not resolve their startup/attachment
defects. Own-server work is parked at the user's request.

## Official update and exact identities

The user completed the official patcher in `shadowbane-testing`. The patcher
reports release 1.0.6; the executable's embedded client version is 1.3.38.15.
Actual executable and object-cache hashes match the fetched official manifest.
The local patcher metadata file stayed unchanged, so it is not used as proof
that the patch completed.

| Artifact | SHA-256 |
| --- | --- |
| Official manifest | `a6b33e082a99f5578af1f94ce7f1d585ec2f2c2246af8f06e389aa3eacb5fd8f` |
| Official `sb.exe` | `381e67586b3c36b8ce1dcdb824439010d373d455aa6b460b02cf44f7d58fe9e5` |
| Derived prepared executable | `e75ba188142c95a8f69a27ff8d6e83ecfcecf641cc462e0889600b5a759d7437` |
| Official `cache/CObjects.cache` | `4df20426f0809779b28a4a9769ebf94fc1a02d6598e216f3a1b199ffb08b4804` |

## Binary review

Compared with official 1.3.38.14 (`e703e7cf…`), both executables are 21,143,613
bytes and retain identical PE headers and section layouts. There are 735 changed
bytes: 734 in `.text` and one embedded version byte in `.data` at RVA `0x12dc18c`.
`.rdata`, `.idata`, `.rsrc` and `.reloc` are unchanged.

The executable changes instructions at RVAs `0x4c5d1c`, `0x4c5d6c`, `0x4c6547`
and `0x4c69e7`, redirecting to previously unused space at `0x8f8000..0x8f8378`.
Disassembly shows object timing and attachment/vector handling, including calls
to `Math.dll` quaternion rotation and the system timer. This is a real code
change, not a version-only patch. These observations describe client code;
they do not establish server behavior or a new authority to issue actions.

Independent production alignment covers 16 profiles and 51 calibrated anchors,
with zero changed intersections. All 119 SHA-qualified native probe spans remain
byte-exact and have zero changed intersections. All seven loader writes align at
their original locations, with no relocated, missing or ambiguous sites. Exact
original/prepared hashes are added to the existing guards; signature, loaded-image,
character-session, ownership and unknown-image rejection checks remain in force.
Executable probes on both candidate images passed final qualification.

## Qualification

Independent binary, host and native source reviews passed. The final package
was built using the configured project environment: 5,165 host tests passed
(39 skips), and each native profile passed 236 tests and all 138 required gates.
Each profile also passed 74 movement IPC, 86 combat IPC and 148 actor IPC cases.
All original/prepared executable probes and installed-wheel checks passed.
Independent verification checked 116 artifacts and 88 stages. The three optional
CTest binding wrappers were skipped; corresponding actual-image probes executed.
Existing selected-cue/effects transparency stretch diagnostics remain unresolved
and recorded separately, with no failed required acceptance gate.

| Qualified artifact | SHA-256 |
| --- | --- |
| Full native DLL | `1168f696e9d7b77915aa44b076dbcaec1e5c760321e13a777efa9eb2cba02b9a` |
| Host wheel | `f386d6249e68b95875c422c9b3e94880a42537ba3b0d6ce478bc5c6847b14b90` |
| Package archive | `39b23f62e4cf2f14459087c5cb5f0c998b04e398dac7a212a250e22f57f27b3a` |
| Build receipt | `1734932862c33766a6beaf91bc93034923d19d8a81ddfc3c2c92ff6a874f2897` |

The first local package attempt completed host/native checks but failed while
building the wheel because system Python lacked the build dependency. That
attempt is unqualified. The successful package above was rebuilt from the same
committed source using the existing project build environment.

## Official assets and release-note follow-up

All 211 official paths were inspected in both guest client directories. Exactly
six bot assets required replacement: `sb.exe`, `Config/Config.wpak`, and the
`CObjects`, `Render`, `Textures` and `Visual` caches. The updated normal client
matches all 209 immutable manifest entries. Two mutable DoubleFusion files are
preserved as user/runtime state. The 1,772,431,675-byte texture file is streamed
from the verified official client through one temporary replacement; no retained
rollback copy or duplicate large payload is needed.

The user supplied the release notes. They describe Archon's Blade with a white
flame both drawn and sheathed, reduced Archon health, non-initiating Mine
Commanders, siege-engine lifecycle fixes, corrected promotion lists, safer
teleport arrival locations, warehouse cap changes and a one-active-bane limit.
They also say auras visibly end on stealth, logout and unequip. These are product
notes, not server-source evidence. Connecting the new attachment/timing code to
the sword effect is a plausible inference, not a proved identification.

After launch, prioritize native aura observation across stealth/logout/unequip,
position/session transitions after teleport, and explicit target policy for Mine
Commanders. Sustained PvE/buff renewal and pending recovery PR consolidation are
still unfinished; this patch qualification does not claim live gameplay success.

## Installation

The fresh baseline had host .77 source `60988fa`, native .53/package source
`490cba7`, both clients and manager stopped, and 2,861,375,488 free bytes. The
32-member payload was 31,624,328 bytes; required working space, including the
single large atomic replacement, was 1,949,010,331 bytes.

Preparation verified all 467 installed module files. Apply changed six official
files plus the DLL, verified the complete client package and 10,063 preserved
files, and updated launcher/dashboard identities. Activation started healthy,
unbound manager PID 2560; only the expected worker dispatch permit changed to
revoked/unbound. All five shortcuts and the launcher's read-only preflight passed.
No deployment rollback copies were created.

The first launch produced PID 5608, creation `134359570353507178`, HWND 983522,
with the exact DLL `1168f696…` loaded. A read-only VM screenshot subsequently
confirmed the login screen. Initial passive readiness correctly remained
unavailable at login/loading, with no observable local player; it is not an
in-world combat acceptance result. After login, fresh readiness observed a live
readable player, fresh ready movement in scene 5, actor-action capability, and
no pending cleanup. No gameplay actions had been sent at this checkpoint.

The running core transaction used reviewed payload plan `b8bec074…`. A separately
reviewed retirement helper added a scheduled-task reference check after staging;
all preparation/apply/activation/launch bytes stayed identical. Its updated
helper is staged independently; the in-flight core plan was not rewritten.
Installer review covered 39 offline tests and 10 PowerShell parses.

Obsolete runtime retirement completed after exact inventory, process, configuration,
shortcut and scheduled-task checks. Removal reclaimed 51,006,279 guest bytes and
5,688,888 host/share bytes, totaling 56,695,167 bytes. Current processes and user
data were preserved. No cleanup todos remain. Recover software from committed
source and official assets; preserve settings/jobs/journals in place. See [deployment policy](deployment-policy.md).

Private binary/disassembly and deployment evidence lives under
`artifacts/client-update-20261008`; client binaries and captures are not published.

## Next live check

The production invocation retains saved buff intent and native Umbra/Wonderbane
identity, uses no geometry profile, and runs a finite one-kill/90-second session
with a 60-second encounter limit. Its 120-second timer requests normal cleanup.
Twenty-four focused invocation tests and PowerShell parsing passed. The initial
PowerShell wrapper cut off Python stderr; error capture was corrected without
changing control logic. The resulting traceback identifies only the foreground
client precondition; no production run or attack was started.

## Character/window correction at 18:44 UTC

The initial readiness reader verified process lifetime, native capabilities and
local-player liveness, but did not verify the character name. Calling that result
Umbra readiness was incorrect. A subsequent native character-session read reports
`ictus` on Wonderbane in the same PID 5608. Window enumeration finds one game
process in the testing VM, with its visible, non-minimized main window behind
File Explorer. No second/headless game process or matching recent crash event
was found; the evidence does not establish why another instance disappeared.
The bounded invocation stopped before reaching its explicit Umbra identity check
and sent no gameplay actions. Do not weaken that check to continue implicitly.


## Live PvE and buffs after multi-client repair

PR #110 merged the verified launcher delivery record at `230bfe7`. The subsequent
production runs bound native **Umbra / Wonderbane**, PID 4100, creation FILETIME
134359627798514406, HWND 329000, actor key `[4050960, 53]`, scene 1. The other
client (Ictus, PID 264) was not controlled. Both invocations used native population,
object identity, action and health evidence; no geometry profile or system-message
parsing was used. Saved buff intent and the empty player attack list were preserved.

Installed host .78 source is `6c8ea10aa34d9f585a8d6d8166a1af8707687ec7`.
The separate cosmetic native overlay is
`0f808385d83c731306021b38109e623bde265be1`, DLL SHA-256
`e6dcdef161abac62b91c5275b3334c07f0a77d6755ef48c7dd950fa21689a2c7`.
The overlay delta leaves actor/combat/movement/lease and IPC guard sources
unchanged. This is not a claim that its DLL is the original B54 package DLL.

- Run `a553c5d59c114237976da1afb1b32733`: one native health-zero NPC kill,
  28.125 seconds, confirmed child cleanup, exit 0. Concoction, Precision,
  Beorc Rune and defensive stance were PRESENT. Transform was missing.
- Run `064d880f130a4e9e8626cd679a48c5ca`: two native health-zero NPC kills,
  37.515 seconds, confirmed cleanup between encounters and at the kill limit,
  exit 0. Rat Shape queued once, settled locally at 6.859 seconds, and canonical
  coverage subsequently reported all five groups PRESENT.
- Neither run reached its stop timer, received a hotkey stop, or changed the
  attack list. Fresh read-only inspection after each run found native owner NONE,
  no pending cleanup, a fresh ready scene, and Umbra alive.

The first run's missing Transform was not a failed cast. Both alternatives were
ready before Shot to the Leg entered combat mode. Their native definitions
require peace mode, and later progress reported them not ready while mode was 2.
This explanation is inferred from the native predicate and recorded mode; progress
retains generic `not_ready`, not the raw native refusal enum. The next run began
in peace mode and applied Rat Shape without a forced mode toggle or an all-buffs
barrier. There is no demonstrated Transform scheduler defect from these runs.

Private evidence remains under the diagnostics share's
`bot-production-pve-20261008-multi/production-pve-<run-id>` directories. The second
run's `production.json` SHA-256 is
`0cc792b3873948dbbe914f3b7e03be73ccdda91fd26ccc5ebf9229c3bd776f43`;
`progress.jsonl` is
`908985f4ab16c03e208fcd50e0fca7f7030d28a1a69549365a4608ad2fa462b4`.
Full captures and executable assets remain private; no fallback runtime was kept.

Next: consolidate the pending preparation-registration and worker-attachment
recovery source from PRs #92 and #94 into one qualified host-only update. Sustained
buff expiry/reuse and alternating transformations remain unverified by these short
runs; automatic PvP retaliation remains outside this acceptance result.
