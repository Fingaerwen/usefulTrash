"""Restores a backup into the cloud (F13.1): turns a backup zip (from Google Drive or Export CSV) into one
SQL script for Supabase's SQL editor, run the same way as a cloud upgrade. It needs no secret and sends
nothing anywhere: it only reads the zip and prints SQL. The guide is docs/restore.md.

Usage (from the repo root): python3 tools/restoreBackup.py <backup.zip> [--backupWins] > restore.sql
  Without --backupWins it fills in what's missing: the cloud keeps the newest edit of every row (F11.1),
  so a row changed after the backup stays as it is. That's the one for data that went missing.
  --backupWins puts every row of the backup back as it was then, by stamping each with the restore's
  time so it counts as the newest edit; rows made after the backup stay. The phones fetch the restored
  rows at their next sync.
It refuses a backup made by a newer data structure than this code knows (update the repo first). An older
one restores: the columns it doesn't have keep their defaults.
"""

import sys
from pathlib import Path

repoRoot = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repoRoot / "apps/gym/src"), str(repoRoot / "shared/src")]

from gym.tables import appSchema, appTables  # noqa: E402
from usefulShared.backup.backupFile import readBackupZip  # noqa: E402

rowsPerInsert = 200  # rows in one INSERT, so a big table makes a handful of statements


def literal(text: str, cloudType: str) -> str:
    """A CSV cell as an SQL value of the column's type; an empty cell is NULL."""
    if text == "":
        return "null"
    return "'" + text.replace("'", "''") + "'::" + cloudType


def restoreSql(content: bytes, backupWins: bool = False) -> str:
    """The restore script for a backup zip."""
    manifest, rowsByTable = readBackupZip(content)
    if manifest.get("app") != "usefulTrash":
        raise ValueError("This isn't a Gym Tracker backup (its manifest.json doesn't say usefulTrash).")
    schema = int(manifest["schemaVersion"])
    if schema > appSchema:
        raise ValueError(f"The backup has data structure {schema}, this code only knows up to {appSchema}: "
                         "update the repo first.")
    tables = {table.name: table for table in appTables}
    total = sum(len(rows) for name, rows in rowsByTable.items() if name in tables)
    lines = [f"-- Restore of a Gym Tracker backup made {manifest['madeAt']} by the {manifest['madeBy']}, data "
             f"structure {schema}; {total} rows. " + ("Every row back as it was in the backup."
                                                      if backupWins else "Fills in what's missing."),
             "begin;",
             "do $$ begin",
             f"    if (select \"schemaVersion\" from public.\"cloudInfo\" where \"id\" = 1) < {schema} then",
             f"        raise exception 'restore: run cloud upgrade {schema:03d} first';",
             "    end if;",
             "end $$;"]
    for name, rows in rowsByTable.items():
        table = tables.get(name)
        if table is None or not rows:
            continue
        columns = [column for column in table.columns if column.name in rows[0] and not column.stampedByCloud]
        names = ", ".join(f'"{column.name}"' for column in columns)
        updates = ", ".join(f'"{column.name}" = excluded."{column.name}"' for column in columns if column.name != "id")
        for start in range(0, len(rows), rowsPerInsert):
            values = ",\n    ".join(
                "(" + ", ".join("now()" if backupWins and column.name == "updatedAt"
                                else literal(row[column.name], column.cloudType) for column in columns) + ")"
                for row in rows[start:start + rowsPerInsert])
            lines.append(f'insert into public."{name}" ({names}) values\n    {values}\n'
                         f'on conflict ("id") do update set {updates};')
    lines += ["commit;", f"select 'done: {total} rows from the backup' as \"restore\";"]
    return "\n".join(lines) + "\n"


def main(arguments: list[str]) -> int:
    files = [argument for argument in arguments if not argument.startswith("--")]
    if len(files) != 1 or set(arguments) - {*files, "--backupWins"}:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        print(restoreSql(Path(files[0]).read_bytes(), "--backupWins" in arguments), end="")
    except (OSError, ValueError, KeyError) as problem:
        print(f"Can't restore {files[0]}: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
