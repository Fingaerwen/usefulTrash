# Ambrosia: what the app does, and how to write a targets file for it

*For the user: add this whole file to your Claude project's files (in your project, as
`claude/targetsFormat.md`). It's written to Claude.*

You write nutrition targets for **Ambrosia**, the user's own diet app (Android, with a PC view). Ambrosia
counts calories, protein, fat and carbs against daily targets, and runs the bulk check from the user's
weigh-in protocol. The targets come from **one JSON file** you write, in the exact format below. The user
imports it in the app. The app checks it strictly and refuses anything outside this format, with a list of
problems the user pastes back to you.

## What the app does with a targets file

- **Two kinds of day.** A **training day** is a weekday with a fixed session in the user's gym plan (Talon, the
  gym app), or the flex day once a workout is logged there. Every other day is a **rest day**. Each kind has
  its own kcal, protein, fat and carbs. Give both, even if they're the same.
- **From the day it's imported.** A new file replaces the current targets from that day on, and the changes
  the bulk check made to them. Before importing, the app shows the user the current targets (with any changes)
  next to the new ones, so the user can tell you what they were.
- **Water** is optional: a daily target in ml.
- **The bulk check** (optional) runs the user's weigh-in protocol with the settings you give, so you own the
  protocol. Leave the whole `bulkCheck` section out to switch it off (for a cut, say). How it works:
  - Blocks of two full Monday–Sunday weeks, back to back from `firstBlockStart` (a Monday). Weigh-ins before it
    don't count.
  - Only weigh-ins on days the user trained count (the protocol is gym only). A block with fewer than
    `minWeighIns` is left out entirely: its own check is skipped, and so is any later check that would compare
    against it.
  - On each block's last day (a Sunday), two checks compare the newest block's average:
    - **Regular:** with the block four weeks earlier, the difference divided by 4 being the weekly rate. Inside
      `rateKgPerWeek` (min to max): no change. Below: add `stepKcal`. Above: remove `stepKcal`.
    - **Big miss:** with the block right before it. Lower: add `bigStepKcal`. More than `bigGainKg` higher:
      remove `bigStepKcal`.
    - If both call for a change the same way, only the big miss's applies. If they point opposite ways, nothing
      changes.
  - Averages and the rate are rounded to 0.01 kg before comparing.
  - A change only ever **suggests**: the user taps Apply. It goes onto training and rest days alike, and
    `changeMacro` takes the grams (carbs: 4 kcal a gram, fat: 9, 150 kcal is 38 g of carbs).
  - After any calorie change (an applied change, or a new file with different kcal) the next full block is the
    new baseline: nothing before it is compared with anything after it.

## The format

```json
{
  "format": "ambrosiaTargets",
  "version": 1,
  "name": "Bulk from 26 Oct",
  "trainingDay": {"kcal": 3200, "proteinG": 160, "fatG": 90, "carbsG": 440},
  "restDay": {"kcal": 3200, "proteinG": 160, "fatG": 90, "carbsG": 440},
  "waterMl": 3000,
  "bulkCheck": {
    "firstBlockStart": "2026-10-26",
    "rateKgPerWeek": {"min": 0.15, "max": 0.35},
    "stepKcal": 150,
    "bigStepKcal": 250,
    "bigGainKg": 1.0,
    "minWeighIns": 8,
    "changeMacro": "carbs"
  }
}
```

| Field | Required | What it is |
|---|---|---|
| `format` | yes | always `"ambrosiaTargets"` |
| `version` | yes | always `1` (the format's version, not the targets') |
| `name` | yes | a short name the app shows, 1 to 100 characters, like `"Bulk from 26 Oct"` |
| `trainingDay` | yes | `kcal` (800 to 8,000), `proteinG` (0 to 500), `fatG` (0 to 400), `carbsG` (0 to 1,500): whole numbers |
| `restDay` | yes | the same four, for rest days |
| `waterMl` | no | whole ml a day, 0 to 10,000 |
| `bulkCheck` | no | leave it out to switch the check off |
| `bulkCheck.firstBlockStart` | yes, in it | the first block's Monday, `"YYYY-MM-DD"` |
| `bulkCheck.rateKgPerWeek` | yes, in it | `{"min": …, "max": …}` in kg a week, from −2 to 2, min below max |
| `bulkCheck.stepKcal` | yes, in it | the regular check's change, whole kcal, 25 to 1,000 |
| `bulkCheck.bigStepKcal` | yes, in it | a big miss's change, whole kcal, 25 to 1,000 |
| `bulkCheck.bigGainKg` | yes, in it | how much higher than the block before counts as a big miss, 0.1 to 5 kg |
| `bulkCheck.minWeighIns` | yes, in it | the fewest weigh-ins a block needs to count, 1 to 14 |
| `bulkCheck.changeMacro` | yes, in it | `"carbs"` or `"fat"`: the macro that takes a change |

No other fields: a misspelled one is refused, so nothing is silently ignored. The app warns (but still imports)
when protein × 4 + fat × 9 + carbs × 4 is more than 10% away from a day's kcal.

## How to hand a targets file over

1. Give it as **a downloadable file named `targets-<name>.json`** if you can create files. Otherwise as **one
   ```json code block holding only the file**, for the user to save as a `.json` file. A short summary in words
   before it is fine.
2. Changing targets: write the whole file again with a new `name`. If the user has applied bulk-check changes,
   ask for the current targets the app shows before an import, and start from those unless you mean to reset.
3. If the app refuses the file, the user pastes its problem list, for example
   `"restDay.kcal" must be a whole number from 800 to 8,000.` Fix exactly those and give the whole file again.
