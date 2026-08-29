# Primitive-loadout exploration

The exploration layer deliberately ignores Shadowbane's class tree while it runs.

A simulated character is:

```text
base numbers
+ passive tags
+ a bag of executable behavior recipes
+ a visible list of requested recipes that are not implemented yet
```

Race, base class, promotion, disciplines, equipment names, and historical build labels may remain in
`metadata` so a generated result can be turned into a legal WonderBane character later. They do not
grant, reject, or score actions inside this layer.

## Why this is the loose harness

The compiled action specification is already the primitive grammar:

- target kind, relation, range, and line of sight;
- resource costs;
- windup, active, recovery, and delivery timing;
- direct damage and restoration;
- scalar and tag changes;
- timed effects, stacking keys, and removal;
- movement;
- semantic tags and policy-facing features.

A named Shadowbane power is only one parameterized composition of those pieces. The open-build
runner selects any compiled compositions, regardless of the class or discipline that originally
supplied them.

Unsupported requested actions do not invalidate a loadout. They are placed in
`omitted_action_keys`, and every run reports the executable coverage fraction. That makes it possible
to enter a newly created toon immediately, simulate the represented portion, and fill missing
primitives later without redesigning the build format.

Action prerequisites such as a melee weapon, Stalk, or invisibility can be auto-added as mechanical
support tags. This is intentional for unconstrained discovery: selecting a recipe means selecting
the minimal state needed to exercise it. A later legality pass can ask whether WonderBane offers a
real build that supplies those requirements.

## Generate arbitrary mixes

The current bundled pool is still small, but the generator already ignores its Assassin and Warlock
origins:

```powershell
python -m shadowbane_lab.rollouts.open_builds `
  --generate 16 `
  --generation-seed 7 `
  --min-actions 2 `
  --max-actions 6 `
  --distances 15,60,110 `
  --seeds 1,2,3 `
  --output .\artifacts\open-builds.json
```

Every generated loadout receives at least one offensive or controlling recipe, then samples the
rest without replacement. Health, mana, stamina, and movement are varied over broad provisional
ranges. Every pair is fought from both sides by default.

As more power recipes are compiled, they automatically enter the selectable pool. No generator code
needs to know which class, race, weapon school, or discipline they came from.

## Add real or invented toons

A roster is intentionally plain:

```json
{
  "schema_version": 1,
  "loadouts": [
    {
      "loadout_id": "irekei-proc-live-001",
      "display_name": "Current Irekei proc toon",
      "action_keys": [
        "shadowbane.assassin.shadow_touch",
        "shadowbane.assassin.shadow_mantle",
        "shadowbane.sundancer.catlike_tread",
        "future.weapon_proc.poison"
      ],
      "health": 612,
      "mana": 418,
      "stamina": 236,
      "move_speed": 19.5,
      "tags": [
        "equipment.dual_wield"
      ],
      "metadata": {
        "race": "irekei",
        "promotion": "assassin",
        "discipline": "sun_dancer",
        "source": "live character snapshot"
      },
      "notes": [
        "The class labels are retained only so this mix can be rebuilt in WonderBane."
      ]
    }
  ]
}
```

Run it together with generated strangers:

```powershell
python -m shadowbane_lab.rollouts.open_builds `
  --roster .\configs\my-toons.local.json `
  --generate 24 `
  --generation-seed 19 `
  --output .\artifacts\my-toons-vs-open-pool.json
```

`configs/*.local.json` is already ignored by Git.

## Interpretation

This mode answers discovery questions:

- Which primitive combinations create coherent strategies?
- Which recipes are never chosen?
- Which mixtures expose a missing engine primitive?
- Does a strange generated kit outperform familiar templates?
- Which promising behavior bag should be translated into an actually legal WonderBane toon?

It is not a legality validator and it is not yet a balance oracle. A separate adapter can later map a
promising primitive bag back through race/class/discipline/equipment availability and report the
nearest buildable toon.
