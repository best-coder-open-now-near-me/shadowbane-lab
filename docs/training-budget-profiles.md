# Training-budget profiles

The optimizer distinguishes three different facts that older build checks treated
as one number:

1. how many training points a character identity has earned by a level;
2. the minimum possible cost implied by selected ranks;
3. the exact train cost of every selected skill and power.

Only the first fact is currently source-pinned for one population. The second is
a conservative rejection boundary. The third remains unresolved.

## Bundled schedule

`wonderbane.non-human.rogue.v1` applies only when the reviewed calculator says
that the base class is Rogue and the race family is not Human.

| Levels | Trains per level | Cumulative at band end |
| --- | ---: | ---: |
| 2–10 | 4 | 36 |
| 11–59 | 10 | 526 |
| 60–64 | 5 | 551 |
| 65–69 | 4 | 571 |
| 70–74 | 3 | 586 |
| 75 | 2 | 588 |

The profile is not extrapolated beyond level 75. Human bonus trains and the
Fighter, Healer, and Mage schedules are intentionally left without a profile.
An unsupported identity therefore receives `budget_points: null`; it does not
inherit Rogue values or a guessed generic schedule.

## Cost evidence

Every selected skill or power receives a `TrainingSelectionCost` record.

- Power rank currently contributes `displayed_rank` as a lower bound. This can
  reject a build whose powers alone already exceed a verified earned pool, but
  cannot prove that a build fits after real train costs are known.
- Displayed skill percentage is not treated as spent training points. Its
  minimum is zero and its exact cost is unresolved until a reviewed cost curve
  or character-sheet observation is added.
- Exact costs have a separate evidence state and cannot be supplied on a
  lower-bound or unresolved record.

The audit exposes both `lower_bound_remaining` and `exact_remaining`. The latter
stays null until every selected cost is exact.

## Search integration

`TrainingBudgetBackedLegalityGate` retains the existing equipment, hand-slot,
and named item-skill checks, then attaches the typed training audit. It bypasses
the older unconditional Rogue shortcut so Human Rogue and unsupported
identities cannot accidentally use the non-Human schedule.

The Irekei Assassin MAP-Elites runner uses this gate for seed builds, opponents,
mutated children, and evaluator evidence. The archive remains candidate-grade
because:

- power costs are lower bounds rather than exact costs;
- displayed skill costs remain unresolved;
- current equipment values are historical candidates;
- selected power rows still use reviewed source-revision overrides.

Future exact cost records can promote the audit without changing the distinction
between earned budget, minimum spend, and exact spend.
