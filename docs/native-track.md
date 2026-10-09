# Native Hunt Foe awareness

## Current scope and delivery

The user selected **Hunt Foe** for Umbra's incoming-player awareness on October 9.
The source lane is `codex/native-track-awareness-20261009`, based on main `7646af6`,
with main as its integration destination. Automatic Track queries and the contact display
are implemented and under final qualification; they are not installed yet. The running .86/.56 runtime is unchanged.

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

## Validation and delivery todo

- Complete: learned Hunt Foe and ten-contact native HUD capture; 92 initial tests.
- Complete: copied response publication and nested-generation handling; native
  fixture and three failed-install cases, plus 31 Python publication tests.
- Complete: same-owner native query and automatic active/idle scheduling, per-character
  settings, dashboard display and independent source reviews.
- Active: combined exact-source package and hosted checks for host .87/native .57.
- Next: normal authorized merge/install, enable Umbra's saved Track intent and
  verify automatic refresh in the running game. The installed .86/.56 runtime
  remains unchanged until qualification completes.

The exact-image query probe verifies all thirteen original callsites and executes
copied native sender code with the actual Track sender callsite and shared append
observer. Its Use body, definition lookup and allocation are synthetic fixtures;
the complete category-4 Use branch is statically qualified, not yet live-qualified
by the new runtime. Private capture data and client binaries stay outside Git.
