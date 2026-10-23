# Gym Tracker: what the app does, and how to write a plan for it

*For the user: add this whole file to your Claude project's files, replacing the older copy (in your
project it's `claude/planFormat.md`). It's written to Claude.*

You write training plans for **Gym Tracker**, the user's own Android gym app. A plan is **one JSON file**
in the exact format below. The user imports it in the app's PC view, and the app then shows each
day's workout on the phone, logs what was done and (from version 0.2-alpha) suggests the next weights
and reps by itself. The app checks every file strictly: anything outside this format is refused, with
a list of problems the user pastes back to you.

## What the app does with a plan

- **A week, Monday to Sunday.** A plan gives each of the 7 days its own session (a workout or a rest
  day), and **today's weekday decides** what the app shows. A missed day is simply missed: nothing
  shifts, and the next day shows its own session. Rest days are rest: there's no "train anyway".
- **The flex day (optional):** one day can make up a session missed earlier that week. Its `makeUp`
  lists the days it can make up, **most important first**. On the flex day the app shows the first
  of those that was missed (a workout day that ended without a workout); if two were missed, only that
  one is made up. If none was missed, it shows the flex day's own exercises: its bonus workout.
- **Moves (optional, with the flex day):** an exercise can move to another day in the weeks the flex
  day makes up certain sessions, like "if Saturday makes up Monday or Thursday, Friday's wrist curl
  moves to the end of Saturday". A moved exercise leaves its `from` day and joins the **end** of its
  `to` day; moved to the flex day, it joins the end of the session made up there. Each day decides from
  what it knows: on Thursday, Monday to Wednesday are over and Thursday and Friday count as trained.
- **Weekly target:** `weeklyTarget` is how many workouts a week the user aims for (weeks run Monday to
  Sunday). It drives the "week 2/5" counter and the streaks, and can't be more than the plan's
  workout days.
- **One workout per day.** The Today screen shows the session's title, the weekday and each exercise in
  the plan's order, like `Bench Press  4×8 @ 80 kg`, with the rest time and the notes underneath:
  ```
  Upper · Monday · week 2/5
  Bench Press   4×8 @ 80 kg              [✓]
    rest 2:00 · "pause at bottom"   ▾ sets · skip
  Dips          3×8                      [✓]
  Incline Walk  15 min                   [✓]
             [ Finish workout ]
  ```
  On the flex day making up Monday, the top line reads `Upper · Saturday, for Monday · week 4/5`. A
  lift logged as plates per side shows its weight as `@ 20 kg/side`. The user ticks an exercise (done
  as targeted), opens it to enter each set's reps and kg, or skips it.
