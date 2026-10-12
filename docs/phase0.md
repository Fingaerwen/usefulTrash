# Phase 0 – feasibility check results

Throwaway spike app: `spikes/phase0/`. Test phone: OnePlus Nord 4 (Android, arm64). PC: Bazzite, Python 3.14.7.
Status legend: ✅ pass · ❌ fail · ⏳ not tested yet · 🟡 partly tested

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1 | APK builds and installs on the phone | ✅ | Needed a workaround for a Flet 1.0.3 template bug (Dart `jni` pinned to 1.0.0, override to 1.1.0 in `spikes/phase0/pyproject.toml`). APK is 140 MB (all CPU types); per-type builds later. |
| 2 | Google sign-in on Android, no stored secret | ⏳ | Riskiest check. AU1c: native Android sign-in, no stored secret. Fallback if it fails: emailed code (F1.1, see `docs/plan.md`). |
| 3 | Supabase read/write, camelCase columns, RLS | 🟡 | Table `phase0Notes` created (`spikes/phase0/sql/001_phase0Notes.sql`). Anonymous access is refused outright (stricter than RLS alone). Signed-in read/write still to test. |
| 4 | Offline writes queued, synced when back online | ⏳ | Needs a Supabase sign-in first (any method: Google or the emailed-code fallback). |
| 5 | Scheduled local notification (Friday 07:00 weigh-in) | ✅ | Own Flet extension `extensions/weighInNotify` (Python → Dart → Kotlin, Android AlarmManager); third-party `flet-local-notifications` rejected (unknown author, no source, old Flet 0.28.3). On the phone: permission request, show-now, 60 s alarm with the app closed, and setting the weekly Friday 07:00 reminder all worked. The real weekly reminder also fired on Friday 2026-10-09 at 07:00. |
| 6 | PC view on GitHub Pages signs in and reads data | ⏳ | |
| 7 | Phone uploads to Google Drive without a stored secret | ⏳ | Doesn't depend on check 2: the phone's Drive permission comes from Google Play services, separate from the Supabase sign-in (F3). Fallback: PC timer backup (R2b). |
| 8 | Cold start under 5 s | ✅ | 3 runs, tap → screen fully drawn: 3.3 s (first), 2.8 s, 2.8 s, including ~0.5–1 s measuring overhead. Python start → screen: 0.24 s. |
| 9 | Pick a JSON file from phone storage | ✅ | Flet's built-in `FilePicker` (`with_data=True`, `.json` filter) read `plans/examplePlan.json` from Downloads and parsed it: 3 cycle days, 5 exercises. |
| 10 | Pre-commit secret scan blocks keys | ✅ | Blocked fake AWS key, fake `sb_secret_` key and a password inside a database URL. |
| 11 | Flet's Android Python version | ✅ | 3.14.7 = same as the PC → plain `python3 -m venv` (V1e). Pinned `requires-python = "==3.14.*"`. |
| 12 | Version name `0.1-alpha` accepted | ✅ | APK: versionName `0.1-alpha`, versionCode `1`. No three-number version needed. versionCode must increase every release. |

Also confirmed: dark mode follows the phone setting (G1).
