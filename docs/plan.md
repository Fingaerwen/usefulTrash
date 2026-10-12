# usefulTrash: Gym App Plan

## Context
This is a personal suite of Python apps in one public repo (`claudProjects/usefulTrash/`). The first app is an Android **gym tracker**; a **diet app** comes later and will share the same cloud database and login. Every decision below was made with you point by point, including the resolution of the "brutal review" flaws. **Approving this plan starts Phase 0 only (the feasibility check).** The staging after that is decided from Phase 0's results (14.1).

---

## 1. Platform & stack
- Android only, single user (you). Python + **Flet 1.0.x** (pinned version).
- **Cloud:** Supabase free tier (Postgres + login).
- **Phone:** local SQLite, offline-first. **Sync runs while the app is open** (2); gym dead-zones are covered by a sync queue.
- **PC view:** the same Flet app built as a static site on **GitHub Pages** (1). The PC view is online-only (no local queue). **Koyeb is dropped** (R1a), because it would hold your sign-in on a server.
- **If GitHub Pages fails Phase 0:** there's no PC view. The phone gets the PC-only features in a "More" menu (history editing for any day, CSV export, plan management, the backup warning). The 7-day edit limit lifts only in this fallback (R1d / R1d-1).
- **Dev Python is pinned to the Python version Flet bundles for Android** (R3).
- **One venv for the whole repo** (V2a), git-ignored. The PC runs **Bazzite** (immutable, so no system package installs). The tool is decided after Phase 0 (V1e): if Flet's Android Python is 3.14 → a plain `python3 -m venv`; otherwise → **uv** installed in your home folder, which provides the matching Python. Requirements are pinned in one file.

## 2. Security & privacy
- **Key rule (absolute):** secrets are **never written into any text** (chat, docs, code, commits, logs) and **never uploaded to any server or cloud**, GitHub Secrets included. Only key *names* are ever mentioned (K4c).
  - **Secrets (local only):** the Supabase secret/admin key, database passwords, Google Drive passes, the APK signing key, `.env`.
  - **Allowed public identifiers (K2a):** the Supabase address, the Supabase *publishable* key and the Google sign-in client ID. They ship inside the app and website; they're public by design and unlock nothing on their own.
  - Sign-in tokens go to Google/Supabase as part of logging in and are stored only on your device (K3a).
  - GitHub's own temporary job token (created by GitHub, never seen or stored) is allowed for the keep-alive commit (3.3a).
- **Leak protection:** a pre-commit secret scan blocks commits containing keys (K4a); GitHub push protection (K4b); `.env` and the signing key are in `.gitignore`.
- **Google sign-in**, **only your Google email allowed** (5.1), **sign-ups disabled after setup** (5.2). The Google app is set to *published* so sign-in passes don't expire after 7 days.
- Row-level security on every table.
- Commits use the **GitHub noreply email + your GitHub username** (6.1). Git currently has no identity set, and `gh` isn't installed.
- No home server and no exposed IP; no name or personal details collected.

## 3. Repo, code style, docs
- **Public GitHub repo, no license** (view-only). Secrets live in an untracked `.env`, never committed (the docs included).
- Layout:
  ```
  usefulTrash/
    apps/gym/   apps/diet/ (later)   shared/ (auth, sync, schema)
    plans/ (JSON spec + examples)    docs/   tests/   .github/workflows/
  ```
- **camelCase literally everywhere** (11.4c): Python names, JSON, exercise IDs, database columns. Hand-written Postgres SQL quotes identifiers (`"weightKg"`). Flet's own snake_case APIs stay as they are.
- **Comments in all code:** a short description of what each part does.
- **Full documentation write-up** in `docs/` when the project is done, updated whenever anything relevant changes or is added.

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
- A short format spec goes in `plans/` for you to paste into your Claude project.

## 5. Cycle & rest
- A **rotating cycle**; a missed day never shifts dates, the next step just waits.
- **Strict about extra rest:** an unplanned rest day does not use up a planned Rest step (13.3).
- **Train anyway** on a planned Rest step: the next workout is done and the rest step is kept for later (19.1c-2 / 13.1a).
- **A planned Rest step is used up when the day ends** with it as the current step and no workout logged, even if the app was never opened (R4a).

