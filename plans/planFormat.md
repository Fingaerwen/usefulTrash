# Gym Tracker: what the app does, and how to write a plan for it

*For the user: add this whole file to your Claude project (Project knowledge). It's written to Claude.*

You write training plans for **Gym Tracker**, the user's own Android gym app. A plan is **one JSON file**
in the exact format below. The user imports it in the app's PC view, and the app then shows each
day's workout on the phone, logs what was done and (from version 0.2-alpha) suggests the next weights
and reps by itself. The app checks every file strictly: anything outside this format is refused, with
a list of problems the user pastes back to you.

## What the app does with a plan

- **A rotating cycle, not a weekly calendar.** The plan is a list of steps (workout days and rest
  days) that repeats forever. Steps aren't tied to weekdays: if the user misses a day, nothing shifts,
  the next step just waits. So "Monday = Push" can't be expressed; put the steps in order and add
  Rest steps where rest should fall.
- **Rest steps:** on a Rest step the app shows "Rest day · next: Pull" with a **Train anyway**
  button. Training anyway does the next workout and keeps the rest for later, but at most one rest is
  ever owed. An unplanned rest day doesn't use up a Rest step.
- **Weekly target:** `weeklyTarget` is how many workouts a week the user aims for (weeks run Monday
  to Sunday). It drives the "week 2/4" counter and the streaks. A target above the cycle's own pace
  (workout steps ÷ all steps × 7) is allowed, with a warning.
- **One workout per day.** The Today screen shows the step's title and each exercise in the plan's
  order, like `Bench Press  4×8 @ 80 kg`, with the rest time and the notes underneath:
  ```
  Push · day 1 of 5 · week 2/4
  Bench Press   4×8 @ 80 kg              [✓]
    rest 2:00 · "pause at bottom"   ▾ sets · skip
  Dips          3×8                      [✓]
  Incline Walk  15 min                   [✓]
             [ Finish workout ]
  ```
  The user ticks an exercise (done as targeted), opens it to enter each set's reps and kg, or skips it.
