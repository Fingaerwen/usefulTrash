# usefulTrash: Gym App Plan

> **Status (2026-10-14):** Phase 0's 12 checks all passed (see `docs/phase0.md`), and the Google app is published (P1.1). The design round is done: code structure (3b), data tables, sync and data upgrades (14, 14b, 14c), releases (12b), diagnostics (12d), screens and look (6, 10, 12c). Staging decided (ST1.1, see "Staging"). Building 0.1-alpha. Built and tested on the PC: everything in 0.1-alpha's list (see "Staging"), including the phone app and PC view screens, the ping workflow, the release script and a signed trial build. Your one-time setup (`docs/setup.md`, steps 1-4) is done. Next: the first release and the check on your phone. This file is the single source of truth: every decision made after approval is applied in the sections below and listed in the **Decision log** at the end.

## Context
This is a personal suite of Python apps in one public repo (`claudProjects/usefulTrash/`). The first app is an Android **gym tracker**; a **diet app** comes later and will share the same cloud database and login. Every decision below was made with you point by point, including the resolution of the "brutal review" flaws. **Approving this plan starts Phase 0 only (the feasibility check).** The staging after that is decided from Phase 0's results (14.1).

---

## 1. Platform & stack
- Android only, single user (you). Python + **Flet 1.0.x** (pinned version; currently 1.0.3).
- **Cloud:** Supabase free tier (Postgres + login).
- **Phone:** local SQLite, offline-first. **Sync runs while the app is open** (2); gym dead-zones are covered by a sync queue.
- **PC view:** the same Flet app built as a static site on **GitHub Pages** (1). Published from a separate `gh-pages` branch (one commit, replaced on each update, with the known-secret-formats check on it) (P6.1). Built with `--no-cdn`, so Python and Flutter come from our own site. The PC view is online-only (no local queue). **Koyeb is dropped** (R1a), because it would hold your sign-in on a server.
- **If GitHub Pages fails Phase 0:** there's no PC view. The phone gets the PC-only features in a "More" menu (history editing for any day, CSV export, plan management, the backup warning). The 7-day edit limit lifts only in this fallback (R1d / R1d-1).
- **Dev Python is pinned to the Python version Flet bundles for Android** (R3).
- **One venv for the whole repo** (V2a), git-ignored. The PC runs **Bazzite** (immutable, so no system package installs). The tool was decided by Phase 0 check 11 (V1e): Flet's Android Python is 3.14.7, the same as the PC, so it's a plain `python3 -m venv` (no uv needed). Requirements are pinned in one file.

## 2. Security & privacy
- **Key rule (absolute):** secrets are **never written into any text** (chat, docs, code, commits, logs) and **never uploaded to any server or cloud**, GitHub Secrets included. Only key *names* are ever mentioned (K4c).
  - **Secrets (local only):** the Supabase secret/admin key, database passwords, Google Drive passes, the APK signing key, `.env`.
  - **Allowed public identifiers (K2a):** the Supabase address, the Supabase *publishable* key and the Google sign-in client ID. They ship inside the app and website; they're public by design and unlock nothing on their own.
  - Sign-in tokens go to Google/Supabase as part of logging in and are stored only on your device (K3a). **On the phone they're encrypted with a key locked inside the phone's security chip (Android Keystore, T1.1)**: only the encrypted copy is saved, in a folder Android leaves out of backups and transfers, so a copied file is useless anywhere else. If the key is ever lost, you sign in again.
  - GitHub's own temporary job token (created by GitHub, never seen or stored) is allowed for the keep-alive (3.3a / F15.1).
- **Leak protection:** a pre-commit secret scan blocks commits containing keys (K4a); GitHub push protection (K4b); `.env` and the signing key are in `.gitignore`.
- **Package guard (CS1.1):** our own packages are found through one local-path line each in the build settings; if a line were missing or mistyped, the build would download a stranger's package of the same name instead (PyPI already has a `securestore` and a `shared`). So the build script refuses to build if one of our packages lacks its local path, checks afterwards that every one was installed from our folders, and our package names get a unique prefix. The Phase 0 builds were checked: all three extensions came from our folders. Built: `tools/packageGuard.py`; our packages are now `usefulTrashShared`, `usefulTrashSecureStore`, `usefulTrashNativeGoogleSignIn` and `usefulTrashWeighInNotify` (BLD1).
- **Sign-in (AU1c):** native **Google sign-in on Android** with no stored secret: the app gets a Google ID token and Supabase checks it using only the public client ID. **If it fails on the phone (check 2), the fallback is an emailed 6-digit code** (F1.1). The **PC view** signs in with Google's official website sign-in, Google Identity Services (6.1): Google gives the page an ID token, Supabase checks it with a nonce, no secret anywhere. Emailed codes were ruled out: Supabase's built-in email only reaches your Supabase team (2 per hour), and your own email server's password would have to sit on Supabase. Supabase's Email sign-in stays **off** until one of these actually needs it.
- **Only your account allowed** (5.1), **sign-ups disabled after setup** (5.2). **The Google app stays in Testing, with your account as the only test user, until check 7 (P1.1).** Google won't publish without a homepage and a privacy policy page. Testing is fine for sign-in: Google blocks every other account (an extra lock on top of Supabase), shows a "not verified" warning you tap through, and asks again for approval once 7 days have passed since the last one, which only matters when signing in with Google again; the Supabase session doesn't depend on it. **Published 2026-10-13**, after check 7's 1-hour Drive test (which ran in Testing, D7.1), because Drive access in Testing would expire every 7 days. The homepage and privacy page live on the PC view's GitHub Pages site: `https://fingaerwen.github.io/usefulTrash/about.html` and `.../privacy.html` (source in `site/`). Since publishing, Google lets any account through its screen; Supabase's sign-up lock refuses them (tested in check 2: `422 signup_disabled`).
- Row-level security on every table.
- Commits use the **GitHub noreply email + your GitHub username** (6.1). Git uploads to GitHub with an SSH key (GH1a); `gh` isn't installed.
- No home server and no exposed IP; no name or personal details collected.

## 3. Repo, code style, docs
- **Public GitHub repo, no license** (view-only). Secrets live in an untracked `.env`, never committed (the docs included).
- Layout (CS1.1, details in 3b):
  ```
  usefulTrash/
    apps/gym/      the gym app: one codebase → phone APK + PC view website
      src/main.py  starts the app and picks phone or PC mode once
      src/gym/     tables.py · rules/ · actions.py · state.py · screens/
    apps/diet/     later, same pattern
    shared/        package usefulShared: cloud/ · signIn/ · store/ · sync/ · backup/ · tables.py · platform/
    cloud/         numbered cloud upgrade scripts, one list for the whole database
    extensions/    our Kotlin plugins: nativeGoogleSignIn, secureStore, weighInNotify
    tools/         PC-only scripts, never shipped: config, build, restore, leak scans
    tests/  plans/ (JSON spec + examples)  docs/  site/  .github/workflows/
    spikes/phase0/ the Phase 0 spike, kept as the record and never imported
  ```
