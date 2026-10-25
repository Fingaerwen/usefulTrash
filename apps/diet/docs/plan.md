# Ambrosia: Diet App Plan

> **Status (2026-10-25):** designed, not built yet. The decisions are below (AM1–AM3, and AM5 and AM6 from the design round); what's still open is in 4j. Phase 0's PC side is done (`apps/diet/docs/phase0.md`): the spike and the `barcodeScan` extension build and pass our checks, Open Food Facts and the bundled generic foods work, and both PC views run side by side. Claude tested the spike on the phone over USB on 2026-10-25 (everything but the scans; your scans are left for later). The design round is done: its first part on 2026-10-25 (AM5.1–AM5.8), and the same day its max-effort part, the bulk check's rules (4g), the tables (4e) and the targets file's fields (4f) (AM6.1–AM6.4). Next: building, with max-effort gate 2 inside it, done last (AM7.2). Building started 2026-10-25. Gym Tracker becomes **Talos** at Ambrosia's first release (AM1.4). This file is Ambrosia's single source of truth: every decision is applied in the sections below and listed in the **Decision log** at the end. The suite's shared rules (security, code style, sync, data upgrades) stay in `docs/plan.md` and aren't repeated here.

## Context
Ambrosia is the diet app of the usefulTrash suite, next to the gym app (Talos, `apps/gym`). You track what you eat by scanning barcodes and searching food databases; the app counts calories, protein, fat and carbs against daily targets your Claude project writes, and runs your Claude project's bulk check on the body weight you log in Talos. It's a phone app with a PC view, built side by side from the start.

Before 2026-10-25 the only notes on it were a few lines in `docs/plan.md` (section 13: same Supabase project, login and naming; shares weight and training days; nutrition tables and goals designed when the diet app is planned, 15.1). Your nutrition numbers and the weigh-in protocol were only in your Claude project's context file, pasted into a session on 2026-10-23; section 2 keeps them here so they aren't lost.

---

## 1. What carries over from the suite (AM1.1)
Ambrosia lives in `apps/diet/` and reuses what Talos already proved, unchanged unless a section here says otherwise:
- **Platform:** Python + Flet 1.0.3 (pinned), one codebase → the phone APK + the PC view website (`docs/plan.md` 1). Phone vs PC is decided once in `main.py` (3b).
- **Cloud and sign-in:** the same Supabase project with row-level security on every table, sign-ups disabled; native Google sign-in on the phone (AU1c) and Google Identity Services in the PC view, no secret anywhere (`docs/plan.md` 2).
- **Shared code:** `usefulShared` (`shared/src/usefulShared/`): the phone store and outbox, the cloud store, sync, Drive backups, the log and its scrubber. Our Kotlin extensions follow the existing pattern (`extensions/`), each guarded by `tools/packageGuard.py` (CS1.1).
- **Code structure:** pure rules with "today" passed in, facts-only storage with everything recalculated (F10.1), one write path through `actions.py`, declarative screens (3b).
- **Data:** camelCase, the common columns on every synced row, newest edit wins, cloud upgrades only add (`docs/plan.md` 14, 14b, 14c).
- **Diagnostics:** the Problems page with Copy, nothing sent automatically (DG1.1).
- **Look:** black and greys following the phone, cards (LK1.2; `apps/gym/src/gym/screens/look.py`).
- **Tests:** the screen test kit with its layout and font checks (`tests/screenTestKit.py`, TS1.1), and real screenshots in headless Chromium before calling a screen done. Ambrosia's tests go in `tests/diet/`, next to `tests/gym/`.
- **Security:** secrets never in any text or on any server; leak scans before commits and on every build (`docs/plan.md` 2).

## 2. Your Claude project's numbers (owned by the targets file)
Quoted word for word from section 10 of your Claude project's context file ("Gym Training Project: Context File", last updated 23 October 2026). The app takes its targets and the bulk check's settings from the targets file (AM3.1), not from here: this is the record of where they come from.