## 6. Today screen (19.1)
```
Push · cycle day 1/5 · this week 2/4 sessions
Bench Press   4×9 @ 82.5 kg ↑new  [✓]   rest 2:00 · "pause at bottom"  ▾ sets · skip
```
- **[✓]** logs it as targeted. **▾ sets** opens per-set rows pre-filled with the target (19.1a-1). **skip** = today only.
- **Finish workout:** anything untouched is **auto-skipped** (19.1b-1) and the cycle advances. **Forgot to finish → it auto-finishes at midnight** the same way (R5a).
- Past days can be edited on the **phone for the last 7 days** (19.1f-1) and on the **PC for any day**. Edits recalculate suggestions, streaks and summaries.

## 7. Progression
- **One rep target for all sets** (8.1). A new exercise starts at `repsMin` (12.1).
- All sets hit the target → next target = **lowest set + 1** (R6a). All sets at `repsMax` or above → **+increment kg**, and reps reset to `repsMin`.
- **Miss** = 2 or more sets under `repsMin` (a 1-set exercise: that set) (8.14a). **2 missed sessions in a row** → drop to the **last lower weight that worked**, with the **reps you last achieved there** as the target (R7b). If there is none → no suggestion (8.10 / 8.15 / 8.16d).
- **After a drop, you must hit the top of the range 2 sessions in a row** before the app suggests going heavier again, which prevents yo-yoing (R7c-1).
- **Skipped exercises are ignored** by progression (19.1e-1).
- Suggestions are **pre-filled** and tagged `↑new`, with Undo; logging one counts as accepting it (8.3).
- **Bodyweight exercises:** reps keep rising past the range, with no weight suggestions (10.9a).

## 8. Progress & stats
- **PRs:** heaviest weight; estimated 1RM (Epley, **only from sets of 10 reps or fewer**) (16.2a); most reps at the **current weight only** (16.3a). Bodyweight exercises: most reps in one set (10.10a).
- **Volume** (sets×reps×kg): per exercise, per workout, per week, vs last week. **Dumbbells are doubled in the combined totals only; one dumbbell is displayed everywhere** (10.4). Bodyweight exercises: total reps, kept separate (10.2).
- **Consistency:** a weekly session target (4.1), streaks = weeks in a row hitting it, exercise completion %. Calendar: trained / rest / **missed = 3rd+ unplanned rest day in a row** (4.5 / 4.7a / 4.9a). Missed days are display-only; **the weekly target wins** for streaks (4.8a).
- Weeks run Monday–Sunday. Dates are plain calendar dates (16.4c).

## 9. Weekly summary & weight
- **Summary:** completion, volume vs last week, PRs hit, weight change. Nutrition is added when the diet app exists (15.1).
- **Summary also shows** total cardio minutes for the week (G9.4a). Cardio counts toward completion %.
- **Weight:** a weekly weigh-in in the gym app plus a trend chart. The reminder is **Friday 07:00** (G9.1), with the text "same day, morning, after toilet, before food" (16.1a).
- **Past exercises** (not in the current plan) appear in Progress under "Past exercises", with full history (G10a).
- **"Not synced" banner** appears after 3 days of unsynced changes (G9.2b).

## 10. Screens
- **Phone tabs:** Today · Progress · Week · Weight (18.1 + 18.3c). The app opens on the **last tab used** (18.2c).
- **Banners at the top of any tab** (18.4a): weekly summary ready, not synced, weigh-in due.
- **PC:** the same tabs + Plans (import/switch/archive) + History (edit any day) + Export CSV + backup status.

## 11. Notifications & background
- Sync and banners are in-app only (2).
- The weekly weigh-in **phone notification is tested in Phase 0**; if Flet can't schedule it, it's an in-app prompt instead.

## 12. Backups & scheduled jobs (no stored secrets anywhere)
- **If Phase 0 shows that automatic Drive renewal needs a secret inside the app:** the backup moves to a **local timer on your Linux PC** instead, with its secrets in a local file only (R2b).
- **Automatic backup, triggered on the phone (main) and in the PC view (second):** when the app opens and the last backup is 30+ days old, it creates **zipped CSV files** (one per table, G9.3b) and uploads them to Google Drive with *your own sign-in*. The permission is limited to files the app created. **Keep the last 3.** A backup record prevents duplicate backups.
- The PC view **warns when the last backup is 60+ days old** (3.4).
- **Daily database ping (GitHub Actions):** uses only the public address + publishable key, calling a harmless `ping` function (K1c / 7.4), so the Supabase free tier doesn't pause. The publishable key lives in one config file that everything references. Whether the ping counts as activity is **watched for the first 2 weeks** (R10).
- **Monthly keep-alive commit** using GitHub's temporary job token, so GitHub doesn't disable the ping schedule (3.3a).

