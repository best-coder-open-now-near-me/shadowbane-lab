# Server-side gameplay migration

Current direction, October 7, 2026: build our own authoritative server. Further
client-circumvention bot work and its deployment/test loop are superseded by this
migration. Preserve useful source and diagnostic evidence; do not require the
pending harness PRs to merge before server development can proceed.

## Ownership and starting point

- **Continue PvE/PvP bot work** owns policy migration, authoritative command/event
  boundaries, combat/buff behavior and regression scenarios.
- **Find Wonderbane fix notes** owns server source/base selection, bootstrap,
  Wonderbane fix inventory, and the controlled client distribution baseline.
- Lab integration destination is `main`; start from refreshed `origin/main`.
  This plan starts from `cdaafb234cfe324cc1c750c77102cfcc76552f50` on
  `codex/server-side-migration-20261007`. It is a source mapping and implementation
  plan, not an implemented server adapter or a successful server launch.
- Initial bootstrap source is now `bafb48fe14e5356a64137954cf2d79205835a204`,
  recovered from the pinned MagicBox image. The setup lane's
  [PR #97](https://github.com/best-coder-open-now-near-me/shadowbane-lab/pull/97)
  publishes the source/database/library pairing and successful Java compilation.
  Database import, server startup and client compatibility remain untested.
  Bootstrap startup must preserve the source pin: the image's default scripts
  fetch and pull a moving branch. This source mapping does not run those scripts.
- Earlier inspected `master` revision `3649c629b709c67625a09150a3752107f4b873cc`
  remains historical context. The newer `9866632` candidate requires data and
  dependencies absent from the inspected image and is not a drop-in upgrade.
  The service map below has now been rechecked directly at `bafb48fe` using Git
  objects; the canonical server checkout and source export remain unchanged.

The existing .14 Wonderbane client is the user's chosen distribution starting
point. Its identity does not establish compatibility with a selected Magicbane
server/database. The other lane owns that work. We do not have original client
source; rendering, UI and client engine fixes may still require client changes.

Server code now lives in the private
[shadowbane-server repository](https://github.com/best-coder-open-now-near-me/shadowbane-server).
Its initial shared `main` is exactly `bafb48fe14e5356a64137954cf2d79205835a204`,
with complete upstream ancestry and unchanged MIT attribution. The tracked local
checkout is `E:/Projects/shadowbane-server`; `codex/shared-gameplay-services` owns
implementation there. Its documentation checkpoint `22521f45872ab989fcea78db4ca8e76b7df3ee3d`
is published in [server PR #1](https://github.com/best-coder-open-now-near-me/shadowbane-server/pull/1).
No Java behavior is changed by that checkpoint. The lab remains the research and
policy-testing destination; bootstrap builds the same pinned server source.

## Reuse, port, and retire

| Existing work | Server destination |
| --- | --- |
| `protocol/model.py`, codec, validation and schema | Reuse semantic observation, legal-action, decision and event vocabulary. Extend only for concrete server requirements; it is not yet a wire-compatible Java API. |
| `protocol/adapters.py` | Reuse the interface idea. Current implementation is a recording adapter, not a connected authoritative adapter. |
| `pve/controller.py`, `pve/preparation.py`, `pve/buff_intent.py` | Port targeting, recovery, optional opener, missing-buff and alternative-form behavior. Remove native process/scene/key/publication and receipt assumptions. These modules are not drop-in server AI. |
| `rollouts/`, `optimization/`, `sim/`, `combat/` | Retain policy exploration, deterministic scenarios and reference formulas. The production server and chosen content are authoritative; simulator gaps are not gameplay rules. |
| Equipment, progression, power and world-data importers | Reuse catalogs, provenance and tooling after mapping to the selected server database. Client tokens, item templates and server IDs must not be assumed interchangeable. |
| Native attack/cast/queued-skill discoveries | Convert into server behavior tests and action lifecycle semantics. Never equate UI selection with an in-flight action's bound target. |
| Client memory polling, action IPC, ownership leases, DLL packaging and foreground/window constraints | Retire as requirements for server bots. Preserve historical source; do not extend these mechanisms to implement new server gameplay. |
| Client rendering/UI fixes and protocol compatibility checks | Keep where actually needed by the controlled client. Server ownership does not remove client engine defects. |

All lab paths above are under `src/shadowbane_lab/`. Keep ordinary server unit,
integration and client compatibility tests. Retiring circumvention harnesses does
not mean losing regression coverage.

## Durable ownership boundaries

The intended flow is:

```text
player packet -> authenticated actor command ---+
                                               +-> shared gameplay admission/execution
server AI policy -> server actor command -------+          |
                                                          v
                                           authoritative state and lifecycle events
                                                          |
                                             client replication / policy observations
```

Start with an in-process Java server AI/controller using shared domain services.
Do not introduce a remote policy service, synthetic client connection, or new
network protocol merely to preserve Python runtime code. Python remains useful
for offline policies, data and comparisons. Add an external policy transport only
when a concrete use requires it.

The server owns entity lifetimes, controller/session association, actual attack
and cast targets, queued skills, inventory consumption, reuse timers, effects,
stance, damage, death and respawn. A policy reads an appropriate observation and
submits intent. It does not mutate health, timers, effects or database rows to
simulate successful gameplay. Bot and player actions share range, resource,
cooldown and targeting validation; actor-specific rules remain explicit.

Commands must be executed under the selected server's gameplay scheduling and
concurrency rules. Revalidate actor/target lifetimes at execution and scheduled
follow-through. Use server-owned lifetime/controller identifiers, not PID, HWND,
client pointer tokens, or object name alone. Human control of a bot-controlled
character changes controller authority without arbitrarily cancelling valid
in-flight casts; actual action interruption follows game rules and explicit intent.

An accepted request is distinct from queued, started, applied, completed,
interrupted and rejected outcomes. Emit structured outcomes where state actually
changes. Retaliation uses source/recipient identities from authoritative combat
events associated with current entity/controller lifetimes, rather than system
messages or the selected object. Packet/session authentication remains relevant
for players, but an internal server actor does not need a fabricated client session.

## Verified source seams and required extraction

At bootstrap server revision `bafb48fe14e5356a64137954cf2d79205835a204`:

- `src/engine/net/client/ClientMessagePump.java` routes player action messages
  to `PowersManager.usePower` and `CombatManager.setAttackTarget`.
- `src/engine/gameManager/CombatManager.java:setAttackTarget(AttackCmdMsg,
  ClientConnection)` obtains the session player, checks message source identity,
  resolves the target, records combat target, enters combat and invokes
  `AttackTarget`. `AttackTarget` schedules weapon attack jobs. Calling it directly
  is not a replacement for the complete command admission path.
- `src/engine/gameManager/PowersManager.java:usePowerA` mixes connection/player
  lookup, learned-power/reuse/mode checks, target and resource handling, scheduling
  and outbound messages. `useMobPower` is a separate existing mob entry point.
  Factor shared behavior while retaining deliberate player/mob differences.
- `src/engine/jobs/DeferredPowerJob.java:attack` consumes the pending player
  weapon power after its applicable range check and invokes the deferred power.
  `CombatManager` integrates it with hit/miss, hand and special dual-wield paths.
  A miss may clear a requires-hit skill; some special powers are retained for
  the other hand. Preserve these distinctions and test expiry/range failure as
  well as a successful hit. Do not replace them with an unconditional consume.
- `src/engine/net/client/handlers/ObjectActionMsgHandler.java` contains the
  consumable path (including potion action case 8), target resolution, charge
  checks and item consumption. Extract item-use admission here alongside learned
  powers; calling power application alone would omit inventory behavior.
- `CombatManager.handleRetaliate(AbstractCharacter, AbstractCharacter)` already
  receives victim and attacker objects and handles player, pet and mob responses.
  Reuse and refine its explicit conditions; do not build a second automatic
  retaliation loop or infer the attacker from client messages. Policy/controller
  integration must avoid duplicate actions from existing retaliation behavior.
- `PowersManager` owns recycle jobs, power execution and effect removal functions.
  Do not treat low-level `runPowerAction` as a public admission API.

These are concrete extraction locations, not proof that this historical revision
already implements the desired Wonderbane behavior. Do not create a second combat
engine next to them. Separate transport decoding/replication from gameplay services
within the production base selected by the setup lane.

## First complete server slice

Implement one server-controlled actor through the shared gameplay services:

1. Apply and refresh concentration potion, Precision, Beorc rune, one eligible
   transformation, and defensive stance when missing. Resolve content from the
   selected database; preserve inventory costs and actual skill restrictions.
2. Represent potion activation and delayed effect application separately so a
   pending application does not cause duplicate consumption. No specific buff
   ordering or overlapping animation requirement was requested.
3. Treat Rat Shape and Skree'ekt Shape as alternatives. Choose an available one
   when coverage is absent; derive duration and reuse from server content rather
   than assuming the observed timing relationship is universal.
4. Queue Shot to the Leg before ordinary attack when legal and available. A queued
   skill consumes on the appropriate attack. An unavailable optional opener must
   not prevent an otherwise legal ordinary attack. Establish required combat mode
   through gameplay services; stance eligibility follows the chosen rules.
5. Preserve a cast/attack's own target across selection changes. Do not wait for
   an unrelated existing projectile to land just to begin bot decision-making.
6. Follow attack, damage, death, cancellation, buff expiry and recovery through
   authoritative events, including effect removal on death and missing inventory.

Acceptance is a direct server integration scenario with controlled actors and
clock/scheduler, then a client-visible compatibility pass. Exercise cooldown
rejection without duplicate resource spend, delayed potion application, form
alternation, queued-skill follow-through, range failures, cancellation, death,
respawn and stale queued work after controller/entity replacement. No nearby human
opponent or manual game-window setup is needed for those domain tests.

Next extend the same slice to controlled PvP and retaliation using authoritative
hostility/damage events and normal target legality. Shared player/NPC rules should
be tested together; expected differences belong in explicit actor rules.

## Parallel work and continuity

- [x] Coordinate ownership with Find Wonderbane fix notes.
- [x] Map actual lab reuse and historical server service entry points.
- [x] Identify a coherent bootstrap source/data/library set in the setup lane
  and remap service boundaries directly against its pinned source.
- [x] Establish the private server repository and tracked development checkout,
  preserving the pinned shared source and upstream history.
- [ ] **Active:** implement shared gameplay admission plus the complete
  buff/combat slice in the server repository.
  Bootstrap runtime/login qualification proceeds in the setup lane; compilation
  and source work do not require pretending those live checks already passed.
- [ ] Add controlled PvP/retaliation and client-visible compatibility validation.

Client follow-on PRs #92 (preparation/stop reasons), #93 (offline hostile
participant probe), and #94 (worker activation) remain preserved source drafts,
not dependencies for this migration. The already-pushed historical deployment
record on `codex/host-cleanup-deployment-20261007` also remains separate. Do not
resume their old live qualification todos automatically or discard their evidence.
No runtime, game settings, VM or deployment is changed by this plan.