> **10. Bulk and nutrition**
> Maintenance estimate: Mifflin-St Jeor for men (10 × kg + 6.25 × cm − 5 × age + 5) gives a resting rate of about 1,790–1,820 kcal for 79 kg and 179 cm at ages 19–25. Multiplied by activity factors 1.55–1.725, maintenance is about 2,800–3,100 kcal. Formula estimates are often around 10% off, so body-weight trends decide.
> Target rate: 0.2–0.3 kg per week (about 0.25–0.38% of body weight, the lower half of the recommended 0.25–0.5%), chosen because he already carries some softness and wants visible abs later.
> Starting intake from Monday 12 Oct 2026: about 3,200 kcal a day. Protein 160 g (about 2 g/kg, spread over ~4 meals of ~40 g), fat 90 g (about 1.1 g/kg), carbs about 440 g (about 5.5 g/kg). 640 + 810 + 1,750 kcal = 3,200 kcal.
>
> **Weigh-in protocol (gym only)**
> Why: under identical conditions daily body weight scatters about 0.5% around its trend (about ±0.4 kg for him), and weighing after training adds noise from the day's food and drink, sweat losses, drinking during the session and the weekly rhythm (weight peaks around Sunday–Monday, falls toward Friday). Two-week averages taken four weeks apart narrow the weekly rate to about ±0.1 kg.
> Same routine every time: after the shower, towel-dried, naked, same scale, before eating or drinking anything after the workout. Drink about the same amount during each session. Log the weight and the time.
> Ignore the first two weeks of the bulk (12–25 Oct 2026): glycogen refill and its water show up as a quick jump that isn't tissue.
> Average each two-week block of two full Monday–Sunday weeks. If a block has fewer than about 8 weigh-ins, skip that block's check.
> Every second Sunday, compare the newest block's average with the block from four weeks earlier and divide the difference by four to get the weekly rate. 0.15–0.35 kg a week: no change. Below: add 150 kcal a day. Above: remove 150 kcal a day.
> Big misses don't wait: if a block comes in lower than the one right before it, add 250 kcal a day straight away; if it comes in more than 1 kg above it, remove 250 kcal a day.
> After any calorie change, the next two-week block becomes the new baseline.
> Waist at home weekly: morning, at the navel, after a normal breath out. If it keeps growing while lifts stall, the surplus is too big.
>
> Key dates: first block 26 Oct – 8 Nov 2026; first big-miss check Sunday 22 Nov 2026; first regular check Sunday 6 Dec 2026. The app takes one weight a day on any day (Friday reminder), so weighing after every session works. With five or six sessions a week, a two-week block has 10–12 readings.
>
> **Timeline and target**
> Timeline, counting from Monday 12 Oct 2026: 82 kg on 21 Dec 2026 at 0.3 kg/week, 25 Jan 2027 at 0.2 kg/week; 85 kg on 1 Mar 2027 / 10 May 2027; 90 kg ~26 Jun 2027 / ~1 Nov 2027.
> Fat-free mass index (FFMI = lean mass ÷ height², at 1.79 m): 85 kg is 23.3 at 12% body fat and 22.5 at 15%; 90 kg is 24.7 and 23.9.
> In the classic 1995 study, drug-free lifters averaged an FFMI of about 22 and topped out around 25. So 90 kg at a lean ~12% would sit right at that ceiling, while 85 kg lean is well within the natural range.
> Recommendation: make 85 kg the target for this bulk. Then cut at about 0.7% of body weight per week (about 0.6 kg a week at 85 kg); losing 4–6 kg takes about 7–10 weeks. Decide on 90 kg after the cut, based on the mirror rather than the scale.

