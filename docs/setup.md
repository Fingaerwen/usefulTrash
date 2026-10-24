# Gym Tracker: one-time setup (plan 12b)

Done once, before the first release (0.1-alpha, published 2026-10-14). Nothing secret appears here: the fingerprints and
names below are public by design (anyone can read them from the APK).

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

### 1b. Cloud upgrade 002 (you, in Supabase; added 2026-10-23)
The same way: New query → paste the whole of
[`cloud/002_settingsAndDeloads.sql`](https://github.com/Fingaerwen/usefulTrash/blob/main/cloud/002_settingsAndDeloads.sql)
→ **Run**. The last line must read `upgrade 002 done`. It adds the tables for weights and weight steps you
set in the app and for deloads you start by hand (WD2.1, WD2.4). It only adds tables, and it refuses to run
twice or before 001.

### 1c. Back up now's page (you, in Google Cloud; added 2026-10-24)
Only for the PC view's **Back up now** (BK1.1); the phone's automatic backups don't need it.
Google Cloud console → **APIs & Services** → **Credentials** → the **Web** client (the one whose ID the app
uses) →
- **Authorized JavaScript origins:** add `https://fingaerwen.github.io` if it isn't there.
- **Authorized redirect URIs:** add `https://fingaerwen.github.io/usefulTrash/driveToken.html`.

→ **Save**. It can take a few minutes to apply. Nothing secret is involved: both addresses are public.

## 2. Two Android sign-in clients (you, in Google Cloud)
Google Play services only hands a sign-in token to an app whose package and signing key it knows.
Gym Tracker is a new package, so it needs its own clients, in the same project as the Web client.

[Google Auth Platform → Clients](https://console.developers.google.com/auth/clients) → **CREATE CLIENT**
→ Application type **Android**, twice:

| Client | Package name | SHA-1 certificate fingerprint |
|---|---|---|
| Gym Tracker (release key) | `io.github.fingaerwen.gymtracker` | `A8:08:97:5C:B8:29:C7:2F:A7:0A:7C:EB:C9:5E:99:04:05:3D:82:BF` |
| Gym Tracker (debug key, test builds) | `io.github.fingaerwen.gymtracker` | `57:92:1B:25:A7:0A:93:21:E8:2A:EA:45:A8:97:B3:3F:10:CC:29:D2` |

No client secret is involved (Android clients have none). The ownership check is optional; skip it.

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
(the key file and its password file, readable only by you; the password was never shown). Copy that
whole folder to your second drive (G3a). Without it, updates can't be installed over the app: you'd have
to uninstall, reinstall and sign in again (only changes not yet synced would be lost).

## 5. A release
0.1-alpha was published on 2026-10-14, before the weekly schedule and everything after it; 0.2-alpha on
2026-10-24 (RL4.1). 0.3-alpha needs no cloud upgrade.
1. Once the release's cloud upgrade is done (if it has one), I run `python3 tools/buildRelease.py --cloudReady`:
   every check, the signed APK, the tag, and the PC view published to GitHub Pages.
2. You create the release on GitHub from the link it prints: title `Gym Tracker <version>`, like
   `Gym Tracker 0.3-alpha`, **not** a pre-release (Obtainium skips those), and drag in the APK it names.
3. On the phone, Obtainium offers it as an update.

## 6. On the phone
1. **Obtainium** → **+** (Add App) → source URL `https://github.com/Fingaerwen/usefulTrash` → **Add**,
   then install Gym Tracker. Later releases come as updates in Obtainium.
2. Open it → **Sign in with Google** → it downloads your data → Today. From 0.3-alpha, the first time
   it opens after its first sync, Google asks once whether Gym Tracker may keep files in your Drive (the
   automatic backup, every 30 days): **Allow**.
3. No battery setting up front (BT1.1). Only if a reminder arrives late (the 08:00 creatine reminder, or the
   Friday 07:00 weigh-in from 0.3-alpha): Settings → Apps → Gym Tracker → Battery → **Unrestricted**.
4. The Phase 0 app was uninstalled on 2026-10-14 (PH1.1).

## 7. The check on your phone (0.2-alpha and 0.3-alpha)
What only the phone can show (Staging: each release is checked on your phone before the next one starts; 0.3-alpha
was built before 0.2-alpha's check, ST1.3, so this list covers both).
Anything that looks wrong: ⋮ → Problems → **Copy**, and paste it to me.
1. **Start:** ⋮ → Problems: the top line reads `Gym Tracker 0.3-alpha · schema 2 · started in … s`, under 5 s
   (check 8).
2. **Plan:** import it in the PC view's Plans tab (first `.venv/bin/python tools/checkPlan.py <file>` on the PC if
   you like). It takes effect today, or tomorrow if you've logged today.
3. **Today:** the header (`Upper · Monday · week 0/5`); [✓] an exercise and tap it again to take it back; ▾ sets
   with another weight; skip; tap a name for its how-to; ✎ weight; Finish (`Workout finished ✓ · … kg`); the steps
   line. On the first sessions your plan's 1 kg weights show as `? kg`: [✓] opens ▾ sets, where the weight typed in
   set 1 counts for the sets below (the target starts from there), or use ✎ weight before you start, which also
   fills the exercise's other days still at `? kg`. A 5- or 6-set exercise logged with uneven reps (your ab
   machine) still shows its name, the entry wraps if it must, and [✓] stays at the right edge (SC2.2).
4. **The gym's dead zone:** airplane mode → log a few → `N waiting` at the top → airplane mode off → it disappears
   within about a minute, and the PC view shows the entries a minute later.
5. **Progress:** each exercise with `now …` and its PR; open one: chart, PRs, `Now Mon …` with ✎, the history.
6. **Week:** the numbers, the calendar row (✓ trained, ✗ missed), ◂ ▸, and a day tapped to enter its steps.
7. **Deload by hand:** ⋮ → Start a deload → Today's deload line, half the sets and 3 reps fewer → ⋮ → Stop the
   deload (unless you want one).
8. **Creatine reminder:** Android asks once whether the app may send notifications (allow it); the next morning at
   08:00, "Creatine · Time for your creatine". An alarm icon in the status bar is expected (alarm-clock mode, so
   it's on time). If it comes late: battery → **Unrestricted** (section 6).
9. **Restart the phone and the app:** still signed in, everything still there, and the reminders still set.
10. **↑new and Undo (0.3-alpha):** after you've topped an exercise's range, its next target shows `↑new` with
    **undo ↑** under it; undo shows the last weight at the top of the range, with **redo ↑** to go back.
11. **Charts (0.3-alpha):** pick an exercise at the top; the kg line and the reps bars fit the screen in light and
    dark mode (the marks are drawn in the text colour); tap a chart and the session is written underneath.
12. **Weight (0.3-alpha):** Friday preselected, ◂ ▸ for another day, Save; the text bars and `Last 4: …` below.
13. **Banners (0.3-alpha):** on Friday "Weigh-in due" until you've weighed in, and at 07:00 the "Weigh-in · Time to
    weigh in" notification; on Monday "Last week's summary is ready", which opens last week on Week and is gone.
14. **The automatic backup (0.3-alpha):** after the update, Google asks once about Drive (allow it); then
    ⋮ → Problems shows `Last backup: … (phone) · today`, and Google Drive has the folder **Gym Tracker backups**
    with one zip in it.
15. **History (0.3-alpha):** ⋮ → History → Days: the last 7 days; Edit one, ✓ an exercise there, and Today
    stays as it was; Delete this workout; then Months: your month per exercise, and a tap shows its chart.
16. **The PC view (0.3-alpha):** the History tab (any day), the Backup tab: Export CSV downloads a zip; after
    step 1c, Back up now opens Google's page in a second window, and then says "Backed up to your Google
    Drive: …". If it doesn't, ⋮ → Problems → Copy, and paste it to me.
