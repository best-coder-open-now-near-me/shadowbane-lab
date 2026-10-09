# Native Hunt Foe awareness

## Current scope and delivery

The user selected **Hunt Foe** for Umbra's incoming-player awareness on October 9.
PR #133 merged into main `9523d0e7aa973e1529c07d950c7cf64e3836eaf2` after all
15 hosted checks passed at reviewed head `7593d06`. Automatic native refresh and
the contact display are implemented and qualified as host .87/native .57. The
qualified .87/.57 runtime is installed, its manager activation verified, and the
game relaunched with the exact DLL. Automatic-query live acceptance awaits login.

The first source checkpoint supplies a durable learned-skill resolver and a passive
native contact reader. These are observation components for the full shared-worker
implementation, not a second bot or a temporary hotkey path. Track is independent
of buff coverage. The previous conc interruption exercise is parked by user request;
normal PvE and Track work take priority.

## Learned skill and routing

`resolve_learned_tracking_ability(session)` resolves the current character's Hunt
Foe definition, learned rank and native power ID. It requires category 4, target
mode 4 and delivery 0. The generic combat resolver still rejects category 4.
The user-confirmed live Umbra definition on the reviewed .16 client is Hunt Foe,
internal name `SCT-007`, power 429578587, rank 40. The implementation resolves the
current learned record instead of using that observation as permanent authority.

At native Use RVA `9bbf0`, ordinary categories 0/1 route through the combat power
path. Category 4 with a zero native key follows `9be38..9bed2`: constructs the
`ArcTrackingListMsg` through `3b2650`, sets message `+60` to the power ID, and sends
through the existing native sender `7f4da0`. This is a tracking query, not a normal
self power or an effect application. Its outbound queue receipt and inbound list
response must be distinct states.

## Native result model

Qualified against exact original .16 SHA-256
`a145ef491341e5107ec064de876d97f0e9c6ebbde2520d6509b4a3b47a7d825a`
and prepared .16
`1a5a9fd59da8255a3c98e16e1e8ff9a415c0921b4189583158c559ad2594360c`.
All 16 inspected result/HUD spans match between those images.

| Native object | Observed layout |
| --- | --- |
| Game root | pointer RVA `16a7bfc`, vtable `1174884`, world state `+64` = 2 |
| Active HUD stack | root `+20`; doubly linked sentinel nodes containing next/previous/HUD |
| Track HUD | vtable `116fb58`; selector `+3b8`; list `+3c0` |
| List | vtable `116acf0`; owner HUD `+3bc`; row vector `+408/+40c/+410` |
| Row control | vtable `116aebc`; HUD owner `+3bc`; list owner `+458`; entry `+44c` |
| Track entry | vtable `116fcc0`; kind `+8` = `1c`; native key `+10`; native name `+20` |

The reader borrows the exact character session, bounds reads and ownership walks,
and rechecks every captured block and the character binding. It reads client
objects, not screen text or system messages. It does not inspect selected targets.
A contact name/key is not an attack instruction or evidence of hostility.

There is no qualified distance in the Track row. Nearby world objects can later
supply positions when their exact keys match. Unknown row fields and the separate
tracking-arrow response are not interpreted as coordinates.

`ArcTrackingListMsg::Process` at `3b2b30` initializes the tracking window, clears
its existing rows and copies the response selector and rows. The decoded row
vector is at `+64/+68/+6c`, with 64-byte rows. The current stored HUD has no
qualified query serial or timestamp. Therefore a passive snapshot reports loaded
contents and unknown response age; repeated identical results and an empty list
cannot establish a fresh response by value comparison.

Private reproducible static evidence is under
`artifacts/track-20261009/static/` (not committed): `findings.txt`,
`qualification.json`, `disassemble_track.py`, and `qualify_spans.py`.
The initial live read confirmed the exact learned definition and the absence path.
The user then used Hunt Foe in town; the reader captured ten native player
names/keys with selector 429578587. The earlier use away from players had no
loaded HUD. Native lookup confirms root +20 is the in-world owner; no alternate
persistent result cache is qualified. That earlier absence does not establish
an empty response or a failed skill use.

## Automatic refresh and presentation

Saved per-character settings schema 3 adds `tracking.enabled` and a ten-second
request interval. Existing settings migrate with tracking disabled. The ordinary
`client pve-settings --process-id <pid> --tracking enabled` command resolves the
current learned Hunt Foe before saving intent. Track runs through the existing
actor owner during PvE and the same idle preparation service between operations,
including when buffs are disabled. There is no second producer or worker.

A dedicated actor Track action carries no target context or buff selector.
The exact native category-4 route has no ordinary cast reuse/recovery check;
request spacing is scheduling policy, not an invented skill cooldown. Known queued
casts may continue while Track queries run. Separate query receipts preserve
existing combat receipts and pending follow-through. Unknown outcomes poll the
original command; a query never cancels a cast or replays an uncertain request.

Native Decode/Process observations publish copied rows with processing generations,
scene/actor identity and native ticks. Entry generations survive nested returns.
Only a complete newer returned Hunt Foe response provides current contacts. Initial
retained history, unavailable capture and old lists cannot become a fresh empty
result. The display expires contacts after two refresh intervals and labels them
as last seen. No query/response nonce or server-origin character session is claimed.
Tracking awareness is not attack permission.

The existing manager progress and idle-service projections show contact names,
response age and status independently from buff coverage. Contact names use text
nodes. Worker/process replacement, paused/stopped ownership and expired observations
remove currentness. Status storage accommodates the bounded 256-contact publication.

## Qualification and delivery

