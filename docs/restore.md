# Restoring a backup (F13.1)

Backups are zips: one CSV file per table, every row in it (deleted ones too), and `manifest.json` with the
data-structure version. The phone puts one in your Google Drive (folder **Gym Tracker backups**) every 30
days and keeps the last 3, plus **GymTracker-history.zip**, which every backup is merged into and which
is never rotated out (a row stays in it even if it's later gone from the cloud). The PC view's Backup tab
makes one on request (**Back up now**) or saves one to your PC (**Export CSV**). The history file and
Export CSV also hold the readable history: `sets.csv`, `weighIns.csv`, `steps.csv` and `diary.csv`.

Ambrosia backs up its own tables the same way, into its own folder **Ambrosia backups**: dated
`Ambrosia-backup-….zip` files, the last 3 kept, and **Ambrosia-history.zip** with the readable `food.csv` (every
entry) and `days.csv` (each day against its targets). Each backup's `manifest.json` says which app it's from, so
the restore below works the same for both and puts the rows back into that app's tables.

## When something went missing

1. Get the backup zip: from Google Drive (folder **Gym Tracker backups**: the newest dated one, or
   `GymTracker-history.zip` for everything ever backed up, or the same from **Ambrosia backups**) or an Export
   CSV zip on your PC.
2. On the PC, from the repo folder:
   `python3 tools/restoreBackup.py ~/Downloads/GymTracker-backup-….zip > restore.sql`
3. Supabase → your project → **SQL Editor** → **New query** → paste the whole of `restore.sql` → **Run**.
   It says `done: N rows from the backup`.
4. Open the app on the phone: it fetches the restored rows at its next sync (within a minute). The PC
   view after a reload.

This **fills in what's missing**: the cloud keeps the newest edit of every row, so anything you changed
after the backup stays as it is.

## To put everything back as it was in the backup

Same steps, with `--backupWins` in step 2:
`python3 tools/restoreBackup.py <backup.zip> --backupWins > restore.sql`

Every row of the backup becomes the newest edit, so your later changes to those rows are replaced. Rows
made after the backup (a workout logged since, say) stay.

## Good to know

- The script needs no password or key and sends nothing anywhere: it only reads the zip and prints SQL.
  Supabase's SQL editor runs it as you, the project's owner.
- It refuses a backup made by a newer version of the data structure than the repo knows: pull the repo
  first. An older backup restores fine.
- It's tested on a throwaway local copy (`tests/cloud/testCloudScripts.py`), never on your data, and the
  test runs again whenever the data structure changes.
