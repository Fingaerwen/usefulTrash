# Gym Tracker plan format

Paste this into your Claude project, so the plans it writes import cleanly. A plan is one JSON file
(see `examplePlan.json`). On import the app lists every problem in plain words; paste that list back
to Claude to get a fixed file.

## The plan

| Field | Needed | What it is |
|---|---|---|
| `planId` | yes | camelCase ID for the plan, like `"pushPullLegs"` |
| `name` | yes | shown in the app, up to 100 characters |
| `version` | yes | whole number, 1 or more; raise it when the plan changes |
| `weeklyTarget` | yes | workouts a week, 1 to 7 |
| `cycle` | yes | the steps in order (1 to 60); the app repeats them |

## A step

| Field | Needed | What it is |
|---|---|---|
| `title` | yes | like `"Push"` or `"Rest"`, up to 50 characters |
| `restDay` | for rest days | `true` makes the step a rest day, which has no exercises |
| `exercises` | for workouts | a list of at least one exercise |

## A strength exercise

| Field | Needed | What it is |
|---|---|---|
| `exerciseId` | yes | camelCase, like `"benchPress"`; the same ID means the same exercise, in every step and every later plan, so its history carries on |
| `name` | yes | up to 100 characters |
| `equipment` | yes | `"barbell"`, `"dumbbell"`, `"bodyweight"` or `"machine"` |
| `sets` | yes | 1 to 20 |
| `repsMin`, `repsMax` | yes | the rep range, 1 to 100, `repsMin` not above `repsMax` |
| `weightKg` | yes, except bodyweight | the starting weight, 0 to 1000 kg with at most 2 decimals; for dumbbells, **one** dumbbell |
| `body` | see below | `"upper"` or `"lower"`: sets the weight step, upper 2.5 kg, lower 5 kg |
| `incrementKg` | see below | the weight step when you top the rep range; overrides `body` |
| `restSec` | no | rest between sets in seconds (shown only, no timer) |
| `notes` | no | form cues shown on the Today screen, one line, up to 500 characters |

A weighted exercise (not bodyweight) needs `body` or `incrementKg`. A bodyweight exercise has no
`weightKg`: it progresses in reps.

## A cardio exercise

`"type": "cardio"`, `exerciseId`, `name`, `minutes` (1 to 600) and optionally `notes`. Nothing else.

## Rules

- Each exercise can be in a step only once.
- An exercise in several steps needs the same settings in each; only `notes` and `restSec` may differ.
  For a heavy and a light day of the same lift, use two IDs (like `"squatHeavy"`, `"squatLight"`).
- No other fields: an unknown field is refused, so a typo like `"repMin"` can't slip through.
- Plain JSON: no comments, no trailing commas, no `NaN`.
- A `weeklyTarget` above the cycle's own pace (workout steps ÷ steps × 7) only gets a warning.
