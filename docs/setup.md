# Talon and Ambrosia: one-time setup (plan 12b, apps/diet/docs/plan.md 4h)

Done once per app, before its first release: Gym Tracker's (now Talon, AM1.4) before 0.1-alpha (published 2026-10-14),
Ambrosia's before 0.1-alpha at the joint release with Talon 0.4-alpha (sections 1d, 2b, 6b and 8). Nothing secret
appears here: the fingerprints and names below are public by design (anyone can read them from the APK).

## 1. Cloud upgrade 001 (you, in Supabase)
1. Open [your Supabase projects](https://supabase.com/dashboard/projects) → the project → **SQL Editor**
   (left sidebar) → **New query**.
2. Run `select version();`. It must say **PostgreSQL 17**, the version the cloud tests use. If it
   doesn't, stop and tell me.
3. New query → paste the whole of
   [`cloud/001_baseTables.sql`](https://github.com/Fingaerwen/usefulTrash/blob/main/cloud/001_baseTables.sql)
   (GitHub's **Copy raw file** button copies it) → **Run**.
4. The last line must read `upgrade 001 done`. A failure changes nothing, and running it twice is refused.

This removes the Phase 0 test table, so the Phase 0 app's note checks stop working (it gets
uninstalled once Gym Tracker works).

### 1b. Cloud upgrade 002 (you, in Supabase, added 2026-10-23)
The same way: New query → paste the whole of
[`cloud/002_settingsAndDeloads.sql`](https://github.com/Fingaerwen/usefulTrash/blob/main/cloud/002_settingsAndDeloads.sql)
→ **Run**. The last line must read `upgrade 002 done`. It adds the tables for weights and weight steps you
set in the app and for deloads you start by hand (WD2.1, WD2.4). It only adds tables, and it refuses to run
twice or before 001.

### 1c. Back up now's page (you, in Google Cloud, added 2026-10-24)
Only for the PC view's **Back up now** (BK1.1). The phone's automatic backups don't need it.
Google Cloud console → **APIs & Services** → **Credentials** → the **Web** client (the one whose ID the app
uses) →
- **Authorized JavaScript origins:** add `https://fingaerwen.github.io` if it isn't there.
- **Authorized redirect URIs:** add `https://fingaerwen.github.io/usefulTrash/driveToken.html`.

→ **Save**. It can take a few minutes to apply. Nothing secret is involved: both addresses are public.

### 1d. Cloud upgrade 003 (you, in Supabase, at the joint release)
For Talon 0.4-alpha and Ambrosia 0.1-alpha. In the release order (plan 14c): your phone has synced (nothing
waiting), a fresh backup exists, then New query → paste the whole of
[`cloud/003_ambrosiaAndWeighInTime.sql`](https://github.com/Fingaerwen/usefulTrash/blob/main/cloud/003_ambrosiaAndWeighInTime.sql)
→ **Run**. The last line must read `upgrade 003 done`. It adds Ambrosia's tables and the time of today's weigh-in.
It only adds, refuses to run twice or before 002, and Talon 0.3 keeps syncing after it.

## 2. Two Android sign-in clients (you, in Google Cloud)
Google Play services only hands a sign-in token to an app whose package and signing key it knows.
Gym Tracker is a new package, so it needs its own clients, in the same project as the Web client.

[Google Auth Platform → Clients](https://console.developers.google.com/auth/clients) → **CREATE CLIENT**
→ Application type **Android**, twice:

| Client | Package name | SHA-1 certificate fingerprint |
|---|---|---|
| Gym Tracker (release key) | `io.github.fingaerwen.gymtracker` | `A8:08:97:5C:B8:29:C7:2F:A7:0A:7C:EB:C9:5E:99:04:05:3D:82:BF` |
| Gym Tracker (debug key, test builds) | `io.github.fingaerwen.gymtracker` | `57:92:1B:25:A7:0A:93:21:E8:2A:EA:45:A8:97:B3:3F:10:CC:29:D2` |

No client secret is involved (Android clients have none). The ownership check is optional. Skip it.

### 2b. Ambrosia's two Android sign-in clients (you, in Google Cloud, before the joint release)
The same way, twice, for Ambrosia's package. One release key signs both apps, so the fingerprints are the same:

| Client | Package name | SHA-1 certificate fingerprint |
|---|---|---|
| Ambrosia (release key) | `io.github.fingaerwen.ambrosia` | `A8:08:97:5C:B8:29:C7:2F:A7:0A:7C:EB:C9:5E:99:04:05:3D:82:BF` |
| Ambrosia (debug key, test builds) | `io.github.fingaerwen.ambrosia` | `57:92:1B:25:A7:0A:93:21:E8:2A:EA:45:A8:97:B3:3F:10:CC:29:D2` |

Without them, sign-in and the Drive backups fail on the phone. The PC view doesn't need them.

## 3. The daily ping's two variables (you, on GitHub)
1. [Settings → Secrets and variables → Actions → Variables](https://github.com/Fingaerwen/usefulTrash/settings/variables/actions)
   → **New repository variable**, twice, with the same values as in your `.env`:
   - `SUPABASE_URL`
   - `SUPABASE_PUBLISHABLE_KEY` (the publishable one, never the secret one)
2. [The dailyPing workflow](https://github.com/Fingaerwen/usefulTrash/actions/workflows/dailyPing.yml)
   → **Run workflow**. Both steps should be green: `ping: ok` and `keep-alive: 204`.

They're variables, not secrets (RL2.1): both values are public by design and already sit in the PC
view's website files. GitHub shows a step's variables in its log for the same reason.

## 4. The release key's backup (you, once)
The release key was made with `tools/makeSigningKey.py` into `~/.local/share/usefulTrash/signing`
(the key file and its password file, readable only by you, the password was never shown). Copy that
whole folder to your second drive (G3a). Without it, updates can't be installed over the app: you'd have
to uninstall, reinstall and sign in again (only changes not yet synced would be lost).

## 5. A release
0.1-alpha was published on 2026-10-14, before the weekly schedule and everything after it. 0.2-alpha on
2026-10-24 (RL4.1). 0.3-alpha needs no cloud upgrade. Talon 0.4-alpha and Ambrosia 0.1-alpha come out together
and need cloud upgrade 003 (section 1d).
1. Once the release's cloud upgrade is done (if it has one), I run `python3 tools/buildRelease.py talon` (or
   `ambrosia`, or `talon ambrosia` for both at once) with `--cloudReady`: every check, the signed APKs, the tags,
   and the site published to GitHub Pages: the start page at `https://fingaerwen.github.io/usefulTrash/` with both
   PC views, `talon/` and `ambrosia/`. An app that isn't in the release keeps the PC view it has there.
2. You create each release on GitHub from the link it prints: title `Talon <version>` or `Ambrosia <version>`,
   like `Talon 0.4-alpha`, **not** a pre-release (Obtainium skips those), and drag in the APK it names.
3. On the phone, Obtainium offers it as an update (Talon). Ambrosia's first gets its entry then (section 6b, step 2).

## 6. On the phone
1. **Obtainium** → **+** (Add App) → source URL `https://github.com/Fingaerwen/usefulTrash` → **Add**,
   then install Gym Tracker. Later releases come as updates in Obtainium.
2. Open it → **Sign in with Google** → it downloads your data → Today. From 0.3-alpha, the first time
   it opens after its first sync, Google asks once whether Gym Tracker may keep files in your Drive (the
   automatic backup, every 30 days): **Allow**.
3. No battery setting up front (BT1.1). Only if a reminder arrives late (the 08:00 creatine reminder, or the
   Friday 07:00 weigh-in from 0.3-alpha): Settings → Apps → Gym Tracker → Battery → **Unrestricted**.
4. The Phase 0 app was uninstalled on 2026-10-14 (PH1.1).

### 6b. Two apps from one repo in Obtainium (one step before the joint release, one on release day)
Both apps' releases come from the same repo, so each Obtainium entry needs a filter, or it would take the other app's
release as its own newest one:
1. The existing entry (Gym Tracker, Talon from 0.4-alpha) → the pencil (Additional options) → **Filter release
   titles by regex**: `^(Talon|Gym Tracker)` → back, it saves by itself. Both names, so it still knows its current
   release before Talon's is out. **Done 2026-10-28**, it still shows 0.3-alpha as installed and latest.
2. **On release day, once Ambrosia's release is out** (before that Obtainium refuses with "Could not find a suitable
   release"): **+ Add** → the same source URL `https://github.com/Fingaerwen/usefulTrash` → **Filter release titles
   by regex**: `^Ambrosia` → further down, switch off **Try inferring app ID from source code** (the repo holds two
   apps, so it could guess Talon's) → the **+** beside the URL, then install Ambrosia.

Leave **Fallback to older releases** on in both, it's the default. With it an entry skips the other app's release
when that one is GitHub's newest.

## 7. The check on your phone (0.2-alpha and 0.3-alpha)
What only the phone can show (Staging: each release is checked on your phone before the next one starts, 0.3-alpha
was built before 0.2-alpha's check, ST1.3, so this list covers both).
Anything that looks wrong: ⋮ → Problems → **Copy**, and paste it to me.
1. **Start:** ⋮ → Problems: the top line reads `Gym Tracker 0.3-alpha · schema 2 · started in … s`, under 5 s
   (check 8).
2. **Plan:** import it in the PC view's Plans tab (first `.venv/bin/python tools/checkPlan.py <file>` on the PC if
   you like). It takes effect today, or tomorrow if you've logged today.
3. **Today:** the header (`Upper`, and under it `Monday · 0 of 5 this week`) and the progress card (`0 of 10
   done`). Tick an exercise with the big circle and tap it again to take it back. **Sets** with another weight.
   In ⋯: Skip, How to (or tap the name), Set the weight. Finish (`Workout finished · … kg`). The steps card. On the
   first sessions your plan's 1 kg weights show as `? kg`: the tick opens Sets, where the weight typed in set 1
   counts for the sets below (the target starts from there), or use Set the weight before you start, which also
   fills the exercise's other days still at `? kg`. A 5- or 6-set exercise logged with uneven reps (your ab
   machine) wraps under its name, and the tick stays at the right edge.
4. **The gym's dead zone:** airplane mode → log a few → `N waiting` at the top → airplane mode off → it disappears
   within about a minute, and the PC view shows the entries a minute later.
5. **Progress:** each exercise with `now …` and its PR. Open one: the chart, the three PR tiles, `NEXT TIME`
   with the pencil, the history.
6. **Week:** the tiles, the days (a filled circle with a tick: trained, a cross: missed, a dot: rest), ‹ ›, and
   a day tapped to enter its steps.
7. **Deload by hand:** ⋮ → Start a deload → Today's deload card, half the sets and 3 reps fewer → ⋮ → Stop the
   deload (unless you want one).
8. **Creatine reminder:** Android asks once whether the app may send notifications (allow it). The next morning at
   08:00, "Creatine · Time for your creatine". An alarm icon in the status bar is expected (alarm-clock mode, so
   it's on time). If it comes late: battery → **Unrestricted** (section 6).
9. **Restart the phone and the app:** still signed in, everything still there, and the reminders still set.
10. **"new" and Not today (0.3-alpha):** after you've topped an exercise's range, its next target is marked
    `new`. Tap the mark (or ⋯ → Not today) and the last weight at the top of the range shows, marked `not today`.
    Tap it again (or ⋯ → Take the step up) to go back.
11. **Charts (0.3-alpha):** pick an exercise at the top. The kg line and the reps bars fit the screen in light and
    dark mode, with the latest session written underneath. Tap the chart and another one is.
12. **Weight (0.3-alpha):** Friday preselected, ‹ › for another day, Save. The chart and `LAST 4` below.
13. **Banners (0.3-alpha):** on Friday "Weigh-in due" until you've weighed in, and at 07:00 the "Weigh-in · Time to
    weigh in" notification. On Monday "Last week's summary is ready", which opens last week on Week and is gone.
14. **The automatic backup (0.3-alpha):** after the update, Google asks once about Drive (allow it). Then
    ⋮ → Problems shows `Last backup: … (phone) · today`, and Google Drive has the folder **Gym Tracker backups**
    with a dated backup and `GymTracker-history.zip` in it.
15. **History (0.3-alpha):** ⋮ → History → Days: every day this month since your plan began, ‹ for earlier ones.
    Open one of the last 7 (a pencil), tick an exercise there, and Today stays as it was. An older day opens
    read-only. Delete this workout. Months: your month per exercise, and a tap shows its chart. All time: every exercise's
    chart with its PRs, and your weight's.
16. **The PC view (0.3-alpha):** the History tab (any day), the Backup tab: Export CSV downloads a zip. After
    step 1c, Back up now opens Google's page in a second window, and then says "Backed up to your Google
    Drive: …". If it doesn't, ⋮ → Problems → Copy, and paste it to me.
17. **The look (0.3-alpha):** black with charcoal cards in dark mode, the mirror (white, light grey) in light mode.
    Nothing cut off or overlapping on Today, Progress, an exercise's page, Charts, Week, Weight and History. The PC
    view has its tabs down the left and its screens in the middle. A grey box instead of a screen: ⋮ → Problems →
    Copy, and paste it to me.
18. **The rest timer (0.3-alpha):** tick an exercise: the timer at the bottom of Today counts down its rest. +30 s
    adds, × stops it. Tapping an exercise's rest time (the stopwatch) starts it between sets. Lock the phone
    during one: at 0 a "Rest over" notification pops up, on time (an alarm icon in the status bar meanwhile is
    expected). It can be muted on its own: Android settings → Apps → Gym Tracker → Notifications → Rest timer.

## 8. The joint release, in order, and its check on your phone (Talon 0.4-alpha, Ambrosia 0.1-alpha)
**Before it (you):** section 2b (6b's first step is done). On release day: Talon on the phone has synced (nothing waiting), a fresh
backup exists (the PC view's Back up now), then cloud upgrade 003 (section 1d). Then I run
`python3 tools/buildRelease.py talon ambrosia --cloudReady` and you make the two GitHub releases (section 5).

**Then on the phone and the PC.** Anything that looks wrong: ⋮ → Problems → **Copy**, and paste it to me.
1. **The update:** Obtainium updates Gym Tracker to **Talon** over the old one: same data, signed in, the new red
   look. ⋮ → Problems: `Talon 0.4-alpha · schema 3 · started in … s`, under 5 s.
2. **The weigh-in time:** save today's weigh-in on the Weight tab: `weighed at 07:12` under the day, at your
   phone's clock, and the time under it in LAST 4. A past day's has none.
3. **Talon's backup** (at its next one, within 30 days): Google Drive's folder **Gym Tracker backups** is now
   **Talon backups**, with `Talon-history.zip` in it and the old dated backups still there until they rotate out.
4. **Ambrosia:** add its Obtainium entry (section 6b, step 2) and install it → Sign in with Google (the same account) → it downloads your
   data → Today. ⋮ → Problems: `Ambrosia 0.1-alpha · schema 3 · started in … s`, under 5 s.
5. **Scanning:** + on a meal → Scan: Android asks once for the camera. Scan about 10 of your usual groceries. A
   shop's own code goes straight to typing the label, a missing one too. Search a few generic foods. Note how many of
   your groceries Open Food Facts had (Phase 0's open item, `apps/diet/docs/phase0.md`).
6. **Targets:** import your targets file (from your Claude project, written with the new brief) on the PC view's
   Targets tab: it shows the targets for training and rest days, and the bulk check's first block.
7. **The dead zone:** airplane mode → log a food and water → `2 waiting` beside today's date → airplane mode off → gone
   within a minute, and the PC view shows them a minute later.
8. **Ambrosia's backup:** after the first sync Google asks once about Drive (allow it). ⋮ → Problems shows
   `Last backup: … (phone) · today`, and Google Drive has the folder **Ambrosia backups**.
9. **The look:** scroll Today and Week with the blurred see-through cards. If scrolling stutters, say so: the blur
   goes and the see-through stays (AM9.1).
10. **The site:** `https://fingaerwen.github.io/usefulTrash/` is the start page with both apps, and each opens its
    PC view (sign in again in each tab).
11. **The bulk check** (from Sunday 6 Dec, the first big-miss check): on a check Sunday with a suggestion, its card
    sits on Today with Apply and Not now. Apply right after a sync adds the change to both kinds of day, and Targets
    shows it with Undo.