## 12b. Releases, updates & data upgrades
- **Versions:** `0.1-alpha` → `0.2-alpha` → … (the middle number bumps every release, with no third number) (V3a). If Android's tooling requires three numbers, it's stored internally as `0.1.0` while every visible name stays `0.1-alpha` (checked in Phase 0). The Phase 0 spike has no version. GitHub releases are **normal releases named alpha**, not pre-releases, so Obtainium picks them up (V4b).
- **Releases:** built and **signed on your PC**, then uploaded to GitHub Releases (G4c-1). The APK contains only the allowed public identifiers. The phone gets updates automatically through **Obtainium** (G4c).
- **Signing key:** stays on your PC, with a copy on a **second drive** (G3a). If it's ever lost: uninstall, reinstall, sign in again; only unsynced data is lost.
- **Data-structure changes:** numbered upgrade scripts run automatically on the phone and the cloud, tested first on a local copy of your data (G6a).
- **Plan import:** the PC view is the normal path. **Phone file import is a fallback only** when the PC view is unavailable (G2b-2). If GitHub Pages fails, the PC features move to the phone (R1d); Koyeb is dropped (R1a).
- **Invalid plans are rejected**, listing every error in plain words (G8a). Checks include missing fields, repsMin > repsMax, duplicate IDs, and weeklyTarget > training days in the cycle.

## 12c. Look & feel (G1)
Dark mode that follows the phone setting, minimal screens and taps, medium-sized tap targets.

## 13. Diet app (later)
- Same Supabase project, login and naming. For now the gym app only **shares weight + training days**. Nutrition tables and goals are designed when the diet app is planned (15.1).

## 14. Data model (draft, camelCase)
`exercises` (stable `exerciseId`, current name, past names, equipment; feeds 11.3 matching and "Past exercises") (R8), `plans`, `cycleState`, `sessions`, `exerciseLogs` (planned vs actual, per-set rows, skipped), `suggestions`, `cardioLogs`, `bodyWeight`, `backups`. Every row has `id` (UUID), `userId`, `updatedAt` (the time the edit was made on the device) and `deleted`. Conflicting edits: **the newest edit time wins** (G7a), so a late-arriving offline edit can't overwrite a newer one.

---

## Phase 0: feasibility check (what approval starts)
A throwaway Flet app in `usefulTrash/spikes/phase0/` that answers each question with pass/fail:
1. Builds as an APK and installs on your phone.
2. Google sign-in works on Android and is restricted to your email.
3. Reads/writes a camelCase-column row in Supabase with RLS on.
4. Works offline: writes are queued and synced once the connection is back.
5. A scheduled local notification fires (weigh-in reminder, Friday 07:00).
6. A `flet build web` version on GitHub Pages can sign in and read the same row.
7. The phone uploads a small file to Google Drive using your sign-in, **with no secret in the app, and still works after the 1-hour token expiry** (R2). Fail → PC timer backup (R2b).
8. **Cold start under 5 seconds** on your phone (G5b).
9. A JSON file can be picked from phone storage (fallback import).
10. A pre-commit secret scan blocks a commit containing a fake key.
11. Records the Python version Flet bundles for Android, which decides the venv tool (V1e / R3). This runs first, in a temporary venv.

12. Builds with the version name `0.1-alpha` and confirms whether Android needs a three-number internal version.

**Your account steps** (guided, done by you): a GitHub account/repo, a Supabase project, Google sign-in setup in Google Cloud (published app, Drive "files this app created" permission), and Obtainium on your phone.

Before Phase 0: check free disk space for Flutter + Android SDK + Java (several GB) (R11).

Setup during Phase 0: create `usefulTrash/` with git (noreply email, username), the GitHub repo and the Supabase project (you'll do the account steps), and **delete the old `claudProjects/gymtracker/` demo**. Results are written up in `docs/phase0.md`, then we decide the staging together.

## Verification
- Phase 0: each of the 12 checks recorded as pass/fail with notes. **If Google sign-in on Android fails (check 2), there's no decided fallback, so we replan.** Any fail → we revisit that decision before building.
- Later phases: automated tests for plan import/validation, cycle + rest rules, progression rules, PR/volume/streak math and sync (offline → online, conflicts). End to end: airplane mode → log → reconnect → shows in the PC view.
