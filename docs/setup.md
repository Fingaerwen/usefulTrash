# Gym Tracker: one-time setup (plan 12b)

Done once, before the first release (0.1-alpha). Nothing secret appears here: the fingerprints and
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

## 5. The first release
1. Once steps 1 and 1b are done, I run `python3 tools/buildRelease.py --cloudReady`: every check, the signed APK,
   the tag, and the PC view published to GitHub Pages.
2. You create the release on GitHub from the link it prints: title `Gym Tracker 0.1-alpha`,
   **not** a pre-release (Obtainium skips those), and drag in the APK it names.

## 6. On the phone
1. **Obtainium** → **+** (Add App) → source URL `https://github.com/Fingaerwen/usefulTrash` → **Add**,
   then install Gym Tracker.
2. Open it → **Sign in with Google** → it downloads your data → Today.
3. No battery setting for 0.1-alpha: it does nothing in the background (BT1.1). Only if 0.2-alpha's
   Friday notification arrives late: Settings → Apps → Gym Tracker → Battery → **Unrestricted**.
4. The Phase 0 app was uninstalled on 2026-10-14 (PH1.1).

## 7. The check on your phone (0.1-alpha)
What only the phone can show (Staging: each release is checked on your phone before the next one starts).
Anything that looks wrong: ⋮ → Problems → **Copy**, and paste it to me.
1. **Start:** ⋮ → Problems: the top line reads `Gym Tracker 0.1-alpha · schema 2 · started in … s`, under 5 s
   (check 8).
2. **Plan:** import it in the PC view's Plans tab (first `.venv/bin/python tools/checkPlan.py <file>` on the PC if
   you like). It takes effect today, or tomorrow if you've logged today.
3. **Today:** the header (`Upper · Monday · week 0/5`); [✓] an exercise and tap it again to take it back; ▾ sets
   with another weight; skip; tap a name for its how-to; ✎ weight; Finish (`Workout finished ✓ · … kg`); the steps
   line. On the first sessions your plan's 1 kg weights show as `? kg`: [✓] opens ▾ sets, where the weight typed in
   set 1 counts for the sets below (the target starts from there), or use ✎ weight before you start, which also
   fills the exercise's other days still at `? kg`.
4. **The gym's dead zone:** airplane mode → log a few → `N waiting` at the top → airplane mode off → it disappears
   within about a minute, and the PC view shows the entries a minute later.
5. **Progress:** each exercise with `now …` and its PR; open one: chart, PRs, `Now Mon …` with ✎, the history.
6. **Week:** the numbers, the calendar row (✓ trained, ✗ missed), ◂ ▸, and a day tapped to enter its steps.
7. **Deload by hand:** ⋮ → Start a deload → Today's deload line, half the sets and 3 reps fewer → ⋮ → Stop the
   deload (unless you want one).
8. **Creatine reminder:** Android asks once whether the app may send notifications (allow it); the next morning at
   08:00, "Creatine · Time for your creatine". An alarm icon in the status bar is expected (alarm-clock mode, so
   it's on time). If it comes late: battery → **Unrestricted** (section 6).
9. **Restart the phone and the app:** still signed in, everything still there, and the reminder still set.
