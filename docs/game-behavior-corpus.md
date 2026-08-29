# Shadowbane behavior corpus and fidelity program

Simulation results are meaningful only when they name the game implementation and era they
attempt to reproduce. “Shadowbane behavior” is not one undifferentiated ruleset: retail changed
over years of patches, public emulators implement particular revisions with incomplete deployment
data, private servers intentionally diverge, and the WonderBane runtime may not match any public
description exactly.

This document defines the research system used to collect those distinctions without flattening
them into simulator folklore.

## Deliverables

The first corpus lives in:

- `research/shadowbane-behavior-corpus-v1.json`: profiles, evidence sources, normalized claims,
  contradiction groups, compile decisions, validation requirements, simulator bindings and
  coverage status.
- `schemas/behavior-evidence-v1.schema.json`: the machine-enforced format.
- `tests/test_behavior_corpus.py`: schema, reference, conflict and fail-closed checks.

The seed contains 5 target profiles, 23 source records, 28 behavior claims and 16 coverage
domains. It is deliberately a beginning, not a declaration that those 28 claims are the whole
game.

## Named behavior profiles

| Profile | Purpose |
|:---|:---|
| `retail-final-24.3` | Historical baseline for the final official retail patch dated January 7, 2009. |
| `magicbane-ab96cfc` | Exact public MagicBane server implementation pinned to commit `ab96cfcda4e983dd7fc1fc205205810f11ddd3de`. |
| `wonderbane-observed` | The actual client/server environment used for controlled differential observations. It remains pending until binaries, data and server identity are fingerprinted. |
| `sbe-2015-1.5` | A later emulator dialect whose Patch 1.5 must never be confused with retail Patch 1.5 or the final retail rules. |
| `reference-lab-v1` | The intentionally simplified local simulator model and reviewed approximations. |

Profiles do **not** inherit mechanics automatically. A claim supported for one profile may be
copied to another only through an explicit, separately reviewed claim. This prevents an old retail
patch note, a MagicBane implementation detail and a custom server balance change from silently
becoming the same rule.

## Evidence roles

There is no single universal trust ranking because different evidence answers different questions.

1. **Observed runtime traces** establish what the exact target environment actually did under a
   controlled fixture.
2. **Exact implementation plus matching deployment data** explains how that result was produced.
   Public server code without its concrete power/effect rows is incomplete.
3. **Official patch material** establishes intended changes and era boundaries, but may not prove
   every implementation detail or later regression.
4. **Pinned community reconstructions** preserve formulas, power tables and edge-case descriptions
   that may no longer exist elsewhere. They remain secondary evidence and can contradict one
   another.
5. **Alternate-server notes** describe only the named alternate profile.
6. **Reviewed lab models** are temporary executable approximations. They cannot promote themselves
   into historical fact.

Every remote source must identify an immutable revision where one exists. Mutable pages are
recorded as pending until snapshotted and hashed. The corpus preserves source limitations and
whether acquisition can be automated.

## Claim lifecycle

A behavior enters the simulator through the following path:

1. Acquire or pin the source.
2. Record its target profile, era, revision and limitations.
3. Extract a small atomic claim rather than copying a whole page into prose.
4. Normalize its parameters, preconditions and affected simulator paths.
5. Attach supporting, contradicting and qualifying evidence.
6. Assign a confidence level and compile disposition.
7. Create the minimum differential fixture capable of distinguishing the claim from neighboring
   hypotheses.
8. Compile the claim, use a reviewed override, or block it.
9. Replace provisional claims when stronger implementation or runtime evidence arrives.

Confidence and compilation are related but separate:

- `confirmed` means strong evidence for the named profile.
- `strong` means converging evidence with a remaining implementation or runtime gap.
- `provisional` means plausible, but not yet safe to treat as engine truth.
- `disputed` means live evidence supports incompatible hypotheses.
- `unresolved` means the required behavior is not presently knowable or representable.

`compile` permits direct use for the named simulator binding. `override` permits a documented
approximation. `block` prevents compilation. Disputed and unresolved claims must always fail
closed.

## Why claim-level conflicts matter

The initial pass already found an important example. One pinned Morloch formula reconstruction
describes armor piercing as a multiplicative reduction of the target's current resistance, while
another mechanics page describes a flat reduction from effective resistance. Both claims are
retained under the contradiction group `armor-piercing-semantics`; neither can compile until source
inspection or differential fixtures distinguish them.

This is preferable to choosing the cleaner-looking formula and producing convincing but
untraceable simulations.

Other seeded nuances include:

- standard effect category/rank replacement;
- powerblock and stun immunity duration and refresh behavior;
- action suppression and exceptions while stunned;
- root and mesmerize damage-break semantics;
- final-patch weapon-power range and self-powerblock changes;
- initial heal-over-time ticks under Shadow Mantle;
- invisibility break and skill-versus-spell behavior;
- natural versus casted flight and vertical combat tiers;
- movement-speed ordering and the horizontal speed cap;
- stamina exhaustion transitions;
- resistance cap/debuff ordering;
- Backstab as a next-swing modifier that bypasses passive defense;
- weapon-dependent effects dispelling on unequip;
- absorber depletion after resistance;
- powerblock checks on pulses;
- independent hit rolls for selected deferred components.

The corpus records which of these are currently safe to compile and which remain hypotheses.

## Coverage map