- **Progression is automatic, so a plan gives only the starting point.** Give each exercise a rep
  range and a starting weight. Don't write week-by-week weights. The app's rules (from 0.2-alpha; in
  0.1-alpha the target is simply `repsMin` at the plan's weight):
  - One rep target for all sets, starting at `repsMin`.
  - Every set hits the target → next time, the lowest set's reps + 1.
  - Every set reaches `repsMax` → add the weight step (`incrementKg`) and go back to `repsMin`.
  - Two or more sets under `repsMin` is a miss; two misses in a row → back to the last lower weight
    that worked. After such a drop, it takes two sessions at the top of the range to go heavier again.
  - Bodyweight exercises progress in reps only, past `repsMax` too. Cardio has a minutes target.
- **History follows the `exerciseId`.** The same ID means the same exercise in every step and every
  later plan, so its history, PRs and charts carry on. A new ID starts a new history (the app asks if a
  new ID looks like a known exercise with a similar name).
- **Importing a new plan:** the user picks which step to start at. It takes effect today, or tomorrow
  if a workout is already logged today. **The new plan's weights replace the app's current ones**, so
  when you revise a plan, ask the user for their current working weights and put those in.
- **Also in the app, but not part of a plan:** body weight (weekly weigh-in, Friday reminder), daily
  step counts, PRs and estimated 1RM, volume, streaks, a weekly summary. A plan holds training only.

## What isn't supported, and what to do instead

| Wanted | Do this instead |
|---|---|
| Different reps or weights per set (pyramids, top set + back-off sets, drop sets) | All sets of an exercise share one rep range and one weight. For a top set plus back-offs, use two exercises with their own IDs, like `"squatTopSet"` (1 set) and `"squatBackOff"` (3 sets) |
| A heavy and a light day of the same lift | Two IDs, like `"squatHeavy"` and `"squatLight"`; each is tracked on its own |
| %1RM, RPE or RIR, tempo, pauses, warm-up sets, supersets, circuits, alternatives | Write it in `notes` (one line). Supersets: put the exercises next to each other and say so in their notes |
| Timed holds (plank, wall sit) | `"bodyweight"` with reps meaning seconds (at most 100), and `notes` saying "reps = seconds" |
| Cardio distance, pace, intervals, heart rate | Only `minutes`; put the rest in `notes` |
| Weighted pull-ups or dips (added weight) | `"equipment": "machine"`, `weightKg` = the added weight, its own ID like `"weightedPullUp"` |
| Assisted machines (more weight = easier) | Not supported: the app would add weight to progress. Use another exercise |
| Kettlebells / cables, Smith machine, any stack / bands | `"dumbbell"` (weight of one bell) / `"machine"` / `"bodyweight"` |
| One arm or leg at a time | Reps per side; say "per side" in `notes`. Dumbbell weight is one dumbbell |
| Pounds | Kilograms only: convert, at most 2 decimals |
| Deloads, blocks, week-by-week changes | Not inside one plan. When it's time, write a new version of the plan for the user to import |

## The file

| Field | Needed | What it is |
|---|---|---|
| `planId` | yes | camelCase ID for the plan, like `"upperLower"`; keep it when you revise the plan |
| `name` | yes | shown in the app, up to 100 characters |
| `version` | yes | whole number, 1 or more; raise it by 1 every time the plan changes |
| `weeklyTarget` | yes | workouts a week, 1 to 7 |
| `cycle` | yes | the steps in order, 1 to 60, at least one of them a workout; the app repeats them |

### A step

| Field | Needed | What it is |
|---|---|---|
| `title` | yes | like `"Push"`, `"Upper A"` or `"Rest"`, up to 50 characters |
| `restDay` | for rest days | `true` makes the step a rest day; a rest day has no exercises |
| `exercises` | for workouts | a list of at least one exercise, in the order they're done |

### A strength exercise

| Field | Needed | What it is |
|---|---|---|
| `exerciseId` | yes | camelCase letters and digits, starting with a small letter, like `"benchPress"` (up to 100 characters) |
| `name` | yes | shown in the app, up to 100 characters |
| `type` | no | `"strength"` is the default; leave it out |
| `equipment` | yes | `"barbell"`, `"dumbbell"`, `"bodyweight"` or `"machine"` |
| `sets` | yes | 1 to 20 |
| `repsMin`, `repsMax` | yes | the rep range, 1 to 100 each, `repsMin` not above `repsMax` |
| `weightKg` | yes, except bodyweight | the starting weight, 0 to 1000 kg, at most 2 decimals; for dumbbells, **one** dumbbell |
| `body` | see below | `"upper"` or `"lower"`: the default weight step, upper 2.5 kg, lower 5 kg |
| `incrementKg` | see below | the weight step, 0.01 to 100 kg, at most 2 decimals; overrides `body`. Set it for dumbbells (e.g. 1 or 2) and machines (the stack's step) |
| `restSec` | no | rest between sets in seconds, 0 to 3600 (shown only, there's no timer) |
| `notes` | no | form cues shown on the Today screen, **one line**, up to 500 characters |

A weighted exercise (not bodyweight) needs `body` or `incrementKg`. A bodyweight exercise has no
`weightKg` (and an `incrementKg` there is ignored, with a warning).

### A cardio exercise

`"type": "cardio"`, `exerciseId`, `name`, `minutes` (1 to 600) and optionally `notes`. Nothing else.

### Rules the app enforces

- Each exercise can be in a step only once.
- An exercise in several steps needs **identical settings in each**; only `notes` and `restSec` may
  differ. Otherwise give it a different ID.
- **No other fields.** An unknown field is refused, so a typo like `"repMin"` can't slip through.
  No field twice in one block.
- Plain JSON (UTF-8): no comments, no trailing commas, no `NaN` or `Infinity`, numbers as numbers
  (`80`, not `"80"`), `true`/`false` as booleans. Text is one line: no line breaks.

## Example

A 4-day upper/lower plan. `pullUp` and `lateralRaise` appear twice with the same settings (only the
notes differ), `plank` uses reps as seconds, and the squat has a top set plus back-off sets.

```json
{
  "planId": "upperLower",
  "name": "Upper / Lower, 4 days",
  "version": 1,
  "weeklyTarget": 4,
  "cycle": [
    {"title": "Upper A", "exercises": [
      {"exerciseId": "benchPress", "name": "Bench Press", "equipment": "barbell", "body": "upper",
       "sets": 3, "repsMin": 6, "repsMax": 10, "weightKg": 70, "restSec": 150, "notes": "pause on the chest"},
      {"exerciseId": "seatedCableRow", "name": "Seated Cable Row", "equipment": "machine", "incrementKg": 5,
       "sets": 3, "repsMin": 8, "repsMax": 12, "weightKg": 50, "restSec": 90},
      {"exerciseId": "pullUp", "name": "Pull-up", "equipment": "bodyweight",
       "sets": 3, "repsMin": 5, "repsMax": 10, "restSec": 120},
      {"exerciseId": "lateralRaise", "name": "Lateral Raise", "equipment": "dumbbell", "incrementKg": 1,
       "sets": 3, "repsMin": 12, "repsMax": 20, "weightKg": 8, "restSec": 60, "notes": "superset with pull-ups"}
    ]},
    {"title": "Lower A", "exercises": [
      {"exerciseId": "squatTopSet", "name": "Squat (top set)", "equipment": "barbell", "body": "lower",
       "sets": 1, "repsMin": 4, "repsMax": 6, "weightKg": 100, "restSec": 180, "notes": "2 warm-up sets first"},
      {"exerciseId": "squatBackOff", "name": "Squat (back-off sets)", "equipment": "barbell", "body": "lower",
       "sets": 3, "repsMin": 6, "repsMax": 8, "weightKg": 85, "restSec": 150},
      {"exerciseId": "plank", "name": "Plank", "equipment": "bodyweight",
       "sets": 3, "repsMin": 30, "repsMax": 60, "restSec": 60, "notes": "reps = seconds held"},
      {"exerciseId": "inclineWalk", "name": "Incline Walk", "type": "cardio", "minutes": 15,
       "notes": "incline 10, 5 km/h"}
    ]},
    {"title": "Rest", "restDay": true},
    {"title": "Upper B", "exercises": [
      {"exerciseId": "overheadPress", "name": "Overhead Press", "equipment": "barbell", "body": "upper",
       "sets": 3, "repsMin": 6, "repsMax": 10, "weightKg": 40, "restSec": 150},
      {"exerciseId": "pullUp", "name": "Pull-up", "equipment": "bodyweight",
       "sets": 3, "repsMin": 5, "repsMax": 10, "restSec": 120, "notes": "slow on the way down"},
      {"exerciseId": "lateralRaise", "name": "Lateral Raise", "equipment": "dumbbell", "incrementKg": 1,
       "sets": 3, "repsMin": 12, "repsMax": 20, "weightKg": 8, "restSec": 60}
    ]},
    {"title": "Lower B", "exercises": [
      {"exerciseId": "romanianDeadlift", "name": "Romanian Deadlift", "equipment": "barbell", "body": "lower",
       "sets": 3, "repsMin": 8, "repsMax": 12, "weightKg": 80, "restSec": 150},
      {"exerciseId": "legPress", "name": "Leg Press", "equipment": "machine", "incrementKg": 10,
       "sets": 3, "repsMin": 10, "repsMax": 15, "weightKg": 120, "restSec": 120}
    ]},
    {"title": "Rest", "restDay": true},
    {"title": "Rest", "restDay": true}
  ]
}
```

## How to hand a plan over

1. Know before writing: workouts per week, the equipment available, and starting weights. If the user
   doesn't know a weight, ask, or pick a clearly light one and say so.
2. Check the plan against every rule above, then give it as **a downloadable file named
   `<planId>-v<version>.json`** if you can create files; otherwise as **one ```json code block holding
   only the plan**, for the user to save as a `.json` file. A short summary in words before it is fine.
3. Revising a plan: keep the `planId`, raise `version` by 1, keep every `exerciseId` for the same
   exercise (never rename one), and use the user's current working weights.
4. If the app refuses the file, the user pastes its problem list, for example
   `Step 2 "Lower A", exercise 3 "Plank": a bodyweight exercise has no "weightKg"; its progress is counted in reps.`
   Fix exactly those and give the whole file again.