- **camelCase literally everywhere** (11.4c): Python names, JSON, exercise IDs, database columns. Hand-written Postgres SQL quotes identifiers (`"weightKg"`). Flet's own snake_case APIs stay as they are.
- **Comments in all code:** a short description of what each part does.
- **Full documentation write-up** in `docs/` when the project is done, updated whenever anything relevant changes or is added.

## 3b. Code structure (CS1.1)
- **Rules are pure** (`gym/rules/`): cycle, progression, PRs/volume/streaks, weekly summary and plan-file checks never touch a screen, the database, the network or the clock; "today" is passed in. Most tests live here, and the phone and the PC view compute identical results from identical facts (F10.1).
- **All your facts are held in memory.** On start the app loads every row (phone: its own database; PC view: the cloud) and `state.py` calculates everything from them. Start-up has about 2 s of room under the 5 s limit (check 8: 2.8–3.3 s); the load time is measured at every release.
- **One write path:** screens call `actions.py`, which builds the row (new `id`, your `userId`) and hands it to the store. The store checks every column and stamps the edit time: the device's clock, or just after the version it replaces if the clock is behind that, so an edit always beats what it was made from. Screens never write rows themselves.
- **Two stores, one interface** (`usefulShared.store`): the phone saves to SQLite and the outbox in one transaction, and sync (phone only) sends the outbox and fetches changes made elsewhere. The PC view writes straight to the cloud; if that fails, nothing changes on screen and you see why.
- **Declarative screens** (Flet 1.0 components): a screen is drawn from the state and redraws itself when facts change. Not yet tried on the phone, so the first build stage checks the cold start stays under 5 s and the extensions work inside components; fallback: the spike's style. The Problems page shows the cold start time. Screens are also drawn in tests without a phone (`tests/screenTestKit.py` renders each component the way Flet does and presses its buttons), so most screen mistakes are caught before a phone build. The PC view's code never imports SQLite, because the browser's Python may lack it (a test checks).
- **Phone vs PC is decided once,** in `main.py` (phone: database + sync + phone sign-in + notifications + automatic backups; PC view: cloud store + browser sign-in + Plans/History/Backup tabs). No scattered "if website" checks.
- **Network calls never block the screen** (phone: a worker thread; browser: fetch). The phone's database stays on the app's main loop, so it needs no locks.
- **Shared code is its own local package** (`usefulShared`), built into the APK and the website the same way as the extensions (Flet's `dev_packages`), so the diet app reuses it unchanged.
- **Package guard:** see section 2.
- **The spike stays frozen:** its proven modules (Supabase calls, session keeper, offline queue, Drive access) move into `shared/`, cleaned up and with tests; `makePublicConfig.py` moves to `tools/`.

## 4. Plan JSON (written in your Claude project)
```json
{
  "planId": "pushPullLegs", "name": "Push Pull Legs", "version": 2, "weeklyTarget": 4,
  "cycle": [
    {"title": "Push", "exercises": [
      {"exerciseId": "benchPress", "name": "Bench Press", "equipment": "barbell",
       "body": "upper", "sets": 4, "repsMin": 8, "repsMax": 12, "weightKg": 80,
       "restSec": 120, "incrementKg": 2.5, "notes": "pause at bottom"},
      {"exerciseId": "dips", "name": "Dips", "equipment": "bodyweight",
       "sets": 3, "repsMin": 8, "repsMax": 12, "restSec": 90},
      {"exerciseId": "inclineWalk", "name": "Incline Walk", "type": "cardio", "minutes": 15}
    ]},
    {"title": "Rest", "restDay": true}
  ]
}
```
- `equipment`: `barbell` | `dumbbell` | `bodyweight` | `machine`. Dumbbell `weightKg` is **one dumbbell**.
- `incrementKg` is optional; the default comes from `body` (upper 2.5 / lower 5) (9.1).
- `weeklyTarget` lives in the plan (17.1a). Mid-week imports: **Monday's plan decides** that week's target (17.4a).
- `notes` = form cues shown on the Today screen (17.3a). Rest time is display only, no timer.
- **Import:** PC view normally; phone file import only as a fallback (G2b-2). Exercises are matched by `exerciseId`, else by name with a prompt (11.3). **You choose the starting cycle day** on import (17.2c). **New plan weights win** (8.12). History stays continuous, so a reset shows as a dip (8.16d).
- **The format spec is `plans/planFormat.md`**, for you to paste into your Claude project; the checks live in `gym/rules/planFile.py` (PF1). A file being imported is checked strictly: an unknown field is refused with the closest real one as a hint, so typos can't slip through. A plan already stored is read leniently, so an older app can still read a plan with fields a newer one added. An exercise in several steps needs the same settings in each (notes and rest time may differ), because progress is tracked per exercise.
- **Likely matches (11.3, PF1):** an exercise with a new ID is asked about if a known exercise of the same kind and equipment has a similar name (ignoring case and punctuation, or one name inside the other) and isn't in the new plan itself. Each is asked about once, best match first. "Yes" stores the known ID in the plan, so the history carries on.
- **A new plan takes effect today, or tomorrow if a workout is already logged today** (PF1), so one day's workout never mixes two plans.
- A week whose Monday had no plan yet (your first import) takes the first plan's weekly target.

## 5. Cycle & rest
- A **rotating cycle**; a missed day never shifts dates, the next step just waits.
- **Strict about extra rest:** an unplanned rest day does not use up a planned Rest step (13.3).
- **Train anyway** on a planned Rest step: the next workout is done and the rest step is kept for later (19.1c-2 / 13.1a). **At most one rest is owed (KR1.2):** training through two Rest steps in a row owes one rest day, not two, then the plan carries on. Training on that owed rest day keeps it owed.
- **A planned Rest step is used up when the day ends** with it as the current step and no workout logged, even if the app was never opened (R4a).
- **Nothing here is stored; it's all recalculated (F10.1).** Cycle position, rest-step use and midnight auto-finish are worked out each time from the facts: logged sessions (each records which plan step it was, 14), and plan imports with the date and starting step you chose. So the phone and the PC view always agree, and nothing has to run at midnight. These rules get written as automated tests first, including edge cases such as "train anyway" twice in a row on a Rest step (done: `tests/gym/rules/testCycle.py`).

## 6. Today screen (19.1)
```
Push · day 1 of 5 · week 2/4      3 waiting  ⋮
─────────────────────────────────────────────
Bench Press   4×9 @ 82.5 kg ↑new         [✓]
  rest 2:00 · "pause at bottom"  ▾ sets · skip
Dips          3×10                       [✓]
Incline Walk  15 min                     [✓]
─────────────────────────────────────────────
              [ Finish workout ]
  Today     Progress     Week     Weight
```
- **Approved layout (SC2.1).** The top line is the plan step's title (from your plan), its place in the cycle, and workouts done this week vs the weekly target. A rest day shows "Rest day · next: Pull" with a **[ Train anyway ]** button. The **⋮** menu holds Problems (12d) and Sign out.
- **Steps today (SC4.1):** one line under Finish, on rest days too: `Steps today: 14,000 ✎` (CA1.1).
- **[✓]** logs it as targeted. **▾ sets** opens per-set rows pre-filled with the target (19.1a-1). **skip** = today only.
- **Finish workout:** anything untouched is **auto-skipped** (19.1b-1) and the cycle advances. **Forgot to finish → it auto-finishes at midnight** the same way (R5a).
- **One workout per day (DT1.1):** logging again later the same day adds to that day's workout.
- **Taps (BLD1):** [✓] logs the exercise as targeted, and tapping it again takes it back. Taking back the day's last entry removes the workout too, finished or not, so a mistaken tap never moves the cycle on. Finish is available once something is logged. Train anyway applies to that day only. Targets in 0.1-alpha are the plan's own (repsMin at the plan's weight); suggestions come with 0.2-alpha.
- **Waiting changes (SC1.1):** while changes wait to be sent (no internet), a small, quiet "3 waiting" shows at the top; it disappears once they're sent. The 3-day "Not synced" banner stays (G9.2b).
- Past days can be edited on the **phone for the last 7 days** (19.1f-1) and on the **PC for any day**. Edits recalculate suggestions, streaks and summaries.

## 7. Progression
- **One rep target for all sets** (8.1). A new exercise starts at `repsMin` (12.1).
- All sets hit the target → next target = **lowest set + 1** (R6a). All sets at `repsMax` or above → **+increment kg**, and reps reset to `repsMin`.
- **Miss** = 2 or more sets under `repsMin` (a 1-set exercise: that set) (8.14a). **2 missed sessions in a row** → drop to the **last lower weight that worked**, with the **reps you last achieved there** as the target (R7b). If there is none → no suggestion (8.10 / 8.15 / 8.16d).
- **After a drop, you must hit the top of the range 2 sessions in a row** before the app suggests going heavier again, which prevents yo-yoing (R7c-1).
- **Skipped exercises are ignored** by progression (19.1e-1).
- Suggestions are **pre-filled** and tagged `↑new`, with Undo; logging one counts as accepting it (8.3). Suggestions are recalculated from your logged history, not stored (F10.1); an Undo is saved as a fact on that day's exercise entry.
- **Bodyweight exercises:** reps keep rising past the range, with no weight suggestions (10.9a).

## 8. Progress & stats
- **PRs:** heaviest weight; estimated 1RM (Epley, **only from sets of 10 reps or fewer**) (16.2a); most reps at the **current weight only** (16.3a). Bodyweight exercises: most reps in one set (10.10a).
- **Volume** (sets×reps×kg): per exercise, per workout, per week, vs last week. **Dumbbells are doubled in the combined totals only; one dumbbell is displayed everywhere** (10.4). Bodyweight exercises: total reps, kept separate (10.2).
- **Consistency:** a weekly session target (4.1), streaks = weeks in a row hitting it, exercise completion %. Calendar: trained / rest / **missed = 3rd+ unplanned rest day in a row** (4.5 / 4.7a / 4.9a). Missed days are display-only; **the weekly target wins** for streaks (4.8a).
- Weeks run Monday–Sunday. Dates are plain calendar dates (16.4c).

## 9. Weekly summary & weight
- **Summary:** completion, volume vs last week, PRs hit, weight change. Nutrition is added when the diet app exists (15.1).
- **Summary also shows** total cardio minutes for the week (G9.4a). Cardio counts toward completion %.
- **Daily steps (CA1.1):** you can enter your day's step total (what your phone's step counter shows) once a day, any day, rest days included; entering it again replaces it. It's converted at **100 steps = 1 minute** (a brisk walking pace) and added to the week's cardio, shown as e.g. `Cardio 185 min (45 gym + 140 from steps)`. Steps aren't a workout: they don't move the cycle, don't count toward completion %, the weekly workout count or streaks, and a day with only steps is still a rest day.
- **Weight:** a weekly weigh-in in the gym app plus a trend chart. The reminder is **Friday 07:00** (G9.1), with the text **"Time to weigh in"** (NT1.2, replaces 16.1a's "same day, morning, after toilet, before food"). **One weight per day (DT2.1):** entering it again replaces it.
- **Past exercises** (not in the current plan) appear in Progress under "Past exercises", with full history (G10a).
- **"Not synced" banner** appears after 3 days of unsynced changes (G9.2b).

## 10. Screens
- **Phone tabs:** Today · Progress · Week · Weight (18.1 + 18.3c). The app opens on the **last tab used** (18.2c).
- **What each tab holds (SC3.1):** **Progress** = each exercise with its PRs and chart; **Week** = this week's summary, the calendar and the streak; **Weight** = the weigh-in and its chart. Progress, as approved:
  ```
  Progress                                     ⋮
  ─────────────────────────────────────────────
  Bench Press   now 82.5 kg × 9    PR 85 kg   ▸
  Squat         now 120 kg × 6     PR 120 kg  ▸
  Dips          now 12 reps        PR 14 reps ▸
  Past exercises (2)                          ▸
  ```
  Tapping an exercise opens its detail: a chart (3M · 1Y · All), its PRs (heaviest, estimated 1RM, most reps at the current weight; 8) and its history:
  ```
  Bench Press                      3M · 1Y · All
   kg  ▁▂▃▃▄▅▅▆
  PRs: heaviest 85 kg · 1RM ~107 kg · 12 reps @ 82.5 kg
  14 Oct  4×9 @ 82.5   ·   10 Oct  4×8 @ 82.5   · …
  ```
  The app says "PR" (personal record).
- **Week (SC4.1)**, as approved (◂ ▸ steps through earlier weeks; tapping a day in the calendar row enters or fixes that day's steps: on the phone for the last 7 days, on the PC for any day):
  ```
  Week 14–20 Oct                      ◂ ▸   ⋮
  ─────────────────────────────────────────────
  Workouts    3 of 4          Streak   5 weeks
  Completion  92%             Cardio   185 min
                              (45 gym + 140 from steps)
  Volume      18,400 kg   ↑ 6% vs last week
  PRs         Bench 85 kg · Squat 120 kg
  Weight      81.2 kg   ↓ 0.4 kg
  ─────────────────────────────────────────────
  Mo ✓   Tu ·   We ·   Th ✗   Fr ✓   Sa     Su
  ✓ trained   · rest   ✗ missed
  ```
  All numbers in these sketches are examples. A part that's zero is left out, e.g. `Cardio 140 min (from steps)` when no gym cardio was logged.
- **Weight (SC5.1)**, as approved (any day works, Friday is preselected; saving again the same day replaces it, DT2.1; on Fridays a "weigh-in due" banner shows until you've weighed in, 18.4a). No hint text on this screen:
  ```
  Weight                                       ⋮
  ─────────────────────────────────────────────
  Fri 16 Oct    [ 81.2 ] kg              [Save]
  ─────────────────────────────────────────────
   kg  ▆▅▅▄▄▃▃▂                3M · 1Y · All
  Last 4:  82.0 · 81.8 · 81.6 · 81.2   (↓ 0.8 kg)
  ```
- **Banners at the top of any tab** (18.4a): weekly summary ready, not synced, weigh-in due.
- **PC:** the same tabs + Plans (import/switch/archive) + History (edit any day) + Export CSV + backup status with a "Back up now" button (F14.1). 0.1-alpha's PC view has Today and Plans (import, with the active and earlier plans listed); Switch and Archive come later (importing again works meanwhile), History, Export and backups with 0.3-alpha (BLD1).
- **PC screens (SC6.1)**, as approved:
  ```
  Plans      Active:  Push Pull Legs (v2) · since 6 Oct · 4/week
             [ Import a plan file… ]
             Earlier: Full Body (v1) · 1 Sep – 5 Oct   [Switch] [Archive]

  History    ◂ October 2026 ▸
             Mo 13  Push · 5 exercises · finished      [Edit]
             Su 12  Rest · 9,500 steps                 [Edit]

  Backup     Last backup: 12 Sep (phone) · 32 days ago
             [ Back up now ]   [ Export CSV ]
  ```
  Import: pick the file → problems listed in plain words (G8a) → "is this the same exercise?" for likely matches (11.3) → choose the starting day (17.2c) → it takes effect. Edit opens the day laid out like Today (sets, steps, weight, or delete the workout). Backup warns at 60+ days (3.4).
- **First launch (phone):** Sign in with Google → "Downloading your data… N rows" (14b) → if no plan exists yet: "Import your plan in the PC view", with "Import a file" as the fallback (G2b-2) → Today.

## 11. Notifications & background
- Sync and banners are in-app only (2).
- The weekly weigh-in **phone notification** works (Phase 0 check 5): our own small Android plugin, `extensions/weighInNotify` (C5d), schedules it with Android's alarms. No third-party notification library. It uses **alarm-clock mode**, because OnePlus delayed normal exact alarms by up to an hour (F21.2), and the app's battery setting should be **"Unrestricted"** so the phone doesn't kill it in the background.

## 12. Backups & scheduled jobs (no stored secrets anywhere)
- **If Phase 0 shows that automatic Drive renewal needs a secret inside the app:** the backup moves to a **local timer on your Linux PC** instead, with its secrets in a local file only (R2b).
- **Automatic backup from the phone (F14.1):** when the app opens and the last backup is 30+ days old, it creates **zipped CSV files** (one per table, G9.3b) and uploads them to Google Drive with *your own sign-in*. The permission is limited to files the app created. **Keep the last 3.** A backup record prevents duplicate backups. The **PC view** has a **"Back up now"** button instead of automatic backups, because a browser needs a click and a Google popup every time it asks for Drive access. Not tested yet: the browser's Drive permission (Google Identity Services' token client) gets a small test before the button relies on it.
- The PC view **warns when the last backup is 60+ days old** (3.4).
- **Restore (F13.1):** a small restore script plus a short guide. It's tested once when backups are built (into a spare copy, never the live data) and again after every data-structure change. Each backup records its data-structure version, so older backups still restore correctly.
- **Daily database ping (GitHub Actions):** uses only the public address + publishable key, calling a harmless `ping` function (K1c / 7.4), so the Supabase free tier doesn't pause. Whether the ping counts as activity is **watched for the first 2 weeks** (R10). The ping gets the address and publishable key from **GitHub Actions variables** in the repo settings, set once by you (RL2.1), so the repo stays free of them (C2a); the apps get them from the generated config file. The workflow uses no third-party actions (only `curl`), has the minimum permissions and prints nothing but the result. Built: `.github/workflows/dailyPing.yml`, daily at 06:17 UTC and by hand; the keep-alive step runs even on a day the ping fails. GitHub shows a step's variables in its log; both are public and already in the website's files.
- **Keep-alive (F15.1):** GitHub switches off scheduled jobs after 60 days without repo activity, so the ping job uses GitHub's temporary job token to call GitHub's "enable workflow" API, which resets that timer without any commits. Checked when the workflows are built; if it doesn't reset the timer, fall back to a monthly keep-alive commit (3.3a).

## 12b. Releases, updates & data upgrades
- **Versions:** `0.1-alpha` → `0.2-alpha` → … (the middle number bumps every release, with no third number) (V3a). If Android's tooling requires three numbers, it's stored internally as `0.1.0` while every visible name stays `0.1-alpha` (Phase 0 check 12: not needed; `0.1-alpha` is accepted as is, and the internal versionCode must go up by one each release, so it's simply the middle number: `0.1-alpha` → 1, `0.2-alpha` → 2). The Phase 0 spike used `0.1-alpha` only to run that check. GitHub releases are **normal releases named alpha**, not pre-releases, so Obtainium picks them up (V4b).
- **App identity (RL1.3):** the app is called **Gym Tracker**, on the phone and in the PC view's title. Android package `io.github.fingaerwen.gymtracker`, set explicitly in the build settings and separate from the Phase 0 spike, which gets uninstalled once Gym Tracker works.
- **Releases:** built and **signed on your PC**, then uploaded to GitHub Releases (G4c-1). The APK contains only the allowed public identifiers. The phone gets updates automatically through **Obtainium** (G4c). Only the **arm64** APK is built (your phone's CPU type), so one small file per release instead of the 140 MB all-types APK.
- **Release script (`tools/buildRelease.py`):** (1) checks: on `main` with nothing uncommitted, tests pass, version raised, package guard before building (CS1.1); (2) writes the public config from `.env`; (3) builds the signed APK and the PC view; (4) checks after: package guard, secret scan of the APK and the website (no secret formats, no `.env` value except the three public ones), and the APK's signing certificate matches the release key's public fingerprint kept in the repo; (5) tags the version and, once you confirm any cloud upgrade is done (14c), publishes the PC view (P6.1); (6) tells you the rest: create the release on GitHub's website from the tag and drag the APK in (no GitHub token needed, `gh` isn't installed); Obtainium then updates the phone. Built: tags are `gym-v<version>`, and `--buildOnly` is a trial run that tags and publishes nothing. The leak scan (`tools/leakScan.py`) also looks for the signing password, inside zips within zips.
- **One-time setup for Gym Tracker** (the guide: `docs/setup.md`): two Android clients in Google Cloud for the new package (the release key's and the debug key's fingerprints; both are public), the two GitHub Actions variables, Obtainium pointed at the repo, then on the phone: sign in, allow Drive when asked, battery "Unrestricted", uninstall the Phase 0 app.
- **Signing key:** stays on your PC, with a copy on a **second drive** (G3a). Its passwords are passed to the build through environment variables loaded from a local file outside the repo, never typed on the command line, because shell history counts as a log (F20). Made once with Java's `keytool`: a key file plus a random password, generated straight into a folder outside the repo that only you can read, and never shown. The certificate's name holds no personal details, because anyone can read it from the APK. That folder (key + password file) is what gets copied to the second drive. Checked in Flet 1.0.3: its Android build reads the signing values only from environment variables, and its logs show the build command but never the environment, so the passwords can't end up in a file or in any output. If it's ever lost: uninstall, reinstall, sign in again; only unsynced data is lost. Made 2026-10-14 with `tools/makeSigningKey.py` into `~/.local/share/usefulTrash/signing` (certificate `CN=Gym Tracker`, RSA 4096, valid until 2054); its public SHA-256 is in `apps/gym/signingCertificate.txt`. Backed up 2026-10-14 (KB1.1) to the 500 GB NVMe drive (ext4, so it stays readable only by you), checked identical to the original.
- **Data-structure changes:** numbered upgrade scripts: you paste the cloud ones, the phone runs its own, and all are tested on your PC first. Details in 14c (G6a, UP1.1, UP2.1).
- **Plan import:** the PC view is the normal path. **Phone file import is a fallback only** when the PC view is unavailable (G2b-2). If GitHub Pages fails, the PC features move to the phone (R1d); Koyeb is dropped (R1a).
- **Invalid plans are rejected**, listing every error in plain words (G8a). Checks include missing fields, repsMin > repsMax, duplicate IDs, and a weeklyTarget outside 1–7 (F12.1). A target faster than the cycle's own pace (training steps ÷ cycle length × 7) isn't rejected, just flagged with a warning, because a short cycle can run more than once a week.

## 12c. Look & feel (G1)
Dark mode that follows the phone setting, minimal screens and taps, medium-sized tap targets. **Accent (LK1.1):** white in dark mode, black in light mode, so the app is black and white either way (buttons, ✓ marks and charts included).

## 12d. Diagnostics (DG1.1)
- **"Problems" page** in the app, phone and PC view (DG1.1), reached from a small menu (exact place set with the screens): app version and schema number, sync status (changes waiting, the oldest one, the last successful sync, changes the cloud refused and why), the last backup, and recent errors in plain words with a technical line underneath. A **Copy** button puts the whole report on the clipboard for you to paste to me; **Clear** empties it. An error that needs you (a refused change, a wrong clock, an update needed) also shows a banner on any tab (18.4a). Nothing is ever sent anywhere automatically: no crash reports, no analytics.
- **One shared log** (`usefulShared.platform`): on the phone a small file in the app's private storage (two files of 256 KB, oldest dropped first); in the PC view memory only, so nothing is stored in your browser. Release builds don't write to Android's system log.
- **No secrets or personal details in the log:** code logs events and kinds, never values: HTTP errors as status, error code and a short message (capped, as in Phase 0); tokens only as fingerprints (the first 8 characters of their SHA-256, as in Phase 0). Every line also passes a scrubber that removes anything token-, key- or email-shaped, as a safety net. The Problems page runs the Phase 0 log check and shows its result ("0 token-shaped strings").
- **Crashes:** an unexpected error is written to the log before anything else, so after a crash the next start shows what happened. If the app can't start at all, the fallback is reading the log over USB.
- **Tested:** fake tokens, keys and emails go through the scrubber and must come out removed; a full fake sign-in, renewal and sync run must leave no token value in the log. The scrubber is also given the session's current tokens, because Supabase's refresh tokens are short and look like nothing in particular.

## 13. Diet app (later)
- Same Supabase project, login and naming. For now the gym app only **shares weight + training days**. Nutrition tables and goals are designed when the diet app is planned (15.1).

## 14. Data tables (camelCase)
Every synced row has `id` (UUID), `userId`, `updatedAt` (when the edit was made, from the device's clock, to the microsecond), `deleted` (rows are never really removed: deleting is an edit like any other, so it syncs and can be undone) and `cloudUpdatedAt` (stamped by the cloud when it stores a change; used only to fetch what's new, never to decide which edit wins) (SY1.1). Conflicting edits: **the newest edit time wins** (G7a), so a late-arriving offline edit can't overwrite a newer one.

| Table | One row per | Columns besides the common ones |
|---|---|---|
| `plans` (gym) | plan import | `importedAt` (orders imports taking effect the same day), `effectiveDate`, `startStep`, `planJson` (the plan as imported, with matched exercise IDs), `archived` |
| `sessions` (gym) | workout day (DT1.1) | `date`, `planImportId` + `stepIndex` (which plan step this workout was), `finishedAt` (empty until you tap Finish) |
| `exerciseLogs` (gym) | exercise per workout day | `date`, `exerciseId`, `targetReps` + `targetWeightKg` (what Today suggested), `sets` (a list of reps + kg), `minutes` (cardio), `skipped`, `declinedSuggestion` (an Undo) |
| `bodyWeight` (shared) | day (DT2.1) | `date`, `weightKg` |
| `dailySteps` (shared) | day (CA1.1) | `date`, `steps` |
| `backups` (shared) | backup | `madeAt`, `fileName`, `driveFileId`, `sizeBytes`, `schemaVersion`, `madeBy` (phone or PC view) |
| `cloudInfo` (cloud only) | one row in total | `schemaVersion`, `minAppSchema` (UP1.1); the apps only read it |

- **IDs that can't duplicate (DT1.1 / DT2.1):** a day's workout, an exercise on a day, a day's weight and a day's steps get IDs calculated from your user ID and the date (plus the exercise), so the phone and the PC view logging the same thing produce the same row, never two. Plan imports and backups get random IDs.
- **Only facts are stored (F10.1).** Recalculated instead: cycle position, rest-step use, auto-finish (a past day's workout counts as finished), auto-skips (an exercise with no entry in a finished workout), suggestions, PRs, streaks, and the exercise list itself: current and past names come from the plan imports, which replaces the planned `exercises` table (R8) with the same uses (11.3 matching, "Past exercises"). Cardio entries live in `exerciseLogs`, which replaces `cardioLogs`. No `cycleState` or `suggestions` tables.
- **Each workout records its plan step**, so editing or deleting an old day never rewrites the steps of later ones.
- **Dates** are the device's local calendar date when you log (16.4c); edit times are exact moments (UTC).
- **In the cloud (F11.1 + SY1.1):** one trigger on every table ignores a change that isn't newer than the stored one, refuses a change stamped more than 5 minutes in the future (a phone with a wrong clock would otherwise win every conflict; the app then says "check your phone's clock"), and stamps `cloudUpdatedAt`. `updatedAt` always comes from the device that made the edit; the server never stamps it (unlike the Phase 0 test table). Row-level security: only your own rows, which you can read, add and change but not remove. The database enforces no links between tables, because offline changes can arrive in any order; the rules ignore leftovers.
- **On the phone:** the same tables in SQLite, plus two local-only ones: `outbox` (changes waiting to be sent) and `syncState` (how far fetching has got).

## 14b. Sync (SY2.1)
- **Sending (phone):** each change goes into the phone's database and the `outbox` in one transaction. Sync sends the outbox in batches as upserts; the cloud's trigger keeps the newest. An entry leaves the outbox only once the cloud has it and the row hasn't been edited again in the meantime.
- **Fetching (phone and PC view):** each table is asked for rows whose `cloudUpdatedAt` is at or after the last one seen minus 5 minutes (so a change stamped a moment before it finished saving isn't missed), in pages ordered by `cloudUpdatedAt` and `id`. A fetched row replaces the local one only if it's newer, so getting the same change twice is harmless.
- **When:** at start, a few seconds after every change, every minute while the app is open, and when it comes back on screen. **No internet** (your gym: up to ~30 minutes at a time) changes nothing while you train: everything is saved on the phone first, and the app keeps trying every minute, so changes go out within about a minute of the connection coming back (SY2.2). Each request gives up after 15 seconds, so a weak connection can't stall sync, and a send cut off halfway is simply repeated (getting the same change twice is harmless). Changes still waiting when you close the app go out the next time it's open. No live connection: simpler, and it works the same in the browser.
- **First download** (new install or reinstall): everything is fetched before the Today screen shows, with a progress count. Signing in needs the internet anyway.
- **PC view:** loads everything at sign-in, writes straight to the cloud (CS1.1), and fetches every minute, so changes from the phone show up without reloading.
- **Version check (UP1.1):** before each sync the app reads `cloudInfo` and syncs only if `minAppSchema` ≤ its own schema number ≤ `schemaVersion`. Otherwise it stops, keeps the outbox and says what to update.
- **Signed out:** sync pauses and the outbox is kept. The phone's database remembers whose data it holds and is cleared if a different account ever signs in (impossible today: sign-ups are off).
- **"Not synced" banner** (G9.2b): when the oldest outbox entry is 3+ days old. Changes the cloud refused show the reason.
- **Refused changes:** the cloud takes a batch all or nothing, so a refused batch is sent again row by row to find the refused row. That row is set aside with the cloud's reason (Problems page), the rest still go, and it's sent again once it's edited or you tap "Try again". A connection dropping meanwhile refuses nothing.
- **Backups** sync first, then write from the device's copy (phone) or the loaded copy (PC view). Deleted rows are included, so a restore is exact.

## 14c. Data upgrades (UP1.1 / UP2.1)
- **One numbered list:** `cloud/NNN_name.sql` changes the cloud, and each app carries the matching phone steps. An app's schema number is the last upgrade it was built for; the version check (14b) compares it with `cloudInfo`.
- **Cloud: you paste each script** into Supabase's SQL editor (copied with GitHub's "Copy raw file", as in check 3) (UP2.1), because changing tables needs admin access that no app or server may hold; no database password exists anywhere. Each script runs as one transaction (a failure changes nothing), refuses to run twice or out of order, only adds things (UP1.1), holds structure only (never data or secrets), and ends by raising `cloudInfo.schemaVersion` and showing "upgrade NNN done". `minAppSchema` is raised only for an unavoidable breaking change: older apps then stop syncing until updated (UP1.1). Script 001 creates the real tables and removes the Phase 0 test table.
- **Filling in existing data** (say, a new column worked out from old ones) happens in the cloud only. The script sets those rows' edit time to the upgrade time, so the change wins the newest-edit rule and reaches every device by sync. Phone steps only change the structure of the phone's database.
- **Phone steps** run by themselves when the updated app starts, before anything else. The app first copies its database file, then runs the pending steps in one transaction; if anything fails, it puts the copy back and shows the error, so nothing is lost.
- **Tested on your PC first (G6a):** cloud scripts run in a local Postgres (a podman container with the same major version as your Supabase project, plus a small stand-in for Supabase's sign-in functions and roles), built from script 001 upward, which also proves the scripts can rebuild the whole database from nothing, and loaded with a copy of your data from the latest backup. Your data never leaves the PC for this. Phone steps are tested with pytest on the same copy, including a change still waiting in the outbox from before the upgrade. The restore script is re-tested after every structure change (F13.1).
- **Release order when there's an upgrade:** the phone has synced (nothing waiting, so no offline edit loses to a data fill-in), a fresh backup exists, you paste the script and see "done", and only then are the PC view and the APK published.

---

## Phase 0: feasibility check (what approval starts)
A throwaway Flet app in `usefulTrash/spikes/phase0/` that answers each question with pass/fail:
1. Builds as an APK and installs on your phone.
2. Google sign-in works on Android and is restricted to your email (AU1c). Fail → emailed-code fallback (F1.1).
3. Reads/writes a camelCase-column row in Supabase with RLS on.
4. Works offline: writes are queued and synced once the connection is back.
5. A scheduled local notification fires (weigh-in reminder, Friday 07:00).
6. A `flet build web` version on GitHub Pages can sign in (Google in the browser or emailed code, chosen at this check) and read the same row.
7. The phone uploads a small file to Google Drive using your sign-in, **with no secret in the app, and still works after the 1-hour token expiry** (R2). Runs while the Google app is still in Testing (D7.1): the 1-hour test doesn't depend on publishing. Publishing (homepage + privacy policy page, P1.1) follows once you've approved the pages, so Drive access stops expiring every 7 days. Fail → PC timer backup (R2b). This doesn't depend on check 2: on Android the Drive permission comes from Google Play services, separate from how you sign into Supabase (F3).
8. **Cold start under 5 seconds** on your phone (G5b).
9. A JSON file can be picked from phone storage (fallback import).
10. A pre-commit secret scan blocks a commit containing a fake key.
11. Records the Python version Flet bundles for Android, which decides the venv tool (V1e / R3). This runs first, in a temporary venv.

12. Builds with the version name `0.1-alpha` and confirms whether Android needs a three-number internal version.

**How the checks depend on each other (F3):** checks 3 and 4 need *a* Supabase sign-in (Google, or the emailed-code fallback). Check 6 needs a sign-in in the browser. Check 7 needs only Google's Drive permission on the phone, so it can be tested even if check 2 fails.

**Check 2 requirements: "only your account", without your email in the public repo (F8):**
- Your email address never goes into code, SQL or docs in this repo; it's a personal detail and the repo is public.
- Enforcement instead: sign in once with your Google account → in Supabase, turn off "Allow new users to sign up" (5.2) → check that a second Google account is refused. Row-level security then keeps every row to your user ID. While the Google app is in Testing (P1.1), Google blocks other accounts before Supabase sees them, so to test Supabase's own lock: add the second account as a test user for a moment, check Supabase refuses it, then remove it again.
- Turn off every Supabase sign-in method that isn't used. Email sign-in stays off until the F1.1 fallback or the PC view needs it; if it's turned on, test that sign-in *before* turning sign-ups off, or confirm it still works after.

**Check 2 requirements: things that can fail silently (F9):**
- **Google Cloud needs two clients:** a **Web** client (its public ID goes into the app, and Google issues the sign-in token for it) and an **Android** client (package `io.github.fingaerwen.phase0` + the public SHA-1 fingerprint of the signing certificate). Phase 0 uses the debug key's fingerprint; the release key's fingerprint is added at the first release.
- **Google creates a client secret for the Web client automatically.** Never copy, download or paste it anywhere; it isn't needed. (The pre-commit hook blocks it as a backstop, F5.)
- **Supabase's Google provider gets the client ID only.** If Supabase refuses to save without the secret → **stop**: that's the AU1 conflict with the key rule, and we decide again. *Checked 2026-10-12 in the dashboard's own form code: with Google enabled, only "Client IDs" is required; "Client Secret (for OAuth)" is optional and only used for website sign-in.*
- **Nonce:** the app makes a random one-time value, sends its SHA-256 hash to Google and the raw value to Supabase, so a stolen sign-in token can't be replayed.
- **One small module for all Supabase calls**, plain HTTP rather than the `supabase-py` library (heavy, has compiled parts that may not have Android builds, slows start-up). One module also means the network layer can be swapped if the browser build (check 6) needs it.
- **Every path in the Kotlin sign-in plugin must reply** to Python, including "cancelled" and errors: Flet method calls have no default timeout, so a missing reply would leave the button waiting forever.
- **Before any token is stored:** Android cloud backup is off (F4, verify in the built manifest) and the Supabase project isn't paused (F7).
- **Check 2 keeps the session in memory only** (closing the app signs you out). **Before check 4, decide how tokens are stored on the phone:** where, whether they're encrypted with a key locked inside the phone (Android Keystore), and backups. `allowBackup="false"` (F4) stops cloud backups, but on Android 12+ some phone makers still copy app files during a phone-to-phone transfer (Android's own docs), so only encryption with a key that never leaves the phone fully keeps tokens on one device. **Decided 2026-10-12: T1.1**, see the decision log.

**Your account steps** (guided, done by you): a GitHub account/repo, a Supabase project, Google sign-in setup in Google Cloud (Testing with you as the only test user until check 7, then published; Drive "files this app created" permission), and Obtainium on your phone.

Before Phase 0: check free disk space for Flutter + Android SDK + Java (several GB) (R11).

Setup during Phase 0: create `usefulTrash/` with git (noreply email, username), the GitHub repo and the Supabase project (you'll do the account steps), and **delete the old `claudProjects/gymtracker/` demo** (done, P0.1a). Results are written up in `docs/phase0.md`, then we decide the staging together.

## Staging (ST1.1)
Decided 2026-10-14, after Phase 0 and the design round. Each release gets its tests written first and is checked on your phone before the next one starts.
- **0.1-alpha · Log a workout:** cloud script 001 (real tables, trigger, `ping`), sign-in and session keeper, phone database + outbox + sync with the version check, the Problems page and log, plan import (PC view, phone file as the fallback), the cycle and rest rules, the Today screen (✓, sets, skip, Finish, steps line, "N waiting"), the daily ping workflow, the release script and the first signed release through Obtainium. Also: the declarative-screens check on the phone (CS1.1), the one-time setup (12b), and the privacy policy updated for daily steps.
- **0.2-alpha · See progress:** progression suggestions (↑new, Undo), the Progress, Week and Weight tabs with charts, banners, the Friday notification.
- **0.3-alpha · PC view and safety:** History editing, automatic Drive backups + "Back up now" (its browser Drive permission tested first), CSV export, the restore script and its test.

## Verification
- Phase 0: each of the 12 checks recorded as pass/fail with notes. **If Google sign-in on Android fails (check 2), the fallback is an emailed code (F1.1).** Any other fail → we revisit that decision before building.
- Later phases: automated tests for plan import/validation, cycle + rest rules, progression rules, PR/volume/streak math and sync against a fake cloud (offline → online, conflicts both ways, the 5-minute fetch overlap, refused changes, first download, the version check; 14b). End to end: airplane mode → log → reconnect → shows in the PC view.
- **Sync against the real server (built 2026-10-14):** besides the fake cloud, the cloud calls and whole sync rounds between two devices run against PostgREST (the Data API server Supabase runs) on a local copy of the cloud built from `cloud/`, in a podman pod reachable only from this PC (`tests/cloud/testDataApi.py`). Every rule is also checked by breaking it on purpose and seeing a test fail.

---

## Decision log
Newest at the bottom. Every decision made after the plan was approved gets a line here, and the sections above are updated to match, so the plan can't drift again. Codes match the questions they answered.

- **2026-10-06 · P0.1a:** delete the old `gymtracker` demo (done).
- **2026-10-06 · GH1a:** git uploads to GitHub with an SSH key.
- **2026-10-06 · AU1c:** native Android Google sign-in with no stored secret, tested in check 2. Made 23 minutes after the plan was last saved, so the plan didn't get it until the 2026-10-12 review.
- **2026-10-07 · C5a / C5d:** scheduled notifications through our own Kotlin plugin (`extensions/weighInNotify`) instead of a third-party library or a fork of Flet's Android template.
- **2026-10-12 · F1.1:** if Google sign-in fails on the phone, fall back to an emailed 6-digit code. Drive backups stay on the phone either way.
- **2026-10-12 · F2.1:** the plan lives in the repo as `docs/plan.md` (it used to be only in `~/.claude/plans/`).
- **2026-10-12 · F10.1:** store only facts; cycle position, rest-step use, midnight auto-finish and suggestions are recalculated from them (no `cycleState` / `suggestions` tables), so the phone and the PC view can't disagree.
- **2026-10-12 · F11.1:** "newest edit wins" is enforced by a database trigger that ignores older incoming changes; edit times come only from the device.
- **2026-10-12 · F12.1:** plan import rejects a weeklyTarget only outside 1–7; a target faster than the cycle's pace just gets a warning.
- **2026-10-12 · F13.1:** backups get a restore script + guide, tested on a spare copy when built and after every data-structure change; each backup records its structure version.
- **2026-10-12 · F14.1:** automatic backups come from the phone only; the PC view gets a "Back up now" button.
- **2026-10-12 · F15.1:** keep the ping schedule alive through GitHub's "enable workflow" API instead of monthly bot commits (fallback: the commit).
- **2026-10-12 · F21.1 → F21.2:** the weekly reminder uses alarm-clock mode. OnePlus gave normal exact alarms a 1-hour window even with battery "Unrestricted"; alarm-clock alarms fire on the dot. Battery stays on "Unrestricted".
- **2026-10-12 · C2a:** check 2 keeps the Supabase session in the app's memory only; how tokens are stored on the phone is decided before check 4. The app gets the public identifiers (K2a) from a git-ignored config file generated from `.env` (`spikes/phase0/makePublicConfig.py`), so nothing new goes into the public repo.
- **2026-10-12 · P1.1:** the Google app stays in Testing with only your account as a test user until check 7, then gets published (Google requires a homepage + privacy policy page to publish). Sign-in works in Testing; Drive backups need publishing.
- **2026-10-12 · T1.1:** the sign-in session is stored on the phone encrypted with a non-exportable Android Keystore key (own small Kotlin extension), in the app's no-backup folder; a failed decryption means signing in again. The offline queue itself isn't encrypted (gym data isn't sensitive to you).
- **2026-10-12 · 6.1:** the PC view signs in with Google Identity Services in the browser (Google's recommended website sign-in; same nonce check as the phone, no secret). Rejected: emailed codes (6.2: Supabase's built-in email only reaches its own team, a custom mail server's password would sit on Supabase) and Google's older redirect sign-in (6.3: Google discourages it).
- **2026-10-12 · P6.1:** the PC view is published from a `gh-pages` branch. This relaxes C2a for the three public values (Supabase address, publishable key, Google client ID): they also sit in that branch's site files, exactly what the website serves to every visitor. No secret is involved; secret keys still never exist in the project.
- **2026-10-12 · D7.1:** check 7's Drive test runs while the Google app is still in Testing, because its 1-hour token expiry test doesn't depend on publishing. Publishing follows once you've approved the homepage and privacy page; it's still needed, because Drive access in Testing expires every 7 days. Replaces "publish before check 7" from P1.1.
- **2026-10-13 · SY1.1:** every synced row also gets `cloudUpdatedAt`, stamped by the cloud when it stores a change and used only to fetch what's new; the device's `updatedAt` still decides which edit wins. Without it, an edit that reaches the cloud late (made offline, e.g. by the diet app later) looks old, and another device would never fetch it. The exact fetch rules come with the sync design.
- **2026-10-13 · UP1.1:** cloud upgrades only add things; the cloud records the oldest app version allowed to sync, and an app stops syncing (changes stay queued) with a clear message when either side is too old; the cloud is upgraded before an app is released. This covers the time when the PC view already runs a new release and the phone still runs the old one. Also corrects G6a: cloud upgrades are run by you, not automatically, because they need admin access that no app or server may hold.
- **2026-10-13 · CS1.1:** code structure (section 3b): pure rules, all facts in memory, one write path, two stores behind one interface (sync on the phone only), declarative screens (checked on the phone in the first build stage), phone/PC chosen once in `main.py`, shared code as the local package `usefulShared`, plus the package guard (section 2) after finding that PyPI already has packages named `securestore` and `shared`.
- **2026-10-13 · DT1.1:** one workout per day; logging again the same day adds to it. Its ID is calculated from your user ID and the date, so the phone and the PC view can't create two.
- **2026-10-13 · DT2.1:** one body weight per day; entering it again replaces it (same ID method).
- **2026-10-13 · SY2.1:** data tables and sync as in sections 14 and 14b (technical design; you left the details to me). Six tables: the exercise list is now worked out from the plan imports (R8's `exercises` table dropped, same uses) and cardio sits in `exerciseLogs`. Each workout records its plan step. Fetching overlaps by 5 minutes; the cloud refuses changes stamped more than 5 minutes in the future. Sync runs at start, after changes, every minute and on return to the screen; a first download finishes before Today shows; backups sync first and include deleted rows.
- **2026-10-13 · UP2.1:** you paste cloud upgrades into Supabase's SQL editor, so no database password exists anywhere (rejected: a script on your PC using the database password from `.env`). The rest of section 14c is technical design (you left the details to me): one numbered list, guarded one-transaction scripts, data fill-ins in the cloud only, phone steps with a database copy to fall back on, and tests in a local Postgres container with a copy of your data that stays on the PC.
- **2026-10-14 · RL1.3:** the app is called "Gym Tracker"; Android package `io.github.fingaerwen.gymtracker`, separate from the Phase 0 spike.
- **2026-10-14 · RL2.1:** the daily ping gets the Supabase address and publishable key from GitHub Actions variables (not secrets, and not in the repo, so C2a holds). Rejected: a config file committed to the repo.
- **2026-10-14 · RL3:** release details (technical design; you left the details to me): arm64-only APK, versionCode = the middle version number, signing key made with `keytool` into a private folder with a random password that is never shown and a certificate name without personal details, the release script's checks before and after building, and the GitHub release created by you on the website (no GitHub token anywhere).
- **2026-10-14 · DG1.1:** a "Problems" page in the app with recent errors in plain words and a Copy button; nothing is sent anywhere automatically. Rejected: reading the phone's log over USB only. The log design in section 12d is technical (you left the details to me).
- **2026-10-14 · SY2.2:** your gym's internet drops for up to ~30 minutes, so offline sync tries every minute instead of backing off to 5 minutes, and each request gives up after 15 seconds; changes still waiting when you close the app go out the next time it's open.
- **2026-10-14 · SC1.1:** Today shows a small "N waiting" while changes wait to be sent. Rejected: nothing until the 3-day banner.
- **2026-10-14 · SC2.1:** the Today layout as drawn in section 6 (header with step, cycle place and week count; ⋮ menu with Problems and Sign out; Finish button; tabs at the bottom).
- **2026-10-14 · SC3.1:** tab split (Progress = exercises, PRs and charts; Week = summary, calendar, streak; Weight = weigh-in and chart) and the Progress layout as drawn in section 10; the app says "PR".
- **2026-10-14 · CA1.1:** daily step totals can be entered (one per day, any day), converted at 100 steps = 1 minute and added to the week's cardio; they never count as a workout. New shared table `dailySteps`. Rejected: steps only for gym cardio exercises.
- **2026-10-14 · SC4.1:** Week layout as drawn in section 10; steps are entered on Today ("Steps today" line) or by tapping a day in Week's calendar row; zero parts of the cardio line are left out.
- **2026-10-14 · SC5.1:** Weight layout as drawn in section 10, without the "same day, morning…" hint on the screen.
- **2026-10-14 · NT1.2:** the Friday notification says "Time to weigh in" (replaces 16.1a's text).
- **2026-10-14 · SC6.1:** PC screens (Plans, History, Backup) as drawn in section 10; first-launch flow on the phone written down there too.
- **2026-10-14 · LK1.1:** accent colour white in dark mode and black in light mode (a black-and-white look). Rejected: always dark mode with white (would change G1).
- **2026-10-14 · ST1.1:** staging: 0.1-alpha logs a workout, 0.2-alpha shows progress, 0.3-alpha adds the PC history editing and backups (section "Staging"). Building starts with 0.1-alpha.
- **2026-10-14 · KR1.2:** "Train anyway" keeps at most one rest owed: training through two Rest steps in a row owes one rest day, then the plan carries on. Rejected: every skipped rest stays owed (KR1.1), because rest days would pile up after a busy week.
- **2026-10-14 · PF1:** plan file checks and exercise matching as in section 4 and `plans/planFormat.md` (technical design; you left the details to me). A new plan takes effect today, or tomorrow if a workout is already logged today.
- **2026-10-14 · BLD1:** details settled while building 0.1-alpha (technical; you left them to me): Today's taps as in section 6, 0.1-alpha's PC view (Today and Plans), our package names with the `usefulTrash` prefix, release tags `gym-v<version>`, and the release key made with `tools/makeSigningKey.py` (password never shown).
- **2026-10-14 · KB1.1:** the release key's backup goes on the 500 GB NVMe drive. Rejected: the 1 TB drive (it holds the project, so one failure loses both), the NTFS partitions (they lose the owner-only permissions).