| Priority | Domain | Evidence | Simulator | Immediate need |
|:---:|:---|:---:|:---:|:---|
| P0 | Power metadata and progression | Seeded | Partial | Export concrete rows and pin all class/race/discipline pages. |
| P0 | Action lifecycle and cancellation | Partial | Partial | Extract action jobs and capture cast/interruption timelines. |
| P0 | Target legality, range, LOS and verticality | Partial | Partial | Inspect fail conditions and build boundary fixtures. |
| P0 | Hit rolls and passive defense | Partial | Absent | Extract combat paths and run fixed-sheet statistical tests. |
| P0 | Damage, resistance and armor piercing | Partial | Partial | Resolve ordering and the armor-piercing contradiction. |
| P0 | Stacking, dispels and break conditions | Seeded | Partial | Pairwise collision tests over pinned effect rows. |
| P0 | Crowd control and immunities | Seeded | Partial | Confirm refresh rules and add every control family. |
| P0 | Movement, flight and stamina | Seeded | Partial | Extract movement state transitions and measure displacement. |
| P0 | Stealth, detection and Backstab | Seeded | Partial | Separate activation, visibility and next-swing resolution. |
| P0 | Periodics, drains and absorbers | Seeded | Partial | Explicit initial ticks, pulse schedules and damage ordering. |
| P0 | Build-derived stats and equipment | Partial | Absent | Versioned character sheets, item data and derivation formulas. |
| P1 | Group and AoE rules | Partial | Absent | Target filters, caps, friendly fire and caster inclusion. |
| P1 | Pets and mob AI | Partial | Absent | Hate, aggro, taunt, ownership and deterministic AI scenarios. |
| P1 | Death and resurrection | Partial | Partial | Cleanup ordering and pending effects across death. |
| P1 | Client protocol and desync | Blocked | Partial | Fingerprint WonderBane and correlate semantic actions with observations. |
| P2 | Siege, buildings and world systems | Partial | Absent | Index after duel-critical mechanics stabilize. |

The machine-readable coverage rows list the exact claim IDs already associated with each domain.

## Acquisition passes

### 1. Pin implementation source

Index the exact MagicBane commit by subsystem rather than treating it as one source:

- power lookup, target checks, cast/recycle and action jobs;
- effect construction, category/rank collision, modifiers and dispels;
- hit, defense, damage, resist, expose, armor piercing and absorbers;
- movement, flight, stamina, collision and verticality;
- equipment, weapon state, skill/stat derivation and item effects;
- mobile AI, hate, pets and ownership;
- death, cleanup, corpse and resurrection;
- buildings, siege and world simulation.

The repository history must also be searchable because a current implementation can reveal when
and why a behavior changed.

### 2. Harvest historical material by revision

The Morloch wiki should be crawled by immutable `oldid`, including:

- patch history and every official patch page;
- global mechanics and formula pages;
- race, class, profession and discipline pages;
- every power table;
- skills, stats, equipment, weapon and damage-type pages;
- movement, flight, stealth, detection, crowd-control and immunity pages;
- pets, mobs, death, cities and siege pages.

Patch pages must be classified as retail, emulator or alternate-server material before claims are
extracted.

### 3. Acquire concrete data

The public MagicBane code explicitly depends on deployment data for concrete power/effect rows.
An authorized export should be snapshotted with hashes and parsed into a versioned raw layer. The
same applies to accessible WonderBane client tables and assets. No credentials, secrets or
unauthorized server data belong in the repository.

### 4. Fingerprint the actual runtime

Before calling WonderBane “MagicBane behavior,” record:

- executable and data-file hashes;
- client version strings and server identity;
- enabled patch/configuration information;
- character sheet, equipment, training and active effects for each fixture;
- window/client configuration relevant to input and observation;
- the exact test date and environment.

### 5. Run discriminating scenarios

A useful trace is not merely a duel replay. Each fixture should vary one disputed boundary and
record observations before, during and after the action. Examples include:

- rank below/equal/above for stack collisions and grounding;
- range just inside/on/outside the boundary;
- stun and powerblock with several remaining immunity durations;
- zero, absorbed, resisted and positive damage for break conditions;
- initial versus later periodic ticks;
- raw resistance below/at/above cap with several exposes;
- Backstab activation followed by miss, weapon swap, target death or delayed swing;
- cast, launch and deferred resolution separated by death or interruption;
- natural and casted flight across vertical tiers;
- stamina crossing the exhaustion threshold while attacking or flying.

Traces should emit canonical semantic events alongside screenshots or logs, not depend solely on
video interpretation.

## Repository invariants

- No mutable source may silently change an existing claim.
- No behavior crosses profiles automatically.
- Every compiled simulator field must map to one or more claim IDs.
- Every reviewed override must list the missing evidence and its replacement test.
- Contradictory claims remain side by side and block compilation.
- Source snapshots are content-addressed when licensing and access permit storage.
- Runtime fixtures record the exact build, character and environment.
- Aggregate duel results name both the ruleset profile and policy version.
- A mechanics change and a policy change are evaluated separately before being combined.

## Immediate implementation order

The next simulator work should follow the evidence dependency graph rather than simply add more
powers:

1. Effect lifecycle, stacking, dispels, break conditions and action cancellation.
2. Hit/passive-defense resolution, typed damage, resistance ordering and absorbers.
3. Movement, flight tiers, stamina transitions and movement-rate modifiers.
4. Explicit initial and periodic ticks.
5. Stealth/detection and next-swing weapon modifiers.
6. Build-derived stats, skills, equipment and actual power training.
7. Additional class powers and only then larger balance matrices.
8. Bounded look-ahead policies after the mechanics state supports meaningful planning.

The current greedy utility policy remains useful as a deterministic probe, but the corpus—not a
utility constant—decides what behavior the environment exposes.