(The timeline and FFMI tables are written out as sentences here; the numbers are unchanged. The context file's section 10 also covers cardio, sleep, creatine and definition, which Ambrosia doesn't use. Its section 12 lists the open item this plan answers: "Diet app: whether it tracks calories and macros, and how he tracks intake meanwhile (not discussed yet)." Talos's Weight tab stores the day's weight but not the time the protocol mentions; from Talos 0.4 it keeps the time you save today's weigh-in, AM6.3.)

## 3. Decided so far (2026-10-25)
| ID | Decision |
|---|---|
| AM1.1 | Lives in `apps/diet/` in this repo, reusing the suite (section 1). |
| AM1.2 | Called **Ambrosia** on the phone: covert, fantasy-epic. The folder stays `apps/diet`. |
| AM1.3 | Phone app and PC view, built side by side from the start. |
| AM1.4 | Gym Tracker becomes **Talos**: only the visible name changes (the phone's app name, the PC view's title, release titles and APK file names, the site pages, the docs). The package ID `io.github.fingaerwen.gymtracker`, the folder `apps/gym` and the `gym-v` tags stay, so the update installs over the current app with your data and Obtainium link intact. It reaches your phone with Ambrosia's first release, in one changeover; a gym fix released before then still says Gym Tracker. |
| AM2.1 | Counts calories, protein, fat and carbs. |
| AM2.2 | Food comes in by barcode scan (phone) or database search (phone and PC view). No hand-made foods list, no quick numbers. |
| AM2.3 | When a scan or search finds nothing, or the food has no kcal or macros, you type it from the label once (per 100 g); it's saved, so the next scan finds it. |
| AM2.4 | Amounts in grams, or servings and pack fractions ("1 serving", "half the pack"). |
| AM2.5 | Meals: breakfast, lunch, dinner, snacks. |
| AM2.6 | Water is counted. |
| AM3.1 | Targets come from a file your Claude project writes and you import, like the training plan. |
| AM3.2 | Training-day and rest-day targets: the weekdays your gym plan has a fixed session (Mon–Fri) are training days; the flex day (Saturday) becomes one once you log a workout there; the rest day (Sunday) is a rest day. |
| AM3.3 | The bulk check suggests a change and you confirm it; nothing changes on its own. |
| AM5.1 | Barcodes are scanned with ZXing, inside the app: nothing is sent anywhere, and Android asks once for the camera. |
| AM5.2 | The PC view doesn't search packaged foods by name: it searches your own foods and the generic foods, and looks up a typed barcode. The phone has the full search. |
| AM5.3 | Generic foods are ranked plainest first (Phase 0's new ranking): baby foods left out, each name once, your own foods always ahead of them. |
| AM5.4 | Barcodes starting with 2 (shops' own codes) are looked up only in your foods, never in Open Food Facts; the first scan goes straight to typing it from the label. You'll say where you shop later: ask. |
| AM5.5 | History on the phone like Talos's: ⋮ → History, every day back to the first, the last 7 editable. The PC view edits any day. |
| AM5.6 | Each app backs up its own tables: Ambrosia gets its own Drive folder, dated backups and history file, every 30 days; Talos's backup doesn't change. |
| AM5.7 | Talos's Monday summary doesn't get nutrition for now; Ambrosia's Week tab shows the week's food. |
| AM6.1 | A block with fewer weigh-ins than the minimum is left out entirely: its own check is skipped, and so is any later check that would compare against it. |
| AM6.2 | When the regular check and a big miss both call for a change the same way, only the big miss's applies (250 kcal, not 400); opposite ways, nothing changes. |
| AM6.3 | Talos keeps the time you save today's weigh-in (`bodyWeight.weighedAt`, upgrade 003) and shows it beside each weigh-in; a past day's weigh-in has none. |
| AM6.4 | Cloud upgrade 003 as in 4e: `foods`, `foodLogs`, `water`, `dietTargets`, `targetChanges`, `dietBackups` and `bodyWeight.weighedAt`. The bulk check's exact rules are in 4g, the targets file's fields in 4f. |
| AM7.1 | Ambrosia's look: bold, sharp, aggressive gold, with pink gradients over a goddess background, on the suite's black and greys (like Talos's red, LK1.3). |
| AM7.2 | Building order: everything that doesn't need max effort first; the max-effort parts (gate 2: the bulk check and the new tables' sync) last. Commits go to main and are pushed as they're done. |
| AM5.8 | The design round's sketches are the basis for building: phone tabs Today, Week, Targets (⋮: History, Problems); PC view tabs Today, Week, History, Targets, Backup. Details are settled as each screen is built and checked on your phone. |

Rejected on 2026-10-25: a separate repo; calories only, or calories and protein; a foods list made by hand and quick numbers as ways to log; phone only (first chosen, then replaced by AM1.3); the weekly waist measurement; changing targets automatically.

## 4. Design
Settled point by point in the design round, as Talos's plan was: 4a, 4b and 4d on 2026-10-25 (AM5), and 4e, 4f and 4g the same day at max effort (AM6). 4c, 4h and 4i are settled at the joint release (gate 3).

### 4a. Phone screens
- **Today:** what's left of the day's target (kcal, then protein, fat and carbs), with "training day" or "rest day" (AM3.2); four meal cards (AM2.5), each with **+** → Scan, Search, Recent; a water card with **+250 ml** and the day's total (AM2.6).
- **Add food:** scan or search → the food with its values per 100 g → the amount: grams, servings or part of the pack (AM2.4) → the meal → Save. Recent foods re-log in one tap. Not found → "Type it from the label" (AM2.3).
- **Week:** each day's kcal against its target, the week's average macros, and your body weight from Talos.
- **Bulk check banner** on check Sundays: e.g. "+0.12 kg a week → add 150 kcal a day?" with **Apply** and **Not now** (AM3.3).
- **Targets:** import a file, the current targets for training and rest days, and the changes made to them.
- **⋮ menu:** History (AM5.5), Import a targets file and Problems. **As built (2026-10-25):** tapping an entry unfolds it to change the amount or the meal, or delete it; the water card's pencil sets the day's total, to fix a mistake. A day before your first targets file says so instead of asking for one.
- **Tabs:** Today, Week, Targets (AM5.8).

### 4b. PC view
The same app built as a website, online-only like Talos's: the tabs down the left (SC6.2); **Today** for any day (log by searching your foods and the generic foods, or by a typed barcode; edit, delete; no scanning and no packaged-food search by name, AM5.2); **Week**; **History** to edit any day; **Targets** (importing a file is easiest here); **Backup** with Export CSV; the bulk check banner.

### 4c. Both PC views on one site
- `fingaerwen.github.io/usefulTrash/` becomes a small start page linking **Talos** (`/usefulTrash/talos/`) and **Ambrosia** (`/usefulTrash/ambrosia/`).
- `about.html`, `privacy.html` and `driveToken.html` stay where they are, at the addresses Google has registered, so nothing changes in Google Cloud (the web sign-in is allowed for the whole `https://fingaerwen.github.io` origin).
- The release script's publish step (P6.1) puts both builds into its single `gh-pages` commit.
- Talos's PC view moves from `/usefulTrash/` to `/usefulTrash/talos/` at the changeover; the start page links it.

### 4d. Food sources
- **Packaged foods:** Open Food Facts (a free, open food database), by barcode or by name. A request sends only the barcode or the search words, with a User-Agent naming the app and the repo, never your email. The phone calls it from Python (`urllib`, like `shared/src/usefulShared/cloud/supabaseApi.py`); the PC view from the browser. Its rate limits are respected.
- **Generic foods** (rice, chicken breast, an apple, which Open Food Facts covers poorly): USDA FoodData Central's public-domain data, cut down to name plus kcal, protein, fat and carbs per 100 g, bundled with the app and searched offline.
- **Barcode scanning (AM5.1):** ZXing (`zxing-android-embedded`, open source), scanning inside the app with nothing sent anywhere; Android asks once for the camera. Through a new extension `extensions/barcodeScan` (package `usefulTrashBarcodeScan`).
- Foods found are saved in `foods`, so recent foods work offline and a typed label is found again.
- **Search order:** your own foods first, then the generic foods (plainest first, AM5.3), then, on the phone, Open Food Facts.
- **Not found:** Open Food Facts answers an unknown barcode with 404; Ambrosia reads that as "not found, type it from the label" (AM2.3). A barcode starting with 2 is looked up only in your foods (AM5.4). **As built:** a shop's own code is GS1's internal ranges: EAN-13 starting with 2, or 02 or 04 (UPC-A's own ranges as EAN-13), UPC-A starting with 2 or 4, EAN-8 starting with 0 or 2. A typed barcode is checked by its last digit first, so a typing mistake isn't looked up. Without a Talos plan Ambrosia can read, every day is a training day (a bulk needs the food more than the rest).
- **Limits:** Open Food Facts allows 15 barcode lookups and 10 searches a minute per internet connection (its API docs); a barcode is looked up once per scan, never while typing.

### 4e. Tables (cloud upgrade 003, AM6.4)
Settled 2026-10-25 at max effort. Every table has the common columns, the newest-edit trigger and row-level security (`docs/plan.md` 14). Upgrade 003 only adds, so `minAppSchema` stays 1 and Talos 0.3 keeps syncing: it fetches and sends only the columns it knows.

| Table | One row per | Columns besides the common ones |
|---|---|---|
| `foods` | food you've used | `source` (openFoodFacts, usda or label), `barcode` (digits; empty for a USDA food or a label typed without one), `usdaId` (FoodData Central's number, for a USDA food), `name`, `brand` (may be empty), `unit` (g, or ml for a drink: its values are per 100 ml and its amounts read in ml; 1 ml counts as 1 g), `kcal`, `proteinG`, `fatG`, `carbsG` (per 100 g or ml; all four required), `servingG` and `packG` (may be empty) |
| `foodLogs` | food eaten | `date`, `meal` (breakfast, lunch, dinner or snacks), `loggedAt` (its place in the meal), `foodId`, `portion` (grams, servings or pack) with `portionCount` (1, 0.5 and so on; empty for grams), `grams` (the amount, worked out when logged), and copies of the food's `name`, `brand`, `unit` and values per 100 g at the time, so later edits to the food don't rewrite past days |
| `water` | day | `date`, `ml`: the day's total, its ID worked out from the date like `dailySteps` (two devices adding at the same moment keep the newer total) |
| `dietTargets` | targets file import | `importedAt` (orders imports on the same day), `effectiveDate` (the day you import it), `targetsJson` (the file as imported) |
| `targetChanges` | bulk-check change you applied | `checkDate` (the check's Sunday; the ID is worked out from it, so a check makes one change at most), `fromDate` (the day you applied it; it counts from then), `targetsImportId` (the import it changes), `reason` (rate, bigMissLow or bigMissHigh), `kcalChange`, `macro` with `macroChangeG`, and the check's numbers: `blockAvgKg`, `blockWeighIns`, `comparedStart`, `comparedAvgKg`, `comparedWeighIns`, `rateKgPerWeek` (empty for a big miss). Undoing a change deletes its row |
| `dietBackups` | Ambrosia backup | the same columns as `backups`. Its own table because Talos decides its backup is due from the newest `backups` row (`backupJob.backupDue`), so Ambrosia's backups there would stop Talos's (AM5.6) |

- **One shared table changes:** `bodyWeight` gets `weighedAt` (a moment, may be empty). Talos 0.4 stamps it when you save today's weigh-in and shows it beside each weigh-in; a past day's weigh-in, and every weigh-in from before 0.4, has none (AM6.3). An older Talos saving a weigh-in leaves it as it was, because an upsert changes only the columns it sends.
- **IDs that can't duplicate:** a food with a barcode gets its ID from the barcode, a USDA food from its USDA number, a day's water from the date and a change from its check's date, so the phone and the PC view make one row, never two. Food logs, label foods without a barcode, imports and backups get random IDs.
- **Read, never written:** Talos's `bodyWeight` (the bulk check), `plans` (training and rest days, AM3.2), `sessions` and `exerciseLogs` (whether you trained that day). Ambrosia's phone keeps copies, fetched like its own tables; it never edits them, so they're never in its outbox.
- **Facts only (F10.1):** Recent and how often you've used a food, the day's totals, the targets in effect on a day and the bulk check's results are recalculated, never stored. The generic-foods file carries each food's USDA number (FoodData Central's `fdc_id`), so a USDA food keeps its ID when USDA publishes new data.
- **Precision (for upgrade 003's column types):** kcal per 100 g to 0.1, the macros per 100 g to 0.01, grams, serving and pack sizes to 0.1, a portion's count to 0.01 (the actions round to these, so the cloud's copy and the phone's never differ).

### 4f. Targets file (AM3.1, AM6)
Settled with the bulk check on 2026-10-25. The brief for your Claude project, `apps/diet/plans/targetsFormat.md`, is written when building, from this:
- **Targets:** training day and rest day, each with kcal, protein, fat and carbs (whole kcal and grams); an optional water target in ml.
- **The bulk check's settings,** so your Claude project owns the protocol: the first block's start (a Monday), the weekly rate range (0.15 to 0.35 kg), the step (150 kcal), the big step (250 kcal), the big-gain limit (1 kg), the minimum weigh-ins per block (8), and the macro that takes a change (carbs or fat: 4 or 9 kcal a gram, so 150 kcal is 38 g of carbs, a half rounding up). The section is optional: a file without it switches the check off, for a cut, say.
- **Taking effect:** a file applies from the day you import it and replaces the current targets, including changes you applied; before an import, Ambrosia shows the current targets so you can tell your Claude project. A day's targets are the newest import that applies by then, plus that import's changes that count by then. An import whose kcal (training or rest day) differs from the current targets is a calorie change (4g).

### 4g. Bulk check (AM3.3, AM6.1, AM6.2)
Settled 2026-10-25 at max effort: the protocol in section 2, with the settings from the targets file (4f). It only suggests; your targets change when you tap Apply.
- **Blocks:** two full Monday–Sunday weeks, back to back, counted from the first block's start (26 Oct 2026 now). Weigh-ins before it don't count, which leaves out the bulk's first two weeks.
- **Weigh-ins that count:** Talos's `bodyWeight` on days you trained, meaning at least one exercise done in Talos that day (sets or minutes, not skipped). The protocol is gym only, so a weigh-in on another day shows in Ambrosia but stays out of the check. The same "trained" decides when the flex day is a training day (AM3.2).
- **A block's average:** the mean of its weigh-ins. Averages, their differences and the weekly rate are rounded to 0.01 kg (a half away from zero) before anything is compared, so the numbers shown are the ones that decide.
- **Thin blocks (AM6.1):** a block with fewer weigh-ins than the minimum (8) is left out entirely: its own check is skipped, and so is any later check that would compare against it.
- **The baseline:** the first block, and after any calorie change (an applied change, or an import that changes kcal) the first block that starts on or after the day the change counts from. A block before the baseline is never compared with one from it on.
- **The checks,** on each block's last day (a Sunday). Both compare the newest block, and run only when both blocks are from the baseline on and neither is thin:
  - **Regular:** against the block four weeks earlier; the difference divided by 4 is the weekly rate. 0.15 to 0.35 kg a week: no change. Below: add the step (150 kcal). Above: remove it.
  - **Big miss:** against the block right before it. Lower: add the big step (250 kcal). More than the big-gain limit (1.00 kg) higher: remove it.
  - **Both (AM6.2):** if both call for a change the same way, only the big miss's applies (250, not 400). If they point opposite ways, which can only happen after a suggestion you didn't apply, nothing changes.
- **The suggestion:** a banner on Today (phone and PC view) and a line on Targets, with both blocks' averages, their weigh-in counts and the rule that fired. It's recalculated whenever a weigh-in changes, and Apply waits until Ambrosia has synced that day, so a late weigh-in isn't missed. It lasts until you apply it, dismiss it (remembered on each device, like BN1.1), or the next block's check replaces it.
- **Apply:** the kcal change goes onto training and rest days alike, with the file's macro taking the grams, from the day you tap it. On the check Sunday or the Monday after, the block starting that Monday is the new baseline; any later, the one after. Not applying changes nothing, and the checks carry on from the same baseline. Undoing an applied change (on Targets) deletes it, as if it never happened.
- **Your key dates, checked:** 8 Nov, the end of block 1: nothing to compare. 22 Nov: the first big-miss check (block 2 against 1). 6 Dec: the first regular check (block 3 against 1) and a big-miss check (3 against 2).

### 4h. Releases (the joint changeover)
- Ambrosia gets its own version, starting at 0.1-alpha, tagged `ambrosia-v0.1-alpha` and titled "Ambrosia 0.1-alpha"; Talos's next release is titled "Talos 0.4-alpha".
- `tools/buildRelease.py` gets an app choice (today it hard-codes `apps/gym` and `gym-v`).
- Your steps: two Android sign-in clients for `io.github.fingaerwen.ambrosia` (release and debug key, like `docs/setup.md` step 2), and Obtainium's release filters: `^Talos` on the existing entry and `^Ambrosia` on a new one, because without them each app would take the other's release as its own latest.

### 4i. Talos at the changeover (AM1.4, AM6.3)
- **The weigh-in time (AM6.3):** the Weight tab stamps `bodyWeight.weighedAt` when you save today's weigh-in, and shows it beside each weigh-in. Talos's schema number goes to 3, so it syncs only once upgrade 003 is in.
- The name in `apps/gym/pyproject.toml` (product), `apps/gym/src/gym/model.py`, `apps/gym/src/main.py`, `apps/gym/src/gym/pcApp.py`, the tests, `docs/*` and `plans/planFormat.md` (the repo copy).
- `site/*.html`; the privacy page then covers both apps, food logs included.
- Drive backups: the folder **Gym Tracker backups** and its file names (`shared/src/usefulShared/backup/backupJob.py`) get the new name. The existing folder is renamed in place, so the history file carries on, and `tools/restoreBackup.py` accepts the old and new names.

### 4j. Still open
- **From Phase 0, still open:** duplicate generic foods and the four searches the new ranking still gets wrong (oatmeal, spaghetti, skim milk, bacon), if they bother you in use; anything Ambrosia keeps in the browser gets its own key names (both PC views share one browser storage).
- **Where you shop:** you'll say just before the first version goes live (AM5.4); ask then.
- **Talos's Friday weigh-in reminder and banner** (07:00 "Time to weigh in", NT1.2, 18.4a) come from the weekly weigh-in; your protocol now weighs after every session, at the gym. Whether they change is for the joint release (gate 3).
- Settled on 2026-10-25: the scanner (AM5.1), the PC view's name search (AM5.2), the ranking (AM5.3), shop barcodes (AM5.4), one Drive backup per app (AM5.6), Talos's weekly summary (AM5.7), the sketches (AM5.8).

## 5. Max-effort gates
Your rule (2026-10-25): at each of these I stop, tell you to switch to max effort, and don't start until you say it's on. I can't see the effort setting myself, so your word is the check.
1. **Design round: the bulk check rules (4g) and the tables (4e).** The math changes your calories, and cloud upgrade 003 can't be taken back. Done 2026-10-25 (AM6.1–AM6.4).
2. **Building the bulk check and the new tables' sync.**
3. **The joint release (4h, 4i):** the Talos rename, renaming the Drive backup folder in place, both PC views on one site, and the Obtainium filters.

Phase 0 and the rest of the design round don't need max effort.

## 6. Phase 0: the risky parts, checked first
A throwaway spike in `apps/diet/spike/`, never imported (like `spikes/phase0`). On the phone it's a separate package (`io.github.fingaerwen.ambrosiaspike`, debug key), so the real app installs cleanly later. No sign-in, no cloud and nothing published, so there are no Google Cloud or GitHub steps for you. Results go in `apps/diet/docs/phase0.md`.

| # | Check | Where |
|---|---|---|
| 1 | Barcode scanning through Google's code scanner, in the `barcodeScan` extension (built like `extensions/weighInNotify`, guarded by `tools/packageGuard.py`) | phone |
| 2 | Open Food Facts by barcode and by name, from Python on the phone and from the browser in the PC view (whether it allows a web page to call it: CORS), within its rate limits | phone, PC |
| 3 | The generic-foods file from USDA data: its size, search speed on the phone, what it adds to the PC view's load time | phone, PC |
| 4 | Two PC views side by side: the spike's web build at `/ambrosia/` next to Talos's, served locally and drawn in headless Chromium | PC |
| 5 | Importing a file: the phone's picker (as `appBase.pickPlanFile`) and the PC view's | phone, PC |
| 6 | The phone's cold start under 5 s (Talos's check 8 budget); the PC view's load time measured | phone, PC |
| 7 | The spike APK and both web builds pass the package guard and the leak scan (`tools/leakScan.py`) | PC |

Your part, when you have time: install the spike APK, scan about 10 of your usual groceries, search a few generic foods and import a file. `phase0.md` records how many of your groceries Open Food Facts had with all four values; if few, the typed label (AM2.3) carries more of the load, decided then.

## 7. Staging
Phase 0 → the design round (gate 1 inside it) → building (gate 2 inside it, done last, AM7.2) → the joint release (gate 3): Ambrosia 0.1-alpha and Talos 0.4-alpha together, Talos with its red (LK1.3). Each release gets its tests written first and is checked on your phone, as with Talos.

**Built so far (2026-10-25, everything but gate 2):** the rules (foods and amounts, barcodes, the targets file and a day's targets, training and rest days, the week), the food sources (Open Food Facts, USDA's generic foods with their numbers and the new ranking), the state, the actions writing rows as 4e lays them out, the controller, every screen of the sketches in Ambrosia's look (`ambrosia/screens/`), the barcodeScan extension with ZXing only (AM5.1), and the targets brief for your Claude project (`apps/diet/plans/targetsFormat.md`), with tests (`tests/diet`) on a stand-in store. Every screen was drawn in headless Chromium. **Left for gate 2 (max effort):** the bulk check itself (4g) with its banner and Apply; `ambrosia/tables.py`, cloud upgrade 003 and the phone's database steps; sign-in, sync and the app's start (`main.py`, the phone and PC modes, the build settings); the backups (`dietBackups`, AM5.6) and `tools/restoreBackup.py`; Talos's weigh-in time (AM6.3).

---

## Decision log
- **2026-10-25 · AM1.1:** Ambrosia lives in `apps/diet/` in this repo and reuses the suite (rejected: a separate repo).
- **2026-10-25 · AM1.2:** the name on the phone is Ambrosia, the food of the Greek gods (you asked for something covert, then fantasy-epic; rejected: Diet Tracker, Food Tracker, Nutrition, Ration, Quartermaster, Payload, Cache, Mana, Grimoire, Alchemist).
- **2026-10-25 · AM1.3:** phone app and PC view from the start (replaces "phone only for now", chosen earlier the same day).
- **2026-10-25 · AM1.4:** Gym Tracker becomes Talos, the bronze giant who guarded Crete, to go with Ambrosia (also considered: Atlas, Olympus, Ichor, Herakles, Titan, Kratos, Bia, Colossus, Apollo, Adonis, Aegis, Hyperion, Hephaestus). Visible name only; it reaches the phone with Ambrosia's first release (rejected: a gym release right away with only the rename).
- **2026-10-25 · AM2.1–AM2.6:** calories, protein, fat and carbs; barcode scan and database search; a typed label when nothing's found; grams or servings; four meals; water (rejected: calories only, calories and protein, a foods list made by hand, quick numbers, the weekly waist).
- **2026-10-25 · AM3.1–AM3.3:** targets from a file your Claude project writes (rejected: typed into the app); training-day and rest-day targets by the gym plan's weekdays, the flex day once you train (rejected: only days with a workout logged, every gym plan day); the bulk check suggests and you confirm (rejected: automatic changes, no bulk check yet). This takes over Talos's optional weigh-in math (`docs/plan.md` WD2.5, WD2.6).
- **2026-10-25 · AM4.1:** (your rule) work at a max-effort gate (section 5) starts only once you've switched to max effort.
- **2026-10-25 · AM5.1–AM5.8:** (design round, first part, after Claude's phone test over USB) ZXing scans (rejected: Google's code scanner, which sends Google usage metrics; both); no packaged-food name search in the PC view (rejected: a relay of ours in Supabase); the new generic-food ranking (rejected: also a short list of other names for foods); shop barcodes only in your foods (rejected: asking Open Food Facts with a warning); History on the phone like Talos (rejected: PC view only); each app backs up its own tables (rejected: one backup for both); no nutrition in Talos's Monday summary for now (rejected: average kcal and protein there); the sketches as the basis for building (review page: https://claude.ai/artifact/1f6cav1vwBfzrbeBsqwACR).
- **2026-10-25 · AM6.1–AM6.4:** (design round at max effort, gate 1) the bulk check's exact rules worked out from your protocol (4g): weigh-ins count from days you trained, since the protocol is gym only; averages and the rate are rounded to 0.01 kg before comparing; a change counts from the day you apply it. Your choices: a thin block is left out entirely (rejected: only its own check skipped); when both checks call for a change the same way, only the big miss's applies (rejected: both added, 400 kcal; only the regular check's); Talos keeps the time you save today's weigh-in, as the protocol asks (rejected: no time); cloud upgrade 003 as in 4e. Ambrosia's backups get their own table, `dietBackups`, because Talos would read Ambrosia's rows in `backups` as its own last backup.
- **2026-10-25 · AM7.1–AM7.2:** Ambrosia's look is bold, sharp, aggressive gold with pink gradients and a goddess background (your words; rejected: greys only, the same red as Talos). Building does everything that doesn't need max effort first and gate 2 last, committing and pushing as it goes. Where you shop is asked just before the first version goes live.