Exact runtime source `a7b210cb014d9380daa34eeb42d9d0382ca4e44c` on
`codex/hunt-foe-release-20261009` combines the merged Track source with the
previously installed graphics composition. All installed graphics-only files
were preserved; the shared build/test lists retain both graphics and tracking.

The package passed 5,849 host tests with 40 optional skips, 253 full-profile and
249 diagnostics-profile native cases. Three generic private-image cases per
profile are covered by the explicit original/prepared image probes. Both profiles
passed movement/combat/actor IPC counts of 74/86/208 without skips, including the
real copied Track frame. Six installed-wheel desktop startup cases passed; the
real Windows worker handshake is retained with verified source equivalence across
the final test-only correction. Independent verification checked all 136 artifacts,
108 stages and 484 installed host modules. The two existing graphics transparency
diagnostics remain separately recorded and are not claimed fixed.

| Qualified artifact | SHA-256 |
| --- | --- |
| Acceptance package | `662b79825a84c99aff853247c5dc96b78256f09d85cd36de522297883378a025` |
| Builder receipt | `700830eda54a9cdb77b7681927af23ab4bafec33498cd48ec1850a21fe099318` |
| Independent verification | `a3d93e2c052a2e19222c77063967e141144ddb2f57a0c0192e9e277a76de00af` |
| Full native DLL | `d2ef2d9526c0410e5437959883bb574c8f801765aecd35a5aab21bee6dfa4eec` |
| Host wheel | `d6f368d2d6c448af3c9ee1a26c628d902fbcb21b9bb17d1ff1d72836729b136b` |
| Installation plan | `d5d27aa3bcb7cff676fceb484b9039b9323022c2a9b319b1f9bebbda1485af1d` |

The reviewed installer changes one client inventory member, the DLL, plus its
package/launch provenance and host references. It preserves settings, jobs,
journals, the multi-client launcher and lifetime receipts in place. No rollback
copies are created. A fresh baseline verified the active .86/.56 runtime and
9,500 retained records; preservation is recaptured at the actual stopped boundary.
Disposable files from failed package attempts were removed (299,554,190 bytes),
while their logs and compact receipts remain.

- Complete: native learned definition and ten-contact town capture, source reviews,
  shared-owner scheduling/display, package qualification, PR #133 merge, installation,
  manager activation and exact-DLL game launch (484 modules verified).
- Active: enable Umbra's saved Track intent after login and verify automatic refresh.
- Next: integrate the closed-game cleanup source fix in PR #135; Track remains
  awareness only.
- Follow-up: closing the old game left its worker waiting indefinitely for native
  preparation cleanup after the manager removed its binding. The owner adapter
  checked original-process retirement only when cleanup raised, while the actor
  channel converts mapping failures into unconfirmed results. Exact game-lifetime
  retirement must also resolve those unconfirmed results; an inaccessible or still
  live original process must remain unresolved. During installation, the confirmed
  dead-game worker and launcher were retired by exact retained handles; their
  journals and settings were preserved.
- Follow-up: the prior .86 continuous PvE run stopped after five kills and 4,853
  steps with `native movement renewal failed: NativeActionChannelBusy`. Idle buff
  upkeep recovered and remained healthy. The saved error drops the underlying
  renewal reason; the final 1.438-second trace gap suggests possible scheduling
  delay but does not prove lock contention, expiry or ownership loss. Preserve
  those distinctions and inspect renewal scheduling before changing recovery;
  an expired/lost lease must not be silently reacquired.

Installation preserved 9,539 records with zero exclusions. The original installer
mistakenly treated its intended `reviewed-launch.json` update as retained user data.
Completion repair `172b29ff` verified the exact partial state and planned config,
projected only that provenance row, and completed without replaying native writes.
The original retained manifest and before/after row hashes remain as evidence;
all other 9,538 inventory rows were unchanged at that boundary. Fifteen focused
repair tests and independent review passed.

The manager started once. Its original verifier incorrectly required configured
slots while the closed client produced an empty visible-instance inventory.
Verification-only correction `ef9574d0` accepts that exact closed-game state,
requires no workers, and preserves manager identity and all data checks; 67 tests
and independent review passed. Final activation verified 484 host modules, the
same 9,539 records, and only two typed generated changes (startup and dispatch
permit). The original sealed payload stayed unchanged. The reviewed launcher then
verified the new game's loaded DLL against the qualified hash above. No rollback
artifacts were created. The public cleanup fix is `7161148` on
`codex/closed-game-preparation-cleanup-20261009`, targeting main through PR #135;
53 focused tests and independent review passed, with hosted checks pending.

Verified retirement removed the obsolete .86 host (2,151 files), ten staged
wheels and the old staged .56 DLL: 58,981,049 bytes across twelve exact paths.
All twelve paths are absent; the same new game and manager lifetimes, healthy
worker and qualified DLL remained intact afterward. Metadata, diagnostic logs,
settings and journals were preserved. Retirement receipt SHA-256 is
`cfa6a5d4ca49c82ddb234e1ebdd4a7bd346da274d2500d3c99e664364220c21a`.
The merged Track source branch was retired locally and remotely after confirming
its exact tip `7593d06` is retained in origin/main. The normal checkout stays clean
on main; the current release and delivery branches remain published for continuity.

The exact-image query probe verifies all thirteen original callsites and executes
copied native sender code with the actual Track sender callsite and shared append
observer. Its Use body, definition lookup and allocation are synthetic fixtures;
the complete category-4 Use branch is statically qualified, not yet live-qualified
by the new runtime. Private evidence is under local `artifacts/track-20261009`,
`artifacts/b57/d99deb82` and `artifacts/bot-deploy/20261009-track87`; captures and
client binaries are not part of the source delivery.
