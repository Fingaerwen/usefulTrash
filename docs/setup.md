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
1. Once step 1 is done, I run `python3 tools/buildRelease.py --cloudReady`: every check, the signed APK,
   the tag, and the PC view published to GitHub Pages.
2. You create the release on GitHub from the link it prints: title `Gym Tracker 0.1-alpha`,
   **not** a pre-release (Obtainium skips those), and drag in the APK it names.

## 6. On the phone
1. **Obtainium** → **+** (Add App) → source URL `https://github.com/Fingaerwen/usefulTrash` → **Add**,
   then install Gym Tracker.
2. Open it → **Sign in with Google** → it downloads your data → Today.
3. Battery setting **Unrestricted** (Settings → Apps → Gym Tracker → Battery), for the Friday
   notification that comes with 0.2-alpha.
4. Once Gym Tracker works, uninstall the Phase 0 app.