- **Tapping an exercise's name shows its how-to** underneath, from the plan's optional `setup`,
  `howTo` and `form` fields (a plan without them works too: the app then says there's no how-to):
  ```
  Bench Press   4×8 @ 80 kg              [✓]
    rest 2:00 · "pause at bottom"   ▾ sets · skip
    │ Setup: flat bench in a rack, safety pins just below chest height
    │ How to
    │ 1. Lie back with your eyes under the bar
    │ 2. Grip a little wider than your shoulders
    │ Form
    │ •  Shoulder blades squeezed together and down
  ```
  `notes` stays the one short cue that's always visible; `form` is the full list, shown on a tap.
- **Progression is automatic, so a plan gives only the starting point.** Give each exercise a rep
  range and a starting weight. Don't write week-by-week weights. The app's rules (from 0.2-alpha; in
  0.1-alpha the target is simply `repsMin` at the plan's weight):
  - One rep target for all sets, starting at `repsMin`.
  - Every set hits the target → next time, the lowest set's reps + 1.
  - Every set reaches `repsMax` → add the weight step (`incrementKg`) and go back to `repsMin`.
  - Two or more sets under `repsMin` is a miss; two misses in a row → back to the last lower weight
    that worked. After such a drop, it takes two sessions at the top of the range to go heavier again.
  - **An exercise on several days progresses separately on each day:** its own target, weight and
    drop-backs per day, so a lift done fresh on Monday and tired on Wednesday doesn't drag either
    down. Its history, PRs and charts stay one.
  - Bodyweight exercises progress in reps only, past `repsMax` too. Cardio has a minutes target.
- **Deloads are the app's job (from 0.2-alpha):** about a week at half the sets, stopping 3–4 reps
  short. It starts one by itself when two or more `compound` lifts go backwards two sessions in a row,
  or by week 8 at the latest, and the user can start one by hand. So mark the compound lifts, and don't
  write deload weeks into a plan.
- **Volume and estimated 1RM (from 0.2-alpha)** count the real load: a lift logged as plates per side
  is doubled and gets its bar or sled weight added, and a two-dumbbell lift is doubled. That's why
  `dumbbells`, `platesPerSide` and `barKg` exist.
- **History follows the `exerciseId`.** The same ID means the same exercise on every day and in every
  later plan, so its history, PRs and charts carry on. A new ID starts a new history (the app asks if a
  new ID looks like a known exercise with a similar name).
- **Importing a new plan:** it takes effect today, or tomorrow if a workout is already logged today.
  From 0.2-alpha, **exercises the app already knows keep the user's current weights** (the import
  lists the plan weights it didn't use), and only new exercises start at the plan's weight. Until then
  the plan's weights replace the app's, so when you revise a plan before 0.2-alpha, ask the user for
  their current working weights and put those in.
- **Also in the app, but not part of a plan:** body weight (weekly weigh-in, Friday reminder), daily
  step counts, PRs and estimated 1RM, volume, streaks, a weekly summary. A plan holds training only.

## What isn't supported, and what to do instead

| Wanted | Do this instead |
|---|---|
| Different reps or weights per set (pyramids, top set + back-off sets, drop sets) | All sets of an exercise share one rep range and one weight. For a top set plus back-offs, use two exercises with their own IDs, like `"squatTopSet"` (1 set) and `"squatBackOff"` (3 sets) |
| A heavy and a light day of the same lift (different rep ranges or weights) | Two IDs, like `"squatHeavy"` and `"squatLight"`; each is tracked on its own. Only the number of sets may differ between days under one ID |
| Doing a missed session on another day than the flex day, or training on a rest day | Not possible: the weekday decides. Use the flex day's `makeUp` for missed sessions |
| Two flex days, or a flex day that is a rest day when nothing was missed | One flex day, and it has its own (bonus) exercises |
| %1RM, RPE or RIR, tempo, pauses, warm-up sets, supersets, circuits, alternatives | Write it in `notes` (one line). Supersets: put the exercises next to each other and say so in their notes |
| Timed holds (plank, wall sit) | `"bodyweight"` with reps meaning seconds (at most 100), and `notes` saying "reps = seconds" |
| Cardio distance, pace, intervals, heart rate | Only `minutes`; put the rest in `notes` |
| Weighted pull-ups or dips (added weight) | `"equipment": "machine"`, `weightKg` = the added weight, its own ID like `"weightedPullUp"` |
| Assisted machines (more weight = easier) | Not supported: the app would add weight to progress. Use another exercise |
| Kettlebells / cables, Smith machine, any stack / bands | `"dumbbell"` (weight of one bell) / `"machine"` / `"bodyweight"` |
| One arm or leg at a time | Reps per side; say "per side" in `notes`. Dumbbell weight is one dumbbell, with `"dumbbells": 1` |
| Pounds | Kilograms only: convert, at most 2 decimals |
| Deload weeks | The app runs them itself (see above); mark the compound lifts with `"compound": true` |
| Blocks, week-by-week changes | Not inside one plan. When it's time, write a new version of the plan for the user to import |
| Pictures, videos or links showing an exercise | Describe it in words in `setup`, `howTo` and `form` |
| Machine settings (seat height, pin position) | In `setup`, like `"seat at notch 4, back pad upright"` |

## The file

| Field | Needed | What it is |
|---|---|---|
| `planId` | yes | camelCase ID for the plan, like `"upperLower"`; keep it when you revise the plan |
| `name` | yes | shown in the app, up to 100 characters |
| `version` | yes | whole number, 1 or more; raise it by 1 every time the plan changes |
| `weeklyTarget` | yes | workouts a week, 1 to 7, and not more than the week's workout days |
| `week` | yes | the 7 days in order, Monday first; at least one of them a workout |

### A day

| Field | Needed | What it is |
|---|---|---|
| `day` | yes | `"monday"`, `"tuesday"`, … `"sunday"`: the day's place in the week, in order |
| `title` | yes | like `"Push"`, `"Upper A"` or `"Rest"`, up to 50 characters |
| `restDay` | for rest days | `true` makes the day a rest day; a rest day has no exercises |
| `exercises` | for workouts | a list of at least one exercise, in the order they're done |
| `makeUp` | flex day only | the earlier days of the week it makes up, most important first, like `["monday", "thursday"]`; each a workout day before the flex day. At most one day has it |
| `moves` | no, flex day only | exercises that move in the weeks the flex day makes up certain days; a list of moves (below) |

### A move

| Field | Needed | What it is |
|---|---|---|
| `exerciseId` | yes | an exercise of the `from` day |
| `from` | yes | the day it leaves; a workout day, not the flex day itself |
| `to` | yes | the day it joins, at the end; a workout day. The flex day means the end of the session it makes up |
| `when` | yes | the days from `makeUp` that trigger the move, like `["monday", "thursday"]` |

The moved exercise keeps its settings from the `from` day. It can't move into a workout that already
has it, and an exercise moves at most once for each made-up day.

### A strength exercise

| Field | Needed | What it is |
|---|---|---|
| `exerciseId` | yes | camelCase letters and digits, starting with a small letter, like `"benchPress"` (up to 100 characters) |
| `name` | yes | shown in the app, up to 100 characters |
| `type` | no | `"strength"` is the default; leave it out |
| `equipment` | yes | `"barbell"`, `"dumbbell"`, `"bodyweight"` or `"machine"` |
| `sets` | yes | 1 to 20; may differ between days for the same exercise |
| `repsMin`, `repsMax` | yes | the rep range, 1 to 100 each, `repsMin` not above `repsMax` |
| `weightKg` | yes, except bodyweight | the starting weight, 0 to 1000 kg, at most 2 decimals; for dumbbells, **one** dumbbell; with `platesPerSide`, the plates on **one** side |
| `body` | see below | `"upper"` or `"lower"`: the default weight step, upper 2.5 kg, lower 5 kg |
| `incrementKg` | see below | the weight step, 0.01 to 100 kg, at most 2 decimals; overrides `body`. Set it for dumbbells (e.g. 1 or 2) and machines (the stack's step). With `platesPerSide`, it's per side too |
| `dumbbells` | dumbbell only, yes | `2` for one in each hand, `1` for a single dumbbell (held in both hands, or one arm at a time) |
| `platesPerSide` | no, barbell or machine | `true` when the user logs the plates on one side of a bar or plate-loaded machine; volume and 1RM double it |
| `barKg` | no, barbell or machine | the bar's, sled's or carriage's own weight, 0 to 1000 kg, added for volume and 1RM. Leave it out when the logged weight already is the whole load (a stack machine, or a T-bar row logged as all the plates on its one pin) |
| `compound` | no | `true` for a compound lift (squat, bench, row, press, deadlift, pull-up…); the deload trigger watches these |
| `restSec` | no | rest between sets in seconds, 0 to 3600 (shown only, there's no timer) |
| `notes` | no | the short cue always shown on the Today screen, **one line**, up to 500 characters |
| `setup` | no | how-to: the machine or equipment needed and how to set it up, **one line**, up to 300 characters |
| `howTo` | no | how-to: the steps to do it, in order, as a **list of lines**, like `["Lie back…", "Grip…"]`; 1 to 12 lines, each one line of up to 200 characters, without numbers (the app numbers them) |
| `form` | no | how-to: form cues and common mistakes, a **list of lines** like `howTo`; 1 to 12 lines of up to 200 characters |

A weighted exercise (not bodyweight) needs `body` or `incrementKg`. A bodyweight exercise has no
`weightKg` (and an `incrementKg` there is ignored, with a warning).

### A cardio exercise

`"type": "cardio"`, `exerciseId`, `name`, `minutes` (1 to 600) and optionally `notes`, `setup`, `howTo`
and `form`. Nothing else.

### The how-to

`setup`, `howTo` and `form` describe the exercise, so give them **once**: when an exercise is on several
days, a day that leaves one out shows the one from the first day that has it. A day can still give
its own (it then shows that one instead), and nothing has to match. Write them for someone standing at the
machine: short, plain lines, one idea each.

### Rules the app enforces

- Each exercise can be in a day only once.
- An exercise on several days needs **identical settings on each**; only `sets`, `notes`, `restSec`
  and the how-to may differ. Otherwise give it a different ID.
- **No other fields.** An unknown field is refused, so a typo like `"repMin"` can't slip through.
  No field twice in one block. The old `"cycle"` format is refused too: plans now use `"week"`.
- Plain JSON (UTF-8): no comments, no trailing commas, no `NaN` or `Infinity`, numbers as numbers
  (`80`, not `"80"`), `true`/`false` as booleans. Text is one line: no line breaks. For several
  lines (`howTo`, `form`), use a list of one-line texts; no empty lines in it.

## Example

Five core days, a flex day and a rest day. `overheadExtension` is on Monday and Wednesday with the same
settings (only the notes differ), `seatedLegCurl` has 4 sets on Tuesday and 3 on Friday, `plank` uses
reps as seconds, the bench press and leg press are logged as plates per side, and the T-bar row as all
its plates on one pin. Saturday makes up a missed session (Upper first), and two of Friday's exercises
move in some weeks. The bench press and the pull-up have a how-to.

```json
{
  "planId": "upperLowerPushPull",
  "name": "Upper / Lower / Push / Pull",
  "version": 1,
  "weeklyTarget": 5,
  "week": [
    {"day": "monday", "title": "Upper", "exercises": [
      {"exerciseId": "benchPress", "name": "Bench Press", "equipment": "barbell", "body": "upper", "compound": true,
       "platesPerSide": true, "barKg": 20, "incrementKg": 1.25,
       "sets": 3, "repsMin": 6, "repsMax": 10, "weightKg": 25, "restSec": 150, "notes": "pause on the chest",
       "setup": "Flat bench in a rack; bar at the height of your straight arms, safety pins just below chest height",
       "howTo": ["Lie back with your eyes under the bar, feet flat on the floor",
                 "Grip a little wider than your shoulders", "Unrack, lower to mid-chest, pause, press back up"],
       "form": ["Shoulder blades squeezed together and down", "Wrists straight over the elbows",
                "Bum stays on the bench"]},
      {"exerciseId": "tBarRow", "name": "T-Bar Row", "equipment": "machine", "incrementKg": 5, "compound": true,
       "sets": 3, "repsMin": 8, "repsMax": 12, "weightKg": 40, "restSec": 120, "notes": "all plates on the one pin"},
      {"exerciseId": "overheadExtension", "name": "Overhead Dumbbell Extension", "equipment": "dumbbell",
       "dumbbells": 1, "incrementKg": 2, "sets": 3, "repsMin": 10, "repsMax": 15, "weightKg": 20, "restSec": 90}
    ]},
    {"day": "tuesday", "title": "Lower A", "exercises": [
      {"exerciseId": "legPress", "name": "Leg Press", "equipment": "machine", "incrementKg": 5, "compound": true,
       "platesPerSide": true, "barKg": 50, "sets": 3, "repsMin": 10, "repsMax": 15, "weightKg": 40, "restSec": 120,
       "setup": "Seat at notch 4; feet shoulder-width in the middle of the platform"},
      {"exerciseId": "seatedLegCurl", "name": "Seated Leg Curl", "equipment": "machine", "incrementKg": 5,
       "sets": 4, "repsMin": 10, "repsMax": 15, "weightKg": 35, "restSec": 90},
      {"exerciseId": "plank", "name": "Plank", "equipment": "bodyweight",
       "sets": 3, "repsMin": 30, "repsMax": 60, "restSec": 60, "notes": "reps = seconds held"}
    ]},
    {"day": "wednesday", "title": "Push", "exercises": [
      {"exerciseId": "overheadPress", "name": "Overhead Press", "equipment": "barbell", "body": "upper",
       "compound": true, "sets": 3, "repsMin": 6, "repsMax": 10, "weightKg": 40, "restSec": 150},
      {"exerciseId": "lateralRaise", "name": "Lateral Raise", "equipment": "dumbbell", "dumbbells": 2,
       "incrementKg": 1, "sets": 3, "repsMin": 12, "repsMax": 20, "weightKg": 8, "restSec": 60},
      {"exerciseId": "overheadExtension", "name": "Overhead Dumbbell Extension", "equipment": "dumbbell",
       "dumbbells": 1, "incrementKg": 2, "sets": 3, "repsMin": 10, "repsMax": 15, "weightKg": 20, "restSec": 90,
       "notes": "after the presses: fewer reps than Monday is normal"}
    ]},
    {"day": "thursday", "title": "Pull", "exercises": [
      {"exerciseId": "pullUp", "name": "Pull-up", "equipment": "bodyweight", "compound": true,
       "sets": 3, "repsMin": 5, "repsMax": 10, "restSec": 120,
       "setup": "Pull-up bar, or the pull-up handles of the cable tower",
       "howTo": ["Hang with straight arms, hands just wider than your shoulders, palms forward",
                 "Pull until your chin is over the bar", "Lower all the way down"],
       "form": ["No swinging or kicking", "Shoulders down, away from your ears"]},
      {"exerciseId": "preacherCurl", "name": "Preacher Curl", "equipment": "machine", "incrementKg": 2.5,
       "sets": 3, "repsMin": 10, "repsMax": 15, "weightKg": 25, "restSec": 75}
    ]},
    {"day": "friday", "title": "Lower B", "exercises": [
      {"exerciseId": "romanianDeadlift", "name": "Romanian Deadlift", "equipment": "barbell", "body": "lower",
       "compound": true, "platesPerSide": true, "barKg": 20, "incrementKg": 2.5,
       "sets": 3, "repsMin": 8, "repsMax": 12, "weightKg": 30, "restSec": 150},
      {"exerciseId": "seatedLegCurl", "name": "Seated Leg Curl", "equipment": "machine", "incrementKg": 5,
       "sets": 3, "repsMin": 10, "repsMax": 15, "weightKg": 35, "restSec": 90},
      {"exerciseId": "rearDeltMachine", "name": "Rear Delt Machine", "equipment": "machine", "incrementKg": 5,
       "sets": 3, "repsMin": 12, "repsMax": 20, "weightKg": 30, "restSec": 60},
      {"exerciseId": "behindBackWristCurl", "name": "Behind-the-Back Wrist Curl", "equipment": "barbell",
       "incrementKg": 2.5, "sets": 2, "repsMin": 12, "repsMax": 20, "weightKg": 30, "restSec": 60}
    ]},
    {"day": "saturday", "title": "Flex", "makeUp": ["monday", "thursday", "wednesday", "tuesday", "friday"],
     "moves": [
       {"exerciseId": "behindBackWristCurl", "from": "friday", "to": "saturday", "when": ["monday", "thursday"]},
       {"exerciseId": "rearDeltMachine", "from": "friday", "to": "thursday", "when": ["wednesday"]}
     ],
     "exercises": [
       {"exerciseId": "inclineWalk", "name": "Incline Walk", "type": "cardio", "minutes": 30,
        "notes": "incline 10, 5 km/h"}
     ]},
    {"day": "sunday", "title": "Rest", "restDay": true}
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
   exercise (never rename one), and (before 0.2-alpha) use the user's current working weights. Keep
   each exercise's `setup`, `howTo` and `form` too, unless the user asks to change them: the app shows
   only what the plan in use has.
4. If the app refuses the file, the user pastes its problem list, for example
   `Tuesday "Lower A", exercise 3 "Plank": a bodyweight exercise has no "weightKg"; its progress is counted in reps.`
   Fix exactly those and give the whole file again.
